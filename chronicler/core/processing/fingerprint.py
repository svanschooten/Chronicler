"""Cheap content fingerprints for deciding whether an audio source has changed."""

import hashlib
from pathlib import Path

SAMPLE_BYTES = 256 * 1024


def fingerprint_file(path: Path) -> str:
    """A hex digest over the file's size plus its leading and trailing bytes."""
    size = path.stat().st_size
    digest = hashlib.blake2b(str(size).encode(), digest_size=16)

    with path.open("rb") as handle:
        digest.update(handle.read(SAMPLE_BYTES))
        if size > SAMPLE_BYTES * 2:
            handle.seek(-SAMPLE_BYTES, 2)
            digest.update(handle.read(SAMPLE_BYTES))

    return digest.hexdigest()
