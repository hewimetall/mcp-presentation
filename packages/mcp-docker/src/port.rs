use serde::{Deserialize, Serialize};
use thiserror::Error;

#[derive(Debug, Error)]
pub enum ContainerError {
    #[error("{0}")]
    Message(String),
}

impl ContainerError {
    pub fn msg(s: impl Into<String>) -> Self {
        Self::Message(s.into())
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RunContainerRequest {
    pub image: String,
    pub cmd: Vec<String>,
    /// Host:container bind mounts, e.g. "/abs/ws:/work"
    pub binds: Vec<String>,
    pub workdir: Option<String>,
    pub env: Vec<String>,
    pub auto_remove: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RunContainerResult {
    pub status_code: i64,
    pub logs: String,
    pub container_id: String,
}

/// Application port for running build containers (ADR-0012).
pub trait ContainerRuntime: Send + Sync {
    fn run(&self, req: RunContainerRequest) -> Result<RunContainerResult, ContainerError>;
}
