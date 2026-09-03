"""Staging files for import into a workspace's imports/ directory."""

import shutil
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

import httpx


def sanitize_stage_name(original_filename: str | None) -> str:
    """A uuid4 filename carrying only a whitelisted extension from the original name."""
    raw_suffix = Path(original_filename).suffix if original_filename else ""
    safe_suffix = "".join(c for c in raw_suffix if c.isalnum() or c == ".")[:16]
    return f"{uuid.uuid4().hex}{safe_suffix}"


def confine_to_directory(file_path: str | Path, root: Path, description: str) -> Path:
    """Resolve `file_path` and reject it if it lands outside `root`."""
    resolved = Path(file_path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"file_path must be inside {description}: {file_path}")
    return resolved


def safe_display_name(original_filename: str | None, fallback: str) -> str:
    """The caller-supplied name reduced to a single, harmless path component."""
    name = Path((original_filename or "").replace("\\", "/")).name
    name = name.replace(":", "_").strip()
    if not name or name in (".", ".."):
        return fallback
    return name


def stage_local_file(source_path: Path, imports_dir: Path) -> Path:
    """
    Copy a local file (e.g. one returned by a native file picker) into imports_dir under a
    fresh, safe name, and return the staged path.
    """
    dest_path = imports_dir / sanitize_stage_name(source_path.name)
    shutil.copyfile(source_path, dest_path)
    return dest_path


class FileStager(ABC):
    """
    Turns a locally-picked file path into something safe to pass to TaskService.queue_import
    - the same operation, two different mechanisms depending on where the worker that will
    actually read the file runs.
    """

    @abstractmethod
    async def stage(self, local_path: str) -> str:
        pass


class LocalFileStager(FileStager):
    """
    Full-stack desktop mode: the worker runs in this same process, so staging is just a
    local copy into the workspace's imports directory.
    """

    def __init__(self, imports_dir: Path):
        self.imports_dir = imports_dir

    async def stage(self, local_path: str) -> str:
        return str(stage_local_file(Path(local_path), self.imports_dir))


class RemoteFileStager(FileStager):
    """
    Thin-client desktop mode: the worker runs on the remote server, so the picked file has
    to actually get there first - upload it via the same /upload endpoint the web client's
    proxy already uses, and return the path the server reports back.
    """

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
