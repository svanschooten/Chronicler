"""Staging files for import into a workspace's imports/ directory.

Shared between the RPC server's /upload endpoint (chronicler/core/rpc.py) and the
desktop app's local file-picker import flow (chronicler/desktop/views/archive.py) - both
need the same rule: never trust a caller-supplied filename to build a destination path.
"""

import shutil
import uuid
from pathlib import Path


def sanitize_stage_name(original_filename: str | None) -> str:
    """A fresh, collision-proof on-disk filename for a staged import file: a uuid4 with
    only a whitelisted extension carried over from the original name, never the name
    itself - so a path-traversal or otherwise malicious filename never reaches the
    filesystem, regardless of where it came from (upload or a local file picker).
    """
    raw_suffix = Path(original_filename).suffix if original_filename else ""
    safe_suffix = "".join(c for c in raw_suffix if c.isalnum() or c == ".")[:16]
    return f"{uuid.uuid4().hex}{safe_suffix}"


def stage_local_file(source_path: Path, imports_dir: Path) -> Path:
    """Copy a local file (e.g. one returned by a native file picker) into imports_dir
    under a fresh, safe name, and return the staged path. The source path itself is
    never queued for import - only the staged copy is, so it satisfies the same
    "must be inside the workspace's imports directory" confinement that
    WorkerHandlers.handle_import enforces regardless of caller.
    """
    dest_path = imports_dir / sanitize_stage_name(source_path.name)
    shutil.copyfile(source_path, dest_path)
    return dest_path
