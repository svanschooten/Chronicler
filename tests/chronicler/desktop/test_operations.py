"""Tests for the chronicle-level operations shared by the archive and the chronicle view."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import flet as ft
import pytest

from chronicler.core.models import Chronicle
from chronicler.desktop.operations import ChronicleOperations


@pytest.fixture
def make_operations():
    def _make(**overrides):
        parts = {
            "imports": AsyncMock(),
            "task_service": AsyncMock(),
            "transcript_service": AsyncMock(),
            "chronicle_service": AsyncMock(),
            "picker": AsyncMock(),
            "show_snackbar": MagicMock(),
        }
        parts.update(overrides)
        page = MagicMock(spec=ft.Page)
        page.overlay = []
        operations = ChronicleOperations(
            parts["imports"],
            parts["task_service"],
            parts["transcript_service"],
            parts["chronicle_service"],
            parts["picker"],
            parts["show_snackbar"],
            lambda: page,
        )
        return operations, parts, page

    return _make


def _chronicle(**overrides):
    overrides.setdefault("title", "Session One")
    return Chronicle(id=uuid4(), **overrides)


class TestCleaning:
    @pytest.mark.asyncio
    async def test_confirming_queues_a_clean_task_for_that_chronicle(self, make_operations):
        operations, parts, _ = make_operations()
        chronicle = _chronicle()

        with patch("chronicler.desktop.operations.confirm", new=AsyncMock(return_value=True)):
            assert await operations.clean(chronicle) is True

        parts["task_service"].queue_clean.assert_awaited_once_with(chronicle.id)
        parts["show_snackbar"].assert_called_once()

    @pytest.mark.asyncio
    async def test_cancelling_queues_nothing(self, make_operations):
        operations, parts, _ = make_operations()

        with patch(
            "chronicler.desktop.operations.confirm", new=AsyncMock(return_value=False)
        ) as ask:
            assert await operations.clean(_chronicle()) is False

        ask.assert_awaited_once()
        parts["task_service"].queue_clean.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_confirmation_names_the_chronicle(self, make_operations):
        operations, _, _ = make_operations()

        with patch(
            "chronicler.desktop.operations.confirm", new=AsyncMock(return_value=False)
        ) as ask:
            await operations.clean(_chronicle(title="Emberfall 14"))

        _page, _title, message = ask.await_args.args
        assert "Emberfall 14" in message


class TestIdentifyingSpeakers:
    @pytest.mark.asyncio
    async def test_it_refreshes_the_count_and_reports_it(self, make_operations):
        operations, parts, _ = make_operations()
        parts["transcript_service"].refresh_speaker_count.return_value = 3
        chronicle = _chronicle()

        assert await operations.identify_speakers(chronicle) is True

        parts["transcript_service"].refresh_speaker_count.assert_awaited_once_with(chronicle.id)
        assert "3" in parts["show_snackbar"].call_args[0][0]


class TestImportingAudio:
    @pytest.mark.asyncio
    async def test_it_imports_the_picked_file_into_that_chronicle(self, make_operations):
        operations, parts, _ = make_operations()
        parts["picker"].pick_file.return_value = "/audio/alice.mp3"
        parts["imports"].import_audio.return_value = "Added alice.mp3"
        chronicle = _chronicle()

        assert await operations.import_audio(chronicle) is True

        parts["imports"].import_audio.assert_awaited_once_with(chronicle.id, "/audio/alice.mp3")
        parts["show_snackbar"].assert_called_once_with("Added alice.mp3")

    @pytest.mark.asyncio
    async def test_it_only_offers_audio_extensions(self, make_operations):
        operations, parts, _ = make_operations()
        parts["picker"].pick_file.return_value = None

        await operations.import_audio(_chronicle())

        assert "mp3" in parts["picker"].pick_file.await_args[0][0]

    @pytest.mark.asyncio
    async def test_cancelling_changes_nothing(self, make_operations):
        operations, parts, _ = make_operations()
        parts["picker"].pick_file.return_value = None

        assert await operations.import_audio(_chronicle()) is False

        parts["imports"].import_audio.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_failure_is_reported_rather_than_raised(self, make_operations):
        operations, parts, _ = make_operations()
        parts["picker"].pick_file.return_value = "/audio/alice.mp3"
        parts["imports"].import_audio.side_effect = RuntimeError("disk full")

        assert await operations.import_audio(_chronicle()) is True

        assert "disk full" in parts["show_snackbar"].call_args[0][0]

    @pytest.mark.asyncio
    async def test_importing_without_a_chronicle_creates_one(self, make_operations):
        """The archive header's Import menu has no chronicle to import into yet."""
        operations, parts, _ = make_operations()
        parts["picker"].pick_file.return_value = "/audio/alice.mp3"
        parts["imports"].import_audio.return_value = "Created 'alice' and added audio source"

        assert await operations.import_audio(None) is True

        assert parts["imports"].import_audio.await_args[0][0] is None


class TestImportingATranscript:
    @pytest.mark.asyncio
    async def test_the_options_form_opens_first(self, make_operations):
        operations, _, page = make_operations()

        await operations.begin_transcript_import(_chronicle())

        assert operations.transcript_form.dialog.open is True
        page.update.assert_called()

    @pytest.mark.asyncio
    async def test_confirming_picks_a_file_and_imports_into_the_remembered_chronicle(
        self, make_operations
    ):
        operations, parts, _ = make_operations()
        parts["picker"].pick_file.return_value = "/t/session.txt"
        parts["imports"].import_transcript.return_value = "Queued"
        chronicle = _chronicle()

        await operations.begin_transcript_import(chronicle)
        assert await operations.finish_transcript_import() is True

        call = parts["imports"].import_transcript.await_args
        assert call[0][0] == chronicle.id
        assert call[0][1] == "/t/session.txt"

    @pytest.mark.asyncio
    async def test_only_txt_files_are_offered(self, make_operations):
        operations, parts, _ = make_operations()
        parts["picker"].pick_file.return_value = None

        await operations.begin_transcript_import(_chronicle())
        await operations.finish_transcript_import()

        assert parts["picker"].pick_file.await_args[0][0] == ["txt"]

    @pytest.mark.asyncio
    async def test_cancelling_the_picker_imports_nothing(self, make_operations):
        operations, parts, _ = make_operations()
        parts["picker"].pick_file.return_value = None

        await operations.begin_transcript_import(_chronicle())

        assert await operations.finish_transcript_import() is False
        parts["imports"].import_transcript.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_the_form_closes_before_the_picker_opens(self, make_operations):
        """Two native dialogs stacked on each other is what this ordering avoids."""
        operations, parts, _ = make_operations()
        parts["picker"].pick_file.return_value = None

        await operations.begin_transcript_import(_chronicle())
        await operations.finish_transcript_import()

        assert operations.transcript_form.dialog.open is False


class TestEditing:
    @pytest.mark.asyncio
    async def test_the_form_opens_filled_from_the_chronicle(self, make_operations):
        operations, _, _ = make_operations()
        chronicle = _chronicle(title="Session One", description="A first meeting")

        await operations.begin_edit(chronicle)

        assert operations.edit_form.title_field.value == "Session One"
        assert operations.edit_form.description_field.value == "A first meeting"
        assert operations.edit_form.dialog.open is True

    @pytest.mark.asyncio
    async def test_saving_writes_the_edits_back(self, make_operations):
        operations, parts, _ = make_operations()
        chronicle = _chronicle()
        parts["chronicle_service"].get_chronicle.return_value = chronicle

        await operations.begin_edit(chronicle)
        operations.edit_form.title_field.value = "Session One, cleaned"

        assert await operations.finish_edit() is True
        parts["chronicle_service"].edit_chronicle.assert_awaited_once_with(
            chronicle.id, title="Session One, cleaned"
        )

    @pytest.mark.asyncio
    async def test_a_duration_the_form_never_saw_is_not_written_over(self, make_operations):
        """Ticket 075: a task sets the duration while the dialog is open."""
        operations, parts, _ = make_operations()
        opened_with = _chronicle(duration=None)
        parts["chronicle_service"].get_chronicle.return_value = _chronicle(duration="1h 24m")

        await operations.begin_edit(opened_with)
        operations.edit_form.title_field.value = "Renamed"
        await operations.finish_edit()

        sent = parts["chronicle_service"].edit_chronicle.await_args.kwargs
        assert "duration" not in sent

    @pytest.mark.asyncio
    async def test_saving_with_nothing_changed_sends_nothing(self, make_operations):
        operations, parts, _ = make_operations()
        chronicle = _chronicle()
        parts["chronicle_service"].get_chronicle.return_value = chronicle

        await operations.begin_edit(chronicle)
        await operations.finish_edit()

        parts["chronicle_service"].edit_chronicle.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_chronicle_that_vanished_is_reported_not_crashed(self, make_operations):
        operations, parts, _ = make_operations()
        parts["chronicle_service"].get_chronicle.return_value = None

        await operations.begin_edit(_chronicle())

        assert await operations.finish_edit() is True
        parts["chronicle_service"].edit_chronicle.assert_not_awaited()
        parts["show_snackbar"].assert_called_once()


class TestDeleting:
    @pytest.mark.asyncio
    async def test_it_confirms_first(self, make_operations):
        operations, parts, _ = make_operations()

        with patch(
            "chronicler.desktop.operations.confirm", new=AsyncMock(return_value=False)
        ) as ask:
            assert await operations.delete(_chronicle()) is False

        ask.assert_awaited_once()
        parts["chronicle_service"].delete_chronicle.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_confirming_deletes(self, make_operations):
        operations, parts, _ = make_operations()
        chronicle = _chronicle()

        with patch("chronicler.desktop.operations.confirm", new=AsyncMock(return_value=True)):
            assert await operations.delete(chronicle) is True

        parts["chronicle_service"].delete_chronicle.assert_awaited_once_with(chronicle.id)

    @pytest.mark.asyncio
    async def test_the_confirmation_names_the_chronicle(self, make_operations):
        operations, _, _ = make_operations()
        chronicle = _chronicle(title="Emberfall 14")

        with patch(
            "chronicler.desktop.operations.confirm", new=AsyncMock(return_value=False)
        ) as ask:
            await operations.delete(chronicle)

        assert "Emberfall 14" in " ".join(str(part) for part in ask.await_args[0])

    @pytest.mark.asyncio
    async def test_a_failed_delete_is_reported_rather_than_raised(self, make_operations):
        """A file Windows will not release must not reach Flet as an unhandled error."""
        operations, parts, _ = make_operations()
        parts["chronicle_service"].delete_chronicle.side_effect = OSError(
            32, "The process cannot access the file"
        )

        with patch("chronicler.desktop.operations.confirm", new=AsyncMock(return_value=True)):
            assert await operations.delete(_chronicle()) is True

        assert "cannot access the file" in parts["show_snackbar"].call_args[0][0]


class TestLinking:
    @pytest.mark.asyncio
    async def test_it_only_offers_project_databases(self, make_operations):
        operations, parts, _ = make_operations()
        parts["picker"].pick_file.return_value = None

        assert await operations.link_chronicle() is False
        assert parts["picker"].pick_file.await_args[0][0] == ["db"]

    @pytest.mark.asyncio
    async def test_it_registers_the_picked_database(self, make_operations):
        operations, parts, _ = make_operations()
        parts["picker"].pick_file.return_value = "/elsewhere/campaign/project.db"
        parts["imports"].link_chronicle.return_value = "Linked 'campaign'"

        assert await operations.link_chronicle() is True

        parts["imports"].link_chronicle.assert_awaited_once_with("/elsewhere/campaign/project.db")


class TestFormLifecycle:
    def test_both_forms_are_offered_for_attaching(self, make_operations):
        operations, _, _ = make_operations()

        assert operations.forms == [operations.edit_form, operations.transcript_form]


class TestFormDrivenReload:
    @pytest.mark.asyncio
    async def test_saving_an_edit_reloads_the_caller(self, make_operations):
        """
        The form's own Save button belongs to this object, not the view - so the reload
        has to be triggered from here or nothing repaints.
        """
        reload = AsyncMock()
        operations, parts, _ = make_operations()
        operations.on_changed = reload
        chronicle = _chronicle()
        parts["chronicle_service"].get_chronicle.return_value = chronicle

        await operations.begin_edit(chronicle)
        await operations._save_clicked(None)

        reload.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_confirmed_transcript_import_reloads_the_caller(self, make_operations):
        reload = AsyncMock()
        operations, parts, _ = make_operations()
        operations.on_changed = reload
        parts["picker"].pick_file.return_value = "/t/session.txt"

        await operations.begin_transcript_import(_chronicle())
        await operations._import_clicked(None)

        reload.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_a_cancelled_picker_does_not_reload(self, make_operations):
        reload = AsyncMock()
        operations, parts, _ = make_operations()
        operations.on_changed = reload
        parts["picker"].pick_file.return_value = None

        await operations.begin_transcript_import(_chronicle())
        await operations._import_clicked(None)

        reload.assert_not_awaited()


class TestRestoring:
    @staticmethod
    def _snapshot(kind="clean", name="before-clean-x.db"):
        from datetime import datetime

        from chronicler.core.models import Snapshot

        return Snapshot(
            name=name, kind=kind, created_at=datetime(2026, 11, 11, 21, 30), size_bytes=1
        )

    @pytest.mark.asyncio
    async def test_choosing_a_snapshot_restores_it(self, make_operations):
        operations, parts, _ = make_operations()
        parts["chronicle_service"].list_snapshots.return_value = [self._snapshot()]
        chronicle = _chronicle()

        with patch(
            "chronicler.desktop.operations.ask_choice",
            new=AsyncMock(return_value="before-clean-x.db"),
        ) as ask:
            assert await operations.restore(chronicle) is True

        parts["chronicle_service"].restore_snapshot.assert_awaited_once_with(
            chronicle.id, "before-clean-x.db"
        )
        offered = [choice.label for choice in ask.await_args.args[3]]
        assert any("Before cleaning" in label and "2026-11-11 21:30" in label for label in offered)

    @pytest.mark.asyncio
    async def test_cancelling_restores_nothing(self, make_operations):
        operations, parts, _ = make_operations()
        parts["chronicle_service"].list_snapshots.return_value = [self._snapshot()]

        with patch("chronicler.desktop.operations.ask_choice", new=AsyncMock(return_value=None)):
            assert await operations.restore(_chronicle()) is False

        parts["chronicle_service"].restore_snapshot.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_without_snapshots_it_says_so_and_asks_nothing(self, make_operations):
        operations, parts, _ = make_operations()
        parts["chronicle_service"].list_snapshots.return_value = []

        with patch("chronicler.desktop.operations.ask_choice", new=AsyncMock()) as ask:
            assert await operations.restore(_chronicle()) is False

        ask.assert_not_awaited()
        parts["show_snackbar"].assert_called_once()

    @pytest.mark.asyncio
    async def test_a_failed_restore_is_reported_not_raised(self, make_operations):
        operations, parts, _ = make_operations()
        parts["chronicle_service"].list_snapshots.return_value = [self._snapshot()]
        parts["chronicle_service"].restore_snapshot.side_effect = PermissionError("in use")

        with patch("chronicler.desktop.operations.ask_choice", new=AsyncMock(return_value="x.db")):
            assert await operations.restore(_chronicle()) is False

        assert "in use" in parts["show_snackbar"].call_args.args[0]
