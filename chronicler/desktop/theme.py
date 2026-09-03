from dataclasses import dataclass

import flet as ft


@dataclass(frozen=True)
class ThemeColors:
    """
    Shared surface/text palette so every desktop view reacts to Settings.dark_mode the same
    way, instead of each view hardcoding its own (usually dark-only) colors independently.
    """

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
            accent=ft.Colors.AMBER_300,
            sidebar=ft.Colors.BLUE_GREY_900,
        )
    return ThemeColors(
        surface=ft.Colors.WHITE,
        card=ft.Colors.WHITE,
        text=ft.Colors.BROWN_900,
        muted=ft.Colors.BROWN_500,
        border=ft.Colors.BROWN_200,
        accent=ft.Colors.AMBER_800,
        sidebar=ft.Colors.WHITE,
    )
