"""Local deploy adapter — copy artifact into workspace out/deployed (ADR-0007)."""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Literal, TypedDict


class DeployResult(TypedDict):
    deployed_path: str
    source: str
    manifest: str
    deploy_kind: Literal["local_copy"]
    note: str


DEPLOY_NOTE = "local filesystem copy under out/deployed/; not a public URL (v1 has no CDN/hosting)"


def deploy_local(workspace: Path, artifact: Path) -> DeployResult:
    """Copy a file or directory into ``out/deployed`` and write a manifest."""
    if not artifact.exists():
        msg = f"artifact not found: {artifact}"
        raise FileNotFoundError(msg)

    dest_root = workspace / "out" / "deployed"
    if dest_root.exists():
        shutil.rmtree(dest_root)
    dest_root.mkdir(parents=True, exist_ok=True)

    if artifact.is_dir():
        target = dest_root / artifact.name
        shutil.copytree(artifact, target)
        deployed = target
    else:
        deployed = dest_root / artifact.name
        shutil.copy2(artifact, deployed)

    manifest = dest_root / "manifest.json"
    payload = {
        "source": str(artifact.resolve()),
        "deployed_path": str(deployed.resolve()),
        "deployed_at": int(time.time()),
        "adapter": "local",
        "deploy_kind": "local_copy",
        "note": DEPLOY_NOTE,
    }
    manifest.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return {
        "deployed_path": str(deployed.resolve()),
        "source": str(artifact.resolve()),
        "manifest": str(manifest.resolve()),
        "deploy_kind": "local_copy",
        "note": DEPLOY_NOTE,
    }
