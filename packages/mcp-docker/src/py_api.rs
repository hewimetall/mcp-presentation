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
            inner: BollardDockerAdapter::new()
                .map_err(|e| PyValueError::new_err(e.to_string()))?,
        })
    }

    #[pyo3(signature = (image, cmd, binds=None, workdir=None, env=None, auto_remove=true))]
    fn run<'py>(
        &self,
        py: Python<'py>,
        image: &str,
        cmd: Vec<String>,
        binds: Option<Vec<String>>,
        workdir: Option<String>,
        env: Option<Vec<String>>,
        auto_remove: bool,
    ) -> PyResult<Bound<'py, PyDict>> {
        let req = RunContainerRequest {
            image: image.to_string(),
            cmd,
            binds: binds.unwrap_or_default(),
            workdir,
            env: env.unwrap_or_default(),
            auto_remove,
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
