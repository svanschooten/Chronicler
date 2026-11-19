"""Tests for the shared native-file-dialog flow."""

from unittest.mock import AsyncMock, MagicMock

import flet as ft
import pytest

from chronicler.desktop.picking import FilePickerFlow, attach_picker, detach_picker


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


class TestRegistration:
    def test_attach_creates_and_registers_a_picker(self):
        page = MagicMock(services=[])

        picker = attach_picker(page, None)

        assert isinstance(picker, ft.FilePicker)
        assert page.services == [picker]

    def test_attaching_again_keeps_one_registration(self):
        page = MagicMock(services=[])
        picker = attach_picker(page, None)

        assert attach_picker(page, picker) is picker
        assert page.services == [picker]

    def test_detach_removes_only_its_own_picker(self):
        """Two new FilePickers compare equal, so this has to go by identity."""
        other = ft.FilePicker()
        page = MagicMock(services=[other])
        picker = attach_picker(page, None)

        detach_picker(page, picker)

        assert len(page.services) == 1
        assert page.services[0] is other

    def test_a_view_mounting_before_the_last_one_leaves_still_gets_its_picker(self):
        page = MagicMock(services=[])
        leaving = attach_picker(page, None)
        arriving = attach_picker(page, None)

        detach_picker(page, leaving)

        assert len(page.services) == 1
        assert page.services[0] is arriving

    def test_detaching_a_picker_never_attached_is_harmless(self):
        page = MagicMock(services=[])

        detach_picker(page, None)
        detach_picker(page, ft.FilePicker())

        assert page.services == []
