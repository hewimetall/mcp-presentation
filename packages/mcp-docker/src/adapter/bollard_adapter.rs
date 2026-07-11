use crate::port::{ContainerError, ContainerRuntime, RunContainerRequest, RunContainerResult};
use bollard::container::{
    Config, CreateContainerOptions, LogOutput, LogsOptions, RemoveContainerOptions,
    StartContainerOptions, WaitContainerOptions,
};
use bollard::models::HostConfig;
use bollard::Docker;
use futures_util::StreamExt;
use tokio::runtime::Runtime;

/// bollard-backed adapter — talks to Docker Engine API (DooD socket), never CLI.
pub struct BollardDockerAdapter {
    rt: Runtime,
}

impl BollardDockerAdapter {
    pub fn new() -> Result<Self, ContainerError> {
        let rt = Runtime::new().map_err(|e| ContainerError::msg(e.to_string()))?;
        Ok(Self { rt })
    }
}

impl ContainerRuntime for BollardDockerAdapter {
    fn run(&self, req: RunContainerRequest) -> Result<RunContainerResult, ContainerError> {
        self.rt.block_on(async move { run_async(req).await })
    }
}

async fn run_async(req: RunContainerRequest) -> Result<RunContainerResult, ContainerError> {
    let docker = Docker::connect_with_local_defaults()
        .map_err(|e| ContainerError::msg(format!("connect docker: {e}")))?;

    let host_config = HostConfig {
        binds: Some(req.binds.clone()),
        auto_remove: Some(false), // remove explicitly after wait for log capture
        ..Default::default()
    };

    let config = Config {
        image: Some(req.image.clone()),
        cmd: Some(req.cmd.clone()),
        working_dir: req.workdir.clone(),
        env: if req.env.is_empty() {
            None
        } else {
            Some(req.env.clone())
        },
        host_config: Some(host_config),
        ..Default::default()
    };

    let created = docker
        .create_container(None::<CreateContainerOptions<String>>, config)
        .await
        .map_err(|e| ContainerError::msg(format!("create: {e}")))?;
    let id = created.id;

    docker
        .start_container(&id, None::<StartContainerOptions<String>>)
        .await
        .map_err(|e| ContainerError::msg(format!("start: {e}")))?;

    let mut wait_stream = docker.wait_container(
        &id,
        Some(WaitContainerOptions {
            condition: "not-running",
        }),
    );
    let mut status_code: i64 = -1;
    while let Some(msg) = wait_stream.next().await {
        let msg = msg.map_err(|e| ContainerError::msg(format!("wait: {e}")))?;
        status_code = msg.status_code;
    }

    let mut log_stream = docker.logs(
        &id,
        Some(LogsOptions::<String> {
            stdout: true,
            stderr: true,
            follow: false,
            ..Default::default()
        }),
    );
    let mut logs = String::new();
    while let Some(item) = log_stream.next().await {
        match item {
            Ok(LogOutput::StdOut { message }) | Ok(LogOutput::StdErr { message }) => {
                logs.push_str(&String::from_utf8_lossy(&message));
            }
            Ok(_) => {}
            Err(e) => {
                logs.push_str(&format!("\n[log error: {e}]"));
                break;
            }
        }
    }

    if req.auto_remove {
        let _ = docker
            .remove_container(
                &id,
                Some(RemoveContainerOptions {
                    force: true,
                    ..Default::default()
                }),
            )
            .await;
    }

    Ok(RunContainerResult {
        status_code,
        logs,
        container_id: id,
    })
}
