from dataclasses import dataclass

import flet as ft


@dataclass(frozen=True)
class ThemeColors:
    """Shared surface/text palette so every desktop view reacts to
    Settings.dark_mode the same way, instead of each view hardcoding its own
    (usually dark-only) colors independently."""

    surface: str
    card: str
    text: str
    muted: str
    border: str
    accent: str
    sidebar: str


def theme_colors(dark_mode: bool) -> ThemeColors:
    if dark_mode:
        return ThemeColors(
            surface=ft.Colors.BLUE_GREY_800,
            card=ft.Colors.BLUE_GREY_700,
            text=ft.Colors.WHITE,
            muted=ft.Colors.BLUE_GREY_200,
            border=ft.Colors.BLUE_GREY_600,
            # AMBER_300 (bright) reads fine against a dark surface but disappears
            # against a light one - see ThemeColors.accent's light-mode value.
            accent=ft.Colors.AMBER_300,
            sidebar=ft.Colors.BLUE_GREY_900,
        )
    return ThemeColors(
        surface=ft.Colors.WHITE,
        card=ft.Colors.WHITE,
        text=ft.Colors.BROWN_900,
        muted=ft.Colors.BROWN_500,
        # AMBER_100 is a near-white pale yellow - practically invisible as a border
        # against a WHITE surface. BROWN_200 keeps the app's warm palette while
        # actually being visible.
        border=ft.Colors.BROWN_200,
        accent=ft.Colors.AMBER_800,
        # Same WHITE as `surface` - an AMBER_50 sidebar read as an odd yellow/brown
        # tint next to the rest of the (now pure white) light theme rather than a
        # deliberate accent.
        sidebar=ft.Colors.WHITE,
    )
