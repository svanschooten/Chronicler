"""
The dialog that starts one transcription.

It is the only place a track's speaker is chosen, which is deliberate: the button that
opens it says "transcribe", so picking a speaker from somewhere else and having a
transcription start was the surprise this replaces. Saving just the speaker is still
possible, and now says so. See docs/transcription.md.
"""

import asyncio
import logging
from dataclasses import dataclass

import flet as ft

from chronicler.core.config import Settings
from chronicler.core.config_sections import AUTO_LANGUAGE, WHISPER_MODEL_SIZES, language_choices
from chronicler.core.models import AudioSource
from chronicler.i18n import available_locales, t

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TranscribeChoice:
    """What the user asked for. `transcribe` is False when only the speaker was saved."""

    speaker: str
    language: str
    model_size: str
    no_speech_threshold: float
    normalize_first: bool
    transcribe: bool


class TranscribeDialog:
    def __init__(self, source: AudioSource, speakers: list[str], settings: Settings):
        self.source = source
        self.speakers = speakers
        self.settings = settings
        defaults = settings.transcription

        self.speaker: ft.Dropdown | ft.TextField = (
            ft.Dropdown(
                label=t("transcribe.speaker"),
                data="speaker",
                value=source.speaker_name,
                options=[ft.DropdownOption(key=name, text=name) for name in self.speakers],
                editable=True,
                enable_filter=True,
            )
            if self.speakers
            else ft.TextField(
                label=t("transcribe.speaker"),
                data="speaker",
                value=source.speaker_name or "",
            )
        )
        self.language = ft.Dropdown(
            label=t("transcribe.language"),
            data="language",
            value=defaults.language or AUTO_LANGUAGE,
            options=[
                ft.DropdownOption(key=code, text=code)
                for code in language_choices(defaults, available_locales())
            ],
        )
        self.model_size = ft.Dropdown(
            label=t("transcribe.model"),
            data="model_size",
            value=defaults.model_size,
            options=[ft.DropdownOption(key=size, text=size) for size in WHISPER_MODEL_SIZES],
        )
        self.threshold = ft.TextField(
            label=t("transcribe.threshold"),
            data="no_speech_threshold",
            value=str(defaults.no_speech_threshold),
            width=140,
        )
        self.normalize = (
            None
            if source.is_normalized
            else ft.Checkbox(
                label=t("transcribe.normalize_first"),
                data="normalize_first",
                value=defaults.normalize_first,
            )
        )

    async def ask(self, page: ft.Page) -> TranscribeChoice | None:
        """
        The user's choice, or None if they cancelled.

        Written against a future directly rather than through `await_dialog`, because a
        rejected field has to leave the dialog open instead of resolving it.
        """
        future: asyncio.Future[TranscribeChoice | None] = asyncio.get_event_loop().create_future()

        def finish(value: TranscribeChoice | None) -> None:
            if not future.done():
                future.set_result(value)
            page.pop_dialog()

        async def cancel(_event):
            finish(None)

        async def save_speaker(_event):
            choice = self._collect(transcribe=False)
            if choice is not None:
                finish(choice)

        async def start(_event):
            choice = self._collect(transcribe=True)
            if choice is not None:
                finish(choice)

        page.show_dialog(
            ft.AlertDialog(
                title=ft.Text(t("transcribe.title", name=self.source.filename)),
                content=ft.Column(self._body(), tight=True, width=460),
                actions=[
                    ft.TextButton(t("common.cancel"), on_click=cancel),
                    ft.TextButton(t("transcribe.save_speaker"), on_click=save_speaker),
                    ft.FilledButton(self._start_label(), on_click=start),
                ],
            )
        )
        return await future

    def _body(self) -> list[ft.Control]:
        controls: list[ft.Control] = [
            ft.Text(t("transcribe.message"), size=12),
            self.speaker,
            self.language,
            self.model_size,
            self.threshold,
        ]
        if self.normalize is not None:
            controls.append(self.normalize)
        else:
            controls.append(ft.Text(t("transcribe.already_normalized"), size=11))
        return controls

    def _start_label(self) -> str:
        return t("transcribe.start_again") if self.source.is_transcribed else t("transcribe.start")

    def _collect(self, transcribe: bool) -> TranscribeChoice | None:
        """The filled-in values, or None when something is missing or unusable."""
        speaker = self._speaker_name()
        threshold = self._threshold()

        self._mark_speaker(None if speaker else t("transcribe.speaker_required"))
        self._refresh(self.speaker, self.threshold)
        if not speaker or threshold is None:
            return None

        return TranscribeChoice(
            speaker=speaker,
            language=self.language.value or AUTO_LANGUAGE,
            model_size=self.model_size.value or self.settings.transcription.model_size,
            no_speech_threshold=threshold,
            normalize_first=bool(self.normalize.value) if self.normalize is not None else False,
            transcribe=transcribe,
        )

    def _speaker_name(self) -> str:
        """
        The name the user typed or picked.

        An editable Dropdown keeps the two apart, and `text` is the one that tracks the
        field. `value` holds the option that was last *selected*, so typing over a speaker
        the track already remembers leaves `value` on the old name - reading it would
        quietly transcribe as the wrong person.

        `value` is still needed as the fallback, because `text` starts out unset: the
        client fills it in from the selected option only once the dialog has mounted, so
        between opening and that arriving `text` is None while `value` already holds the
        remembered name. Hence None (never reported) and "" (cleared on purpose) mean
        different things here and only the first one falls back.

        A TextField, used when there are no known speakers to pick from, has `value` alone
        and no such split.
        """
        typed = getattr(self.speaker, "text", None)
        if typed is not None:
            return typed.strip()
        return (self.speaker.value or "").strip()

    def _mark_speaker(self, message: str | None) -> None:
        """
        Puts a validation message on the speaker field, whichever control it turned out to be.

        Flet 0.86 spells this per control: a Dropdown carries `error_text`, a TextField
        carries `error`. Both are plain dataclasses and accept the other spelling without
        complaint, so writing the wrong one loses the message silently. See docs/desktop.md.
        """
        if isinstance(self.speaker, ft.Dropdown):
            self.speaker.error_text = message
        else:
            self.speaker.error = message

    def _threshold(self) -> float | None:
        """The typed threshold, or None with the field marked."""
        try:
            value = float((self.threshold.value or "").strip())
        except ValueError:
            self.threshold.error = t("transcribe.threshold_invalid")
            return None

        if not 0.0 <= value <= 1.0:
            self.threshold.error = t("transcribe.threshold_invalid")
            return None

        self.threshold.error = None
        return value

    @staticmethod
    def _refresh(*controls: ft.Control) -> None:
        for control in controls:
            try:
                control.update()
            except (RuntimeError, AssertionError):
                pass
