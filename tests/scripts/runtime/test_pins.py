"""Tests for the embedded-runtime build's pinned artifacts and helpers."""

import re
import struct

import pytest

from chronicler.core import extras
from scripts.runtime import pins, smoke

SHA256 = re.compile(r"^[0-9a-f]{64}$")


def all_artifacts() -> list[pins.Artifact]:
    return [
        *pins.PYTHON_RUNTIMES.values(),
        *pins.FLET_CLIENTS.values(),
        pins.PYAPP_SOURCE,
        pins.SMOKE_AUDIO,
    ]


@pytest.mark.parametrize("artifact", all_artifacts(), ids=lambda artifact: artifact.filename)
def test_every_download_is_pinned_by_checksum(artifact):
    assert artifact.url.startswith("https://")
    assert SHA256.match(artifact.sha256)


def test_every_platform_has_a_python_and_a_flet_client():
    assert set(pins.PYTHON_RUNTIMES) == set(pins.PLATFORMS) == set(pins.FLET_CLIENTS)


def test_the_flet_clients_are_the_pinned_version():
    for artifact in pins.FLET_CLIENTS.values():
        assert f"/v{pins.FLET_CLIENT_VERSION}/" in artifact.url


def test_every_extra_except_the_local_llm_is_a_component():
    """llama-cpp-python has no wheels on PyPI, so local models stay a source install."""
    assert set(pins.COMPONENTS) == set(extras.EXTRAS) - {"llm"}


def test_a_filename_is_readable_rather_than_url_encoded():
    assert "+" in pins.PYTHON_RUNTIMES["linux"].filename


def pe_header(subsystem: int) -> bytes:
    header = bytearray(512)
    struct.pack_into("<I", header, 0x3C, 0x80)
    struct.pack_into("<H", header, 0x80 + 24 + 68, subsystem)
    return bytes(header)


@pytest.mark.parametrize(("value", "expected"), [(2, "GUI"), (3, "console"), (9, "subsystem 9")])
def test_the_windows_subsystem_is_read_from_the_pe_header(tmp_path, value, expected):
    executable = tmp_path / "Chronicler.exe"
    executable.write_bytes(pe_header(value))

    assert smoke.pe_subsystem(executable) == expected


def test_the_windows_gui_launcher_is_patched_once(tmp_path):
    from scripts.runtime import build

    main = tmp_path / "main.rs"
    main.write_text("mod app;\n")

    build.use_windows_gui_subsystem(main)
    build.use_windows_gui_subsystem(main)

    assert main.read_text() == f"{build.WINDOWS_GUI_ATTRIBUTE}\nmod app;\n"
