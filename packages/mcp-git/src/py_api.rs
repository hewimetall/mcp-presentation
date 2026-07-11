use crate::adapter::gix_adapter::GixGitAdapter;
use crate::port::GitPort;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use std::path::PathBuf;

/// Python-facing git service (port → gix adapter).
#[pyclass(name = "GitService")]
pub struct GitService {
    inner: GixGitAdapter,
}

#[pymethods]
impl GitService {
    #[new]
    fn new() -> Self {
        Self {
            inner: GixGitAdapter::new(),
        }
    }

    fn init_bare(&self, path: &str) -> PyResult<String> {
        let p = self
            .inner
            .init_bare(&PathBuf::from(path))
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        Ok(p.display().to_string())
    }

    #[pyo3(signature = (bare, worktree_path, ref_name="HEAD"))]
    fn add_worktree(&self, bare: &str, worktree_path: &str, ref_name: &str) -> PyResult<String> {
        let p = self
            .inner
            .add_worktree(
                &PathBuf::from(bare),
                &PathBuf::from(worktree_path),
                ref_name,
            )
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        Ok(p.display().to_string())
    }

    #[pyo3(signature = (worktree_path, message, paths=None))]
    fn commit(
        &self,
        worktree_path: &str,
        message: &str,
        paths: Option<Vec<String>>,
    ) -> PyResult<String> {
        let paths = paths.unwrap_or_default();
        self.inner
            .commit(&PathBuf::from(worktree_path), message, &paths)
            .map_err(|e| PyValueError::new_err(e.to_string()))
    }
}

#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<GitService>()?;
    Ok(())
}
