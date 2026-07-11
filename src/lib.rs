use parking_lot::Mutex;
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;
use rusqlite::{params, Connection, OptionalExtension};
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};
use uuid::Uuid;

const SCHEMA: &str = r#"
CREATE TABLE IF NOT EXISTS tasks (
    task_id     TEXT PRIMARY KEY,
    session_id  TEXT,
    workspace   TEXT,
    target      TEXT NOT NULL,
    status      TEXT NOT NULL,
    artifact    TEXT,
    logs        TEXT,
    error       TEXT,
    created_at  INTEGER NOT NULL,
    updated_at  INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_status_created
  ON tasks(status, created_at);
"#;

fn now_secs() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

fn open_db(path: &str) -> PyResult<Connection> {
    if let Some(parent) = Path::new(path).parent() {
        if !parent.as_os_str().is_empty() {
            std::fs::create_dir_all(parent).map_err(|e| {
                PyValueError::new_err(format!("cannot create db dir {}: {e}", parent.display()))
            })?;
        }
    }
    let conn = Connection::open(path)
        .map_err(|e| PyValueError::new_err(format!("sqlite open {path}: {e}")))?;
    conn.execute_batch(
        "PRAGMA journal_mode=WAL;
         PRAGMA busy_timeout=30000;
         PRAGMA foreign_keys=ON;",
    )
    .map_err(|e| PyValueError::new_err(format!("pragma: {e}")))?;
    conn.execute_batch(SCHEMA)
        .map_err(|e| PyValueError::new_err(format!("schema: {e}")))?;
    Ok(conn)
}

/// Persistent task store backed by embedded SQLite (rusqlite).
#[pyclass(name = "TaskStore")]
struct TaskStore {
    conn: Mutex<Connection>,
}

#[pymethods]
impl TaskStore {
    #[new]
    fn new(path: &str) -> PyResult<Self> {
        Ok(Self {
            conn: Mutex::new(open_db(path)?),
        })
    }

    /// Insert a queued task; returns task_id.
    fn submit(&self, session_id: &str, workspace: &str, target: &str) -> PyResult<String> {
        let tid = Uuid::new_v4().to_string();
        let ts = now_secs();
        let conn = self.conn.lock();
        conn.execute(
            "INSERT INTO tasks(
                task_id, session_id, workspace, target, status,
                created_at, updated_at
             ) VALUES (?1, ?2, ?3, ?4, 'queued', ?5, ?5)",
            params![tid, session_id, workspace, target, ts],
        )
        .map_err(|e| PyValueError::new_err(format!("submit: {e}")))?;
        Ok(tid)
    }

    /// Partial update. Only provided (Some) fields are written.
    #[pyo3(signature = (task_id, status=None, artifact=None, logs=None, error=None))]
    fn update(
        &self,
        task_id: &str,
        status: Option<&str>,
        artifact: Option<&str>,
        logs: Option<&str>,
        error: Option<&str>,
    ) -> PyResult<()> {
        let ts = now_secs();
        let conn = self.conn.lock();
        let n = conn
            .execute(
                "UPDATE tasks SET
                    status   = COALESCE(?2, status),
                    artifact = COALESCE(?3, artifact),
                    logs     = COALESCE(?4, logs),
                    error    = COALESCE(?5, error),
                    updated_at = ?6
                 WHERE task_id = ?1",
                params![task_id, status, artifact, logs, error, ts],
            )
            .map_err(|e| PyValueError::new_err(format!("update: {e}")))?;
        if n == 0 {
            return Err(PyValueError::new_err(format!("task not found: {task_id}")));
        }
        Ok(())
    }

    /// Fetch one task as a dict, or None.
    fn get<'py>(&self, py: Python<'py>, task_id: &str) -> PyResult<Option<Bound<'py, PyDict>>> {
        let conn = self.conn.lock();
        let row = conn
            .query_row(
                "SELECT task_id, session_id, workspace, target, status,
                        artifact, logs, error, created_at, updated_at
                 FROM tasks WHERE task_id = ?1",
                params![task_id],
                |r| {
                    Ok((
                        r.get::<_, String>(0)?,
                        r.get::<_, Option<String>>(1)?,
                        r.get::<_, Option<String>>(2)?,
                        r.get::<_, String>(3)?,
                        r.get::<_, String>(4)?,
                        r.get::<_, Option<String>>(5)?,
                        r.get::<_, Option<String>>(6)?,
                        r.get::<_, Option<String>>(7)?,
                        r.get::<_, i64>(8)?,
                        r.get::<_, i64>(9)?,
                    ))
                },
            )
            .optional()
            .map_err(|e| PyValueError::new_err(format!("get: {e}")))?;

        match row {
            None => Ok(None),
            Some(t) => Ok(Some(row_to_dict(py, t)?)),
        }
    }

    /// Atomically claim the oldest queued task → running.
    fn claim_next<'py>(&self, py: Python<'py>) -> PyResult<Option<Bound<'py, PyDict>>> {
        let ts = now_secs();
        let conn = self.conn.lock();
        let tx = conn
            .unchecked_transaction()
            .map_err(|e| PyValueError::new_err(format!("tx: {e}")))?;

        let row = tx
            .query_row(
                "SELECT task_id FROM tasks
                 WHERE status = 'queued'
                 ORDER BY created_at ASC
                 LIMIT 1",
                [],
                |r| r.get::<_, String>(0),
            )
            .optional()
            .map_err(|e| PyValueError::new_err(format!("claim select: {e}")))?;

        let Some(tid) = row else {
            return Ok(None);
        };

        tx.execute(
            "UPDATE tasks SET status = 'running', updated_at = ?2 WHERE task_id = ?1",
            params![tid, ts],
        )
        .map_err(|e| PyValueError::new_err(format!("claim update: {e}")))?;

        let full = tx
            .query_row(
                "SELECT task_id, session_id, workspace, target, status,
                        artifact, logs, error, created_at, updated_at
                 FROM tasks WHERE task_id = ?1",
                params![tid],
                |r| {
                    Ok((
                        r.get::<_, String>(0)?,
                        r.get::<_, Option<String>>(1)?,
                        r.get::<_, Option<String>>(2)?,
                        r.get::<_, String>(3)?,
                        r.get::<_, String>(4)?,
                        r.get::<_, Option<String>>(5)?,
                        r.get::<_, Option<String>>(6)?,
                        r.get::<_, Option<String>>(7)?,
                        r.get::<_, i64>(8)?,
                        r.get::<_, i64>(9)?,
                    ))
                },
            )
            .map_err(|e| PyValueError::new_err(format!("claim fetch: {e}")))?;

        tx.commit()
            .map_err(|e| PyValueError::new_err(format!("commit: {e}")))?;

        Ok(Some(row_to_dict(py, full)?))
    }
}

type TaskRow = (
    String,
    Option<String>,
    Option<String>,
    String,
    String,
    Option<String>,
    Option<String>,
    Option<String>,
    i64,
    i64,
);

fn row_to_dict(py: Python<'_>, t: TaskRow) -> PyResult<Bound<'_, PyDict>> {
    let d = PyDict::new(py);
    d.set_item("task_id", t.0)?;
    d.set_item("session_id", t.1)?;
    d.set_item("workspace", t.2)?;
    d.set_item("target", t.3)?;
    d.set_item("status", t.4)?;
    d.set_item("artifact", t.5)?;
    d.set_item("logs", t.6)?;
    d.set_item("error", t.7)?;
    d.set_item("created_at", t.8)?;
    d.set_item("updated_at", t.9)?;
    Ok(d)
}

#[pymodule]
fn _tasks(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<TaskStore>()?;
    Ok(())
}
