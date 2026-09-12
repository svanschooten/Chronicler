"""Tests for the optional-extras registry."""

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest

from chronicler.core import extras


class TestRegistry:
    def test_every_extra_declared_in_pyproject_is_registered(self):
        assert set(extras.EXTRAS) == {"transcription", "normalization", "llm", "recording"}

    def test_an_extra_knows_the_module_its_guard_imports(self):
        assert extras.get_extra("recording").module == "sounddevice"
        assert extras.get_extra("normalization").module == "av"
        assert extras.get_extra("transcription").module == "faster_whisper"
        assert extras.get_extra("llm").module == "llama_cpp"

    def test_an_unknown_extra_is_a_key_error_naming_it(self):
        with pytest.raises(KeyError, match="banjo"):
            extras.get_extra("banjo")

    def test_only_recording_needs_a_system_library(self):
        needing = {name for name, extra in extras.EXTRAS.items() if extra.system_packages}

        assert needing == {"recording"}
        assert extras.get_extra("recording").system_packages == ("libportaudio2",)


class TestAvailability:
    def test_it_agrees_with_a_real_import_attempt(self):
        try:
            importlib.import_module("av")
        except Exception:
            importable = False
        else:
            importable = True

        assert extras.is_available("normalization") is importable

    def test_an_import_error_means_unavailable(self):
        with patch.object(extras.importlib, "import_module", side_effect=ImportError("nope")):
            assert extras.is_available("recording") is False

    def test_a_module_that_loads_but_cannot_bind_is_also_unavailable(self):
        """
        sounddevice imports fine and then raises OSError looking for PortAudio, so a
        find_spec check would call it available. See docs/optional-extras.md.
        """
        with patch.object(extras.importlib, "import_module", side_effect=OSError("no PortAudio")):
            assert extras.is_available("recording") is False

    def test_availability_is_not_cached_between_calls(self):
        with patch.object(extras.importlib, "import_module", side_effect=ImportError):
            assert extras.is_available("recording") is False
        with patch.object(extras.importlib, "import_module", return_value=MagicMock()):
            assert extras.is_available("recording") is True


class TestMessages:
    def test_names_the_pip_extra(self):
        message = extras.missing_message("normalization")

        assert "chronicler[normalization]" in message

    def test_says_what_the_extra_is_for(self):
        assert "normali" in extras.missing_message("normalization").lower()

    def test_an_import_error_mentions_both_pip_and_the_system_package(self):
        message = extras.missing_message("recording", ImportError("no module"))

        assert "chronicler[recording]" in message
        assert "libportaudio2" in message

    def test_a_binding_failure_asks_only_for_the_system_package(self):
        message = extras.missing_message("recording", OSError("PortAudio library not found"))

        assert "libportaudio2" in message
        assert "pip install" not in message

    def test_a_binding_failure_for_an_extra_with_no_system_package_falls_back_to_pip(self):
        message = extras.missing_message("normalization", OSError("something odd"))

        assert "chronicler[normalization]" in message

    def test_the_download_size_is_offered_for_the_prompt(self):
        assert extras.download_estimate("normalization").endswith("MB")

    def test_transcription_warns_that_the_model_downloads_separately(self):
        assert "model" in extras.get_extra("transcription").note.lower()


class TestInstallability:
    def test_a_virtualenv_can_install(self):
        with (
            patch.object(sys, "prefix", "/somewhere/.venv"),
            patch.object(sys, "base_prefix", "/usr"),
        ):
            assert extras.can_install() is True

    def test_a_system_python_with_a_read_only_site_packages_cannot(self):
        with patch.object(sys, "prefix", "/usr"), patch.object(sys, "base_prefix", "/usr"):
            with patch.object(extras.os, "access", return_value=False):
                assert extras.can_install() is False

    def test_a_writable_user_install_can(self):
        with patch.object(sys, "prefix", "/usr"), patch.object(sys, "base_prefix", "/usr"):
            with patch.object(extras.os, "access", return_value=True):
                assert extras.can_install() is True


class TestInstallCommand:
    def test_runs_pip_through_the_running_interpreter(self):
        command = extras.install_command("recording")

        assert command[:4] == [sys.executable, "-m", "pip", "install"]

    def test_installs_the_requirement_rather_than_the_chronicler_extra(self):
        """
        Chronicler is not on PyPI, so `pip install chronicler[recording]` would fail on a
        checkout - see docs/optional-extras.md.
        """
        command = extras.install_command("recording")

        assert command[-1] == extras.get_extra("recording").requirement
        assert not any("chronicler" in part for part in command)


class TestInstall:
    def test_a_successful_run_rechecks_the_import(self):
        with patch.object(extras.subprocess, "run") as run:
            run.return_value = MagicMock(returncode=0, stdout="Successfully installed", stderr="")
            with patch.object(extras, "is_available", return_value=True):
                result = extras.install("recording")

        assert result.ok is True

    def test_pip_succeeding_but_the_import_still_failing_is_not_a_success(self):
        """The PortAudio case: pip is happy, the module still cannot bind."""
        with patch.object(extras.subprocess, "run") as run:
            run.return_value = MagicMock(returncode=0, stdout="Successfully installed", stderr="")
            with patch.object(extras, "is_available", return_value=False):
                result = extras.install("recording")

        assert result.ok is False
        assert "libportaudio2" in result.output

    def test_a_failed_run_reports_pips_own_output(self):
        with patch.object(extras.subprocess, "run") as run:
            run.return_value = MagicMock(returncode=1, stdout="", stderr="No matching distribution")
            result = extras.install("recording")

        assert result.ok is False
        assert "No matching distribution" in result.output

    def test_pip_missing_entirely_is_reported_not_raised(self):
        with patch.object(extras.subprocess, "run", side_effect=OSError("no pip")):
            result = extras.install("recording")

        assert result.ok is False
        assert "no pip" in result.output

    def test_the_import_caches_are_invalidated_so_a_fresh_install_is_visible(self):
        with patch.object(extras.subprocess, "run") as run:
            run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            with patch.object(extras.importlib, "invalidate_caches") as invalidate:
                with patch.object(extras, "is_available", return_value=True):
                    extras.install("recording")

        invalidate.assert_called_once()


class TestPackagedBuilds:
    """
    A PyInstaller build has no pip, `sys.prefix` and `sys.base_prefix` are both the
    extraction directory, and `sys.executable` is Chronicler itself - so the install path
    cannot work there and must not be offered. See docs/optional-extras.md.
    """

    def test_a_frozen_build_cannot_install(self, monkeypatch):
        monkeypatch.setattr(extras.sys, "frozen", True, raising=False)

        assert extras.can_install() is False

    def test_a_frozen_build_is_recognised(self, monkeypatch):
        monkeypatch.setattr(extras.sys, "frozen", True, raising=False)

        assert extras.is_frozen() is True

    def test_a_normal_interpreter_is_not_frozen(self):
        assert extras.is_frozen() is False

    def test_the_message_does_not_name_a_pip_command_that_cannot_be_run(self, monkeypatch):
        monkeypatch.setattr(extras.sys, "frozen", True, raising=False)

        message = extras.missing_message("transcription")

        assert "pip" not in message
        assert "this build" in message

    def test_a_missing_system_library_is_still_reported_as_itself(self, monkeypatch):
        """That one is true whether or not the build is packaged, and is actionable."""
        monkeypatch.setattr(extras.sys, "frozen", True, raising=False)

        message = extras.missing_message("recording", OSError("PortAudio library not found"))

        assert "libportaudio2" in message


class TestUsability:
    def test_an_installed_extra_is_usable(self, monkeypatch):
        monkeypatch.setattr(extras, "is_available", lambda name: True)
        monkeypatch.setattr(extras, "can_install", lambda: False)

        assert extras.is_usable("recording") is True

    def test_a_missing_extra_that_can_be_installed_is_usable(self, monkeypatch):
        """A source checkout is one prompt away from having it."""
        monkeypatch.setattr(extras, "is_available", lambda name: False)
        monkeypatch.setattr(extras, "can_install", lambda: True)

        assert extras.is_usable("recording") is True

    def test_a_missing_extra_in_a_packaged_build_is_not(self, monkeypatch):
        monkeypatch.setattr(extras, "is_available", lambda name: False)
        monkeypatch.setattr(extras, "can_install", lambda: False)

        assert extras.is_usable("recording") is False
