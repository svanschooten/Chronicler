"""Chronicler: a local-first archive for conversation transcripts."""

# The one place the release number is written. Hatchling reads it from here
# (see [tool.hatch.version] in pyproject.toml), so a release is this one edit.
# The release workflow stamps the tag over this line before it builds, so the
# binaries follow the tag even when this was forgotten.
__version__ = "1.0.8"
