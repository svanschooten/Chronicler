"""
Every external artifact the embedded-runtime build downloads, pinned by checksum.

Bumping one means changing its URL and sha256 together; the build refuses a download
whose digest does not match.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Artifact:
    url: str
    sha256: str

    @property
    def filename(self) -> str:
        return self.url.rsplit("/", 1)[-1].replace("%2B", "+")


@dataclass(frozen=True)
class Platform:
    name: str
    uv_platform: str
    python_path: str
    site_packages: str
    executable_suffix: str
    trim: tuple[str, ...]


PYTHON_VERSION = "3.12"

_STANDALONE = "https://github.com/astral-sh/python-build-standalone/releases/download/20260901"

PYTHON_RUNTIMES = {
    "linux": Artifact(
        f"{_STANDALONE}/cpython-3.12.14%2B20260901-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz",
        "72748da13197c1fb161e3afeef20a6a385ff24f2165e6e2758e47008e7faba4c",
    ),
    "windows": Artifact(
        f"{_STANDALONE}/cpython-3.12.14%2B20260901-x86_64-pc-windows-msvc-install_only_stripped.tar.gz",
        "7c45c9622400d578709a9b2cddbe8124cc21d382409d9f13406d706d28e31b14",
    ),
}

FLET_CLIENT_VERSION = "0.86.5"

_FLET = f"https://github.com/flet-dev/flet/releases/download/v{FLET_CLIENT_VERSION}"

# debian10 is the lowest-glibc Linux client (2.28), matching the manylinux_2_28 wheels.
FLET_CLIENTS = {
    "linux": Artifact(
        f"{_FLET}/flet-linux-debian10-light-amd64.tar.gz",
        "6a7b660f09fd794b30b670b4341fd81cb0bc38b71a419e0c48f86d67c413403d",
    ),
    "windows": Artifact(
        f"{_FLET}/flet-windows.zip",
        "ded43763d47debd4474c6580ecbafdd745e7eb916d71d96e617fe655edfb37ac",
    ),
}

PYAPP_SOURCE = Artifact(
    "https://github.com/ofek/pyapp/releases/download/v0.29.0/source.tar.gz",
    "0533004baf6d1d46ef15abad02e98881ec92291c024182a36b57931c8d66df5f",
)

PLATFORMS = {
    "linux": Platform(
        name="linux",
        uv_platform="x86_64-manylinux_2_28",
        python_path="python/bin/python3",
        site_packages="python/lib/python3.12/site-packages",
        executable_suffix="",
        # The interpreter is statically linked, so libpython.so is a duplicate.
        trim=(
            "python/include",
            "python/lib/libpython3.12.so",
            "python/lib/libpython3.12.so.1.0",
            "python/lib/python3.12/tkinter",
            "python/lib/python3.12/idlelib",
            "python/lib/python3.12/turtledemo",
            "python/lib/python3.12/lib2to3",
            "python/lib/python3.12/ensurepip",
            "python/lib/tcl*",
            "python/lib/tk*",
            "python/lib/itcl*",
            "python/lib/thread*",
            "python/lib/python3.12/lib-dynload/_tkinter*",
        ),
    ),
    "windows": Platform(
        name="windows",
        uv_platform="x86_64-pc-windows-msvc",
        python_path="python\\python.exe",
        site_packages="python\\Lib\\site-packages",
        executable_suffix=".exe",
        trim=(
            "python/include",
            "python/libs",
            "python/tcl",
            "python/Lib/tkinter",
            "python/Lib/idlelib",
            "python/Lib/turtledemo",
            "python/Lib/lib2to3",
            "python/Lib/ensurepip",
            "python/DLLs/_tkinter.pyd",
            "python/DLLs/tcl86t.dll",
            "python/DLLs/tk86t.dll",
        ),
    ),
}

# Sixteen seconds of public-domain English speech, for the post-build transcription check.
SMOKE_AUDIO = Artifact(
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-segmentation-models/1-two-speakers-en.wav",
    "f1c877dc01595e28be7147bf2fe38e5268147a868bf3fdb5c37b97f5940e21f3",
)

# llama-cpp-python is deliberately absent: PyPI has no wheels for it, so local .gguf
# models stay a source-install feature.
COMPONENTS = ("transcription", "normalization", "recording")
