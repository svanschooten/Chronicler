"""Chronicle archive (.zip) packing - a portable copy of one chronicle's own storage."""

import io
import json
import zipfile
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, Field

from chronicler import __version__
from chronicler.core.models import Chronicle

MANIFEST_NAME = "chronicle.json"
DATABASE_NAME = "project.db"
SOURCES_DIR = "sources"


class BundleManifest(BaseModel):
    """
    What a bare `project.db` cannot say about itself.

    Title, description, kind and tags live in the *workspace* database, not the
    chronicle's own, so a database lifted out on its own arrives anonymous - re-linking
    one names it after whatever folder it landed in. See docs/storage.md.
    """

    title: str
    description: str | None = None
    kind: str = "Unknown"
    created_at: datetime | None = None
    duration: str | None = None
    speakers_count: int = 0
    tags: list[str] = []
    sources: list[str] = []
    sources_included: bool = False
    chronicler_version: str = __version__
    exported_at: datetime = Field(default_factory=datetime.now)

    @classmethod
    def of(
        cls, chronicle: Chronicle, sources: Sequence[str], sources_included: bool
    ) -> "BundleManifest":
        return cls(
            title=chronicle.title,
            description=chronicle.description,
            kind=chronicle.kind,
            created_at=chronicle.created_at,
            duration=chronicle.duration,
            speakers_count=chronicle.speakers_count,
            tags=[tag.name for tag in chronicle.tags],
            sources=list(sources),
            sources_included=sources_included,
        )


def format_bundle(
    project_db: Path,
    manifest: BundleManifest,
    root: str,
    sources: Sequence[Path] = (),
) -> bytearray:
    """
    Packs a chronicle into a zip, everything under one `root` folder so unpacking it
    somewhere busy leaves one directory behind rather than loose files.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(
            f"{root}/{MANIFEST_NAME}",
            json.dumps(json.loads(manifest.model_dump_json()), indent=2) + "\n",
        )
        bundle.write(project_db, f"{root}/{DATABASE_NAME}")
        for source in sources:
            bundle.write(source, f"{root}/{SOURCES_DIR}/{source.name}")

    return bytearray(buffer.getvalue())


def safe_folder_name(title: str, fallback: str = "chronicle") -> str:
    """The chronicle title reduced to something safe as a folder name inside the zip."""
    safe = "".join(c if c.isalnum() or c in " -_" else "_" for c in title).strip()
    return safe or fallback
