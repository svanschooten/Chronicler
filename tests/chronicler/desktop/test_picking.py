"""Tests for the shared native-file-dialog flow."""

from unittest.mock import AsyncMock, MagicMock

import flet as ft
import pytest

from chronicler.desktop.picking import FilePickerFlow


def _flow(picker=None, snackbar=None):
    return FilePickerFlow(lambda: picker, snackbar or MagicMock())


def _picker(files=None, directory=None):
    picker = MagicMock(spec=ft.FilePicker)
    picker.pick_files = AsyncMock(return_value=files)
    picker.get_directory_path = AsyncMock(return_value=directory)
    return picker


class TestPickingAFile:
    @pytest.mark.asyncio
    async def test_returns_the_chosen_path(self):
        chosen = MagicMock()
        chosen.path = "/audio/alice.mp3"
        flow = _flow(_picker(files=[chosen]))

        assert await flow.pick_file() == "/audio/alice.mp3"

    @pytest.mark.asyncio
    async def test_cancelling_returns_none(self):
        flow = _flow(_picker(files=None))

        assert await flow.pick_file() is None

    @pytest.mark.asyncio
    async def test_an_empty_result_returns_none(self):
        flow = _flow(_picker(files=[]))

        assert await flow.pick_file() is None

    @pytest.mark.asyncio
    async def test_extensions_narrow_the_dialog(self):
        picker = _picker(files=None)
        flow = _flow(picker)

        await flow.pick_file(["mp3", "wav"])

        assert picker.pick_files.await_args.kwargs["allowed_extensions"] == ["mp3", "wav"]
        assert picker.pick_files.await_args.kwargs["file_type"] == ft.FilePickerFileType.CUSTOM

    @pytest.mark.asyncio
    async def test_no_extensions_allows_anything(self):
        picker = _picker(files=None)
        flow = _flow(picker)

        await flow.pick_file()

        assert picker.pick_files.await_args.kwargs["file_type"] == ft.FilePickerFileType.ANY


class TestPickingADirectory:
    @pytest.mark.asyncio
    async def test_returns_the_chosen_directory(self):
        flow = _flow(_picker(directory="/home/me/Chronicler"))

        assert await flow.pick_directory("Choose") == "/home/me/Chronicler"

    @pytest.mark.asyncio
    async def test_cancelling_returns_none(self):
        flow = _flow(_picker(directory=""))

        assert await flow.pick_directory("Choose") is None


class TestFailures:
    @pytest.mark.asyncio
    async def test_no_picker_at_all_is_reported(self):
        snackbar = MagicMock()
        flow = _flow(None, snackbar)

        assert await flow.pick_file() is None
        snackbar.assert_called_once()

    @pytest.mark.asyncio
    async def test_a_missing_session_bus_becomes_an_actionable_message(self):
        snackbar = MagicMock()
        picker = _picker()
        picker.pick_files = AsyncMock(
            side_effect=OSError("SocketException: connect failed /run/user/1000/bus")
        )
        flow = _flow(picker, snackbar)

        assert await flow.pick_file() is None
        assert "enable-linger" in snackbar.call_args[0][0]

    @pytest.mark.asyncio
    async def test_a_directory_dialog_failure_is_explained_the_same_way(self):
        snackbar = MagicMock()
        picker = _picker()
        picker.get_directory_path = AsyncMock(side_effect=OSError("/run/user/1000/bus missing"))
        flow = _flow(picker, snackbar)

        assert await flow.pick_directory("Choose") is None
        assert "enable-linger" in snackbar.call_args[0][0]
