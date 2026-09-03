"""The per-chronicle card rendered in the archive list."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import flet as ft

from chronicler.core.models import Chronicle
from chronicler.desktop.theme import ThemeColors
from chronicler.i18n import t

Handler = Callable[[Any], Any]


@dataclass(frozen=True)
class ChronicleCardHandlers:
    """Every action a card can trigger."""

    on_open: Handler
    on_import_audio: Handler
    on_import_transcript: Handler
    on_edit: Handler
    on_clean: Handler
    on_identify_speakers: Handler
    on_delete: Handler


def chronicle_card(
    item: Chronicle,
    colors: ThemeColors,
    handlers: ChronicleCardHandlers,
) -> ft.Container:
    tags = " · ".join([tag.name for tag in item.tags]) if item.tags else t("archive.no_tags")
    return ft.Container(
        bgcolor=colors.card,
        padding=ft.Padding.all(18),
        border=ft.Border.all(1, colors.border),
        border_radius=12,
        on_click=handlers.on_open,
        data=item,
        content=ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Text(
                            (item.kind or t("common.unknown")).upper(),
                            size=12,
                            weight=ft.FontWeight.BOLD,
                            color=colors.muted,
                        ),
                        ft.Text(item.status or "Imported", size=12, color=colors.muted),
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
                ft.Text(item.title, size=18, weight=ft.FontWeight.BOLD, color=colors.text),
                ft.Text(
                    item.description or t("archive.no_description"),
                    max_lines=2,
                    color=colors.muted,
                ),
                ft.Row(
                    controls=[
                        ft.Text(item.created_at.strftime("%Y-%m-%d"), color=colors.muted),
                        ft.Text(item.duration or t("archive.unknown_duration"), color=colors.muted),
                        ft.Text(
                            t("archive.speakers", count=item.speakers_count), color=colors.muted
                        ),
                    ],
                    wrap=True,
                    spacing=10,
                ),
                ft.Text(tags, color=colors.muted),
                _action_row(item, colors, handlers),
            ],
        ),
    )


def _action_row(
    item: Chronicle,
    colors: ThemeColors,
    handlers: ChronicleCardHandlers,
) -> ft.Row:
    return ft.Row(
        controls=[
            ft.PopupMenuButton(
                icon=ft.Icons.UPLOAD_FILE,
                icon_color=colors.muted,
                items=[
                    ft.PopupMenuItem(
                        content=ft.Text(t("actions.import_audio")),
                        icon=ft.Icons.AUDIO_FILE,
                        data=item,
                        on_click=handlers.on_import_audio,
                    ),
                    ft.PopupMenuItem(
                        content=ft.Text(t("actions.import_transcript")),
                        icon=ft.Icons.DESCRIPTION,
                        data=item,
                        on_click=handlers.on_import_transcript,
                    ),
                ],
                tooltip=t("archive.import_into"),
            ),
            _icon_action(ft.Icons.EDIT, colors, item, handlers.on_edit, t("actions.edit")),
            _icon_action(
                ft.Icons.CLEANING_SERVICES, colors, item, handlers.on_clean, t("actions.clean")
            ),
            _icon_action(
                ft.Icons.RECORD_VOICE_OVER,
                colors,
                item,
                handlers.on_identify_speakers,
                t("actions.identify_speakers"),
            ),
            _icon_action(
                ft.Icons.DELETE_OUTLINE, colors, item, handlers.on_delete, t("actions.delete")
            ),
        ],
        alignment=ft.MainAxisAlignment.END,
    )


def _icon_action(
    icon: ft.IconData,
    colors: ThemeColors,
    data: Any,
    on_click: Handler,
    tooltip: str,
) -> ft.IconButton:
    """`data` is the whole Chronicle, which is what every operation takes."""
    return ft.IconButton(
        icon=icon,
        icon_color=colors.muted,
        data=data,
        on_click=on_click,
        tooltip=tooltip,
    )
