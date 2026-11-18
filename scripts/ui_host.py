"""
Prepares the Flutter client the rendered UI tests in `tests/ui/` connect through.

`flet.testing` in host mode runs the app in the test process and drives a Flutter client
that connects back to it. That client is Flet's own `client/`, fetched at the tag of the
installed Flet so the protocol matches, and trimmed in two ways:

- Every Flet extension (ads, maps, video, webview, ...) is removed. Chronicler uses none,
  and they need system libraries a test runner does not have.
- Flet pins `jni` to 1.0.0 to dodge an ARM64 build bug (dart-lang/native#3498), but the
  current `jni_flutter` and `shared_preferences_android` need ^1.1, so `flutter pub get`
  fails. The override is lifted to ^1.1.1, which builds on x86_64. Drop this once upstream
  releases a fixed `jni`.

Usage:
    python scripts/ui_host.py [DEST]        # default DEST: build/ui-host
    python scripts/ui_host.py --flutter-version

The client ends up in `DEST/client`; point `FLET_TEST_FLUTTER_APP_DIR` at it. See
docs/testing.md.
"""

import argparse
import re
import shutil
import subprocess
import sys
from importlib.metadata import version
from pathlib import Path

FLET_REPOSITORY = "https://github.com/flet-dev/flet"
KEPT_PACKAGES = {"flet", "flet_integration_test"}
"""The Dart packages from Flet's repository the trimmed client still depends on."""

JNI_PIN = "  jni: 1.0.0\n"
JNI_LIFTED = "  jni: ^1.1.1\n"

_EXTENSION_IMPORT = re.compile(r"""^import ['"]package:(flet_\w+)/[^;]*;\n""", re.MULTILINE)
_EXTENSION_REGISTRATION = re.compile(r"^\s*\w+\.Extension\(\),\n", re.MULTILINE)
_SDK_PATH_DEPENDENCY = re.compile(r"^  \w+:\n    path: \.\./sdk/[^\n]*\n", re.MULTILINE)
_JNI_LINE = re.compile(r"^ *jni:.*$", re.MULTILINE)


def trim_main(source: str) -> str:
    """Removes every extension import and registration from the client's `main.dart`."""

    def drop_extension(match: re.Match[str]) -> str:
        return match.group(0) if match.group(1) in KEPT_PACKAGES else ""

    source = _EXTENSION_IMPORT.sub(drop_extension, source)
    return _EXTENSION_REGISTRATION.sub("", source)


def trim_pubspec(source: str) -> str:
    """Removes the extension dependencies and lifts the `jni` override."""
    source = _SDK_PATH_DEPENDENCY.sub("", source)
    if "../sdk/" in source:
        raise ValueError("pubspec.yaml still depends on a package under ../sdk/")
    source = source.replace(JNI_PIN, JNI_LIFTED)
    # No `jni` line at all is fine: upstream has dropped the pin. Any other form of it
    # would be left in place and fail `flutter pub get` with a less helpful message.
    for line in _JNI_LINE.findall(source):
        if line != JNI_LIFTED.rstrip("\n"):
            raise ValueError(f"pubspec.yaml pins jni in a form this script does not lift: {line}")
    return source


def fetch(tag: str, dest: Path) -> Path:
    """Checks out only `client/` and the Dart packages it needs, at the given tag."""
    if dest.exists():
        shutil.rmtree(dest)
    subprocess.run(
        [
            "git",
            "-c",
            "advice.detachedHead=false",
            "clone",
            "--quiet",
            "--depth",
            "1",
            "--branch",
            tag,
            "--filter=blob:none",
        ]
        + ["--sparse", FLET_REPOSITORY, str(dest)],
        check=True,
    )
    packages = [f"packages/{name}" for name in sorted(KEPT_PACKAGES)]
    subprocess.run(
        ["git", "-C", str(dest), "sparse-checkout", "set", "client", *packages], check=True
    )
    return dest / "client"


def prepare(dest: Path) -> Path:
    client = fetch(f"v{version('flet')}", dest)
    for name, trim in (("lib/main.dart", trim_main), ("pubspec.yaml", trim_pubspec)):
        path = client / name
        path.write_text(trim(path.read_text(encoding="utf-8")), encoding="utf-8")
    return client


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("dest", nargs="?", default="build/ui-host", type=Path)
    parser.add_argument(
        "--flutter-version",
        action="store_true",
        help="print the Flutter version the installed Flet builds with, and exit",
    )
    args = parser.parse_args(argv)
    if args.flutter_version:
        from flet.version import flutter_version

        print(flutter_version)
        return 0
    print(prepare(args.dest.resolve()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
