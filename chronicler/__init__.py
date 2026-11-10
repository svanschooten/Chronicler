"""Chronicler: a local-first archive for conversation transcripts."""

# The one place the release number is written. Hatchling reads it from here
# (see [tool.hatch.version] in pyproject.toml), so a release is this one edit.
# Bump it as the first step of every release (docs/packaging.md). The release workflow
# stamps the tag over this line before it builds, but a source checkout is not rebuilt:
# the handshake needs an exact match, so a stale value refuses a server built from the tag.
__version__ = "1.1.5"
