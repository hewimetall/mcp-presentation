use crate::port::{GitError, GitPort};
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};

/// gix-backed adapter — never shells out to `git`.
pub struct GixGitAdapter;

impl GixGitAdapter {
    pub fn new() -> Self {
        Self
    }
}

impl Default for GixGitAdapter {
    fn default() -> Self {
        Self::new()
    }
}

impl GitPort for GixGitAdapter {
    fn init_bare(&self, path: &Path) -> Result<PathBuf, GitError> {
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).map_err(|e| GitError::msg(e.to_string()))?;
        }
        let repo = gix::init_bare(path).map_err(|e| GitError::msg(e.to_string()))?;
        Ok(repo.path().to_owned())
    }

    fn add_worktree(
        &self,
        bare: &Path,
        worktree_path: &Path,
        ref_name: &str,
    ) -> Result<PathBuf, GitError> {
        let bare = bare.canonicalize().unwrap_or_else(|_| bare.to_path_buf());
        let repo = gix::open(&bare).map_err(|e| GitError::msg(format!("open bare: {e}")))?;

        if worktree_path.exists()
            && worktree_path
                .read_dir()
                .map(|mut d| d.next().is_some())
                .unwrap_or(false)
        {
            return Err(GitError::msg(format!(
                "worktree path not empty: {}",
                worktree_path.display()
            )));
        }
        fs::create_dir_all(worktree_path).map_err(|e| GitError::msg(e.to_string()))?;

        let name = worktree_path
            .file_name()
            .and_then(|s| s.to_str())
            .ok_or_else(|| GitError::msg("invalid worktree path"))?;

        let wt_git_dir = bare.join("worktrees").join(name);
        fs::create_dir_all(&wt_git_dir).map_err(|e| GitError::msg(e.to_string()))?;

        // Resolve ref → object id (default HEAD)
        let mut head = repo
            .find_reference(ref_name)
            .or_else(|_| repo.find_reference("HEAD"))
            .map_err(|e| GitError::msg(format!("resolve ref {ref_name}: {e}")))?;
        let id = head
            .peel_to_id_in_place()
            .map_err(|e| GitError::msg(format!("peel: {e}")))?;
        let commit = repo
            .find_object(id)
            .map_err(|e| GitError::msg(format!("object: {e}")))?
            .peel_to_commit()
            .map_err(|e| GitError::msg(format!("commit: {e}")))?;
        let tree_id = commit.tree_id().map_err(|e| GitError::msg(e.to_string()))?;

        // Linked worktree metadata (git worktree layout, no CLI)
        let abs_wt = worktree_path
            .canonicalize()
            .unwrap_or_else(|_| worktree_path.to_path_buf());
        write_file(
            &wt_git_dir.join("gitdir"),
            format!("{}\n", abs_wt.join(".git").display()),
        )?;
        write_file(&wt_git_dir.join("commondir"), "../..\n")?;
        write_file(&wt_git_dir.join("HEAD"), format!("{}\n", id.to_hex()))?;

        write_file(
            &worktree_path.join(".git"),
            format!("gitdir: {}\n", wt_git_dir.display()),
        )?;

        // Materialize files from tree (best-effort checkout)
        checkout_tree_to(&repo, tree_id.detach(), worktree_path)?;

        Ok(abs_wt)
    }

    fn commit(
        &self,
        worktree_path: &Path,
        message: &str,
        paths: &[String],
    ) -> Result<String, GitError> {
        let repo =
            gix::open(worktree_path).map_err(|e| GitError::msg(format!("open worktree: {e}")))?;

        // For v1: if paths empty, commit is a no-op message commit on current tree;
        // otherwise require files exist and rebuild tree from worktree files listed.
        if paths.is_empty() {
            return Err(GitError::msg(
                "commit requires at least one path in v1 (stage explicit paths)",
            ));
        }

        for p in paths {
            let full = worktree_path.join(p);
            if !full.is_file() {
                return Err(GitError::msg(format!("missing file for commit: {p}")));
            }
        }

        // Build a simple tree from listed files (flat paths only in v1)
        let mut entries: Vec<(String, gix::ObjectId)> = Vec::new();
        for p in paths {
            let bytes =
                fs::read(worktree_path.join(p)).map_err(|e| GitError::msg(e.to_string()))?;
            let blob_id = repo
                .write_blob(&bytes)
                .map_err(|e| GitError::msg(format!("write blob: {e}")))?
                .detach();
            let name = Path::new(p)
                .file_name()
                .and_then(|s| s.to_str())
                .ok_or_else(|| GitError::msg("bad path"))?
                .to_string();
            // Keep relative path components for nested files
            entries.push((p.replace('\\', "/"), blob_id));
            let _ = name;
        }

        let tree_id = write_flat_tree(&repo, &entries)?;
        let author = gix::actor::Signature {
            name: "mcp-git".into(),
            email: "mcp-git@localhost".into(),
            time: gix::date::Time::now_local_or_utc(),
        };
        let mut author_buf = gix_date::parse::TimeBuf::default();
        let mut committer_buf = gix_date::parse::TimeBuf::default();
        let author_ref = author.to_ref(&mut author_buf);
        let committer_ref = author.to_ref(&mut committer_buf);

        let parent = repo.head_id().ok().map(|id| id.detach());
        let mut parents: Vec<gix::ObjectId> = Vec::new();
        if let Some(p) = parent {
            parents.push(p);
        }

        let commit_id = repo
            .commit_as(
                committer_ref,
                author_ref,
                "HEAD",
                message,
                tree_id,
                parents.iter().copied(),
            )
            .map_err(|e| GitError::msg(format!("commit: {e}")))?;

        Ok(commit_id.to_string())
    }
}

fn write_file(path: &Path, content: impl AsRef<[u8]>) -> Result<(), GitError> {
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent).map_err(|e| GitError::msg(e.to_string()))?;
    }
    let mut f = fs::File::create(path).map_err(|e| GitError::msg(e.to_string()))?;
    f.write_all(content.as_ref())
        .map_err(|e| GitError::msg(e.to_string()))?;
    Ok(())
}

fn checkout_tree_to(
    repo: &gix::Repository,
    tree_id: gix::ObjectId,
    dest: &Path,
) -> Result<(), GitError> {
    // Recursively checkout tree entries as files/dirs (simple, no filters).
    fn walk(repo: &gix::Repository, tree_id: gix::ObjectId, base: &Path) -> Result<(), GitError> {
        let tree = repo
            .find_object(tree_id)
            .map_err(|e| GitError::msg(e.to_string()))?
            .peel_to_tree()
            .map_err(|e| GitError::msg(e.to_string()))?;
        for entry in tree.iter() {
            let entry = entry.map_err(|e| GitError::msg(e.to_string()))?;
            let name = entry.filename().to_string();
            let path = base.join(&name);
            let mode = entry.mode();
            let oid = entry.oid().to_owned();
            if mode.is_tree() {
                fs::create_dir_all(&path).map_err(|e| GitError::msg(e.to_string()))?;
                walk(repo, oid, &path)?;
            } else if mode.is_blob() || mode.is_executable() {
                if let Some(parent) = path.parent() {
                    fs::create_dir_all(parent).map_err(|e| GitError::msg(e.to_string()))?;
                }
                let obj = repo
                    .find_object(oid)
                    .map_err(|e| GitError::msg(e.to_string()))?;
                let blob = obj
                    .try_into_blob()
                    .map_err(|e| GitError::msg(e.to_string()))?;
                fs::write(&path, blob.data.as_slice()).map_err(|e| GitError::msg(e.to_string()))?;
                #[cfg(unix)]
                if mode.is_executable() {
                    use std::os::unix::fs::PermissionsExt;
                    let mut perms = fs::metadata(&path)
                        .map_err(|e| GitError::msg(e.to_string()))?
                        .permissions();
                    perms.set_mode(0o755);
                    fs::set_permissions(&path, perms).map_err(|e| GitError::msg(e.to_string()))?;
                }
            }
        }
        Ok(())
    }
    walk(repo, tree_id, dest)
}

fn write_flat_tree(
    repo: &gix::Repository,
    entries: &[(String, gix::ObjectId)],
) -> Result<gix::ObjectId, GitError> {
    // Nested path support: build tree recursively from path components.
    use std::collections::BTreeMap;

    #[derive(Default)]
    struct Node {
        files: BTreeMap<String, gix::ObjectId>,
        dirs: BTreeMap<String, Node>,
    }

    let mut root = Node::default();
    for (path, oid) in entries {
        let parts: Vec<&str> = path.split('/').filter(|p| !p.is_empty()).collect();
        if parts.is_empty() {
            continue;
        }
        let mut node = &mut root;
        for part in &parts[..parts.len() - 1] {
            node = node.dirs.entry((*part).to_string()).or_default();
        }
        node.files.insert(parts[parts.len() - 1].to_string(), *oid);
    }

    fn write_node(repo: &gix::Repository, node: &Node) -> Result<gix::ObjectId, GitError> {
        let mut tree = gix::objs::Tree::empty();
        for (name, oid) in &node.files {
            tree.entries.push(gix::objs::tree::Entry {
                mode: gix::objs::tree::EntryKind::Blob.into(),
                filename: name.as_str().into(),
                oid: *oid,
            });
        }
        for (name, child) in &node.dirs {
            let child_id = write_node(repo, child)?;
            tree.entries.push(gix::objs::tree::Entry {
                mode: gix::objs::tree::EntryKind::Tree.into(),
                filename: name.as_str().into(),
                oid: child_id,
            });
        }
        tree.entries.sort_by(|a, b| a.filename.cmp(&b.filename));
        Ok(repo
            .write_object(&tree)
            .map_err(|e| GitError::msg(format!("write tree: {e}")))?
            .detach())
    }

    write_node(repo, &root)
}
