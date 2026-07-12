use crate::adapter::bollard_adapter::BollardDockerAdapter;
use crate::port::{ContainerRuntime, RunContainerRequest};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

/// Python-facing docker service (port → bollard adapter).
#[pyclass(name = "DockerService")]
pub struct DockerService {
    inner: BollardDockerAdapter,
}

#[pymethods]
impl DockerService {
    #[new]
    fn new() -> PyResult<Self> {
        Ok(Self {
            inner: BollardDockerAdapter::new().map_err(|e| PyValueError::new_err(e.to_string()))?,
        })
    }

    #[pyo3(signature = (image, cmd, binds=None, workdir=None, env=None, auto_remove=true, user=None))]
    #[allow(clippy::too_many_arguments)]
    fn run<'py>(
        &self,
        py: Python<'py>,
        image: &str,
        cmd: Vec<String>,
        binds: Option<Vec<String>>,
        workdir: Option<String>,
        env: Option<Vec<String>>,
        auto_remove: bool,
        user: Option<String>,
    ) -> PyResult<Bound<'py, PyDict>> {
        let req = RunContainerRequest {
            image: image.to_string(),
            cmd,
            binds: binds.unwrap_or_default(),
            workdir,
            env: env.unwrap_or_default(),
            auto_remove,
            user,
        };
        let res = self
            .inner
            .run(req)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        let d = PyDict::new(py);
        d.set_item("status_code", res.status_code)?;
        d.set_item("logs", res.logs)?;
        d.set_item("container_id", res.container_id)?;
        Ok(d)
    }
}

#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<DockerService>()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use pyo3::types::{PyAnyMethods, PyModule};

    #[test]
    fn py_docker_service_hello_world() {
        Python::attach(|py| {
            let m = PyModule::new(py, "d").unwrap();
            _native(&m).unwrap();
            assert!(m.getattr("DockerService").is_ok());

            let svc = DockerService::new().unwrap();
            let d = svc
                .run(py, "hello-world", vec![], None, None, None, true, None)
                .unwrap();
            let code = d
                .get_item("status_code")
                .unwrap()
                .unwrap()
                .extract::<i64>()
                .unwrap();
            assert_eq!(code, 0);
        });
    }
}
