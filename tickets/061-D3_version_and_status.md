# 061-D3_version_and_status

## Version and project status disagree

### info

| | |
| --- | --- |
| importance | low |
| danger level | Medium: a source checkout refuses a server built from the latest tag. Change risk: very low. |
| reach | Contributors running from source |
| effort | XS |
| evidence | read in code |
| touches | `chronicler/__init__.py`, `pyproject.toml`, `README.md`, `docs/packaging.md` |

### description

`chronicler/__init__.py` says 1.0.8, while the latest tag is v1.1.2. The release workflow
stamps the tag at build time and commits nothing back. The handshake requires an exact
match, so a source checkout refuses a server built from that tag.

`pyproject.toml:16` says Pre-Alpha, the README badge says alpha, and versions are 1.x.
`pyproject.toml:20-22` lists 3.13 twice, while CI tests only 3.12.

### proposed fix

Set `__version__` to the latest release, and make bumping it an explicit release step.
Pick one status and use it everywhere. Remove the duplicate classifier, and either test
3.13 or stop claiming it.

Done when source, tag, badge and classifiers agree.

### related tickets

- none
