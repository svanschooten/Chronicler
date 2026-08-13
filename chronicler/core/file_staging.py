"""Staging files for import into a workspace's imports/ directory.

Shared between the RPC server's /upload endpoint (chronicler/core/rpc.py) and the
desktop app's local file-picker import flow (chronicler/desktop/views/archive.py) - both
need the same rule: never trust a caller-supplied filename to build a destination path.
"""

import shutil
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

import httpx


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


class FileStager(ABC):
    """Turns a locally-picked file path into something safe to pass to
    TaskService.queue_import - the same operation, two different mechanisms depending
    on where the worker that will actually read the file runs.
    """

    @abstractmethod
    async def stage(self, local_path: str) -> str:
        pass


class LocalFileStager(FileStager):
    """Full-stack desktop mode: the worker runs in this same process, so staging is
    just a local copy into the workspace's imports directory."""

    def __init__(self, imports_dir: Path):
        self.imports_dir = imports_dir

    async def stage(self, local_path: str) -> str:
        return str(stage_local_file(Path(local_path), self.imports_dir))


class RemoteFileStager(FileStager):
    """Thin-client desktop mode: the worker runs on the remote server, so the picked
    file has to actually get there first - upload it via the same /upload endpoint the
    web client's proxy already uses, and return the path the server reports back."""

    def __init__(self, base_url: str, api_key: str | None, client: httpx.AsyncClient | None = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._client = client

    async def stage(self, local_path: str) -> str:
        headers = {"X-API-Key": self.api_key} if self.api_key else {}
        client = self._client or httpx.AsyncClient()
        try:
            with open(local_path, "rb") as f:
                files = {"file": (Path(local_path).name, f)}
                response = await client.post(
                    f"{self.base_url}/upload", files=files, headers=headers
                )
            response.raise_for_status()
            return response.json()["file_path"]
        finally:
            if self._client is None:
                await client.aclose()
