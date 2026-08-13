from chronicler.desktop.theme import theme_colors


def test_dark_and_light_produce_different_surfaces():
    dark = theme_colors(True)
    light = theme_colors(False)

    assert dark != light
    assert dark.surface != light.surface
    assert dark.text != light.text
    assert dark.accent != light.accent
    assert dark.sidebar != light.sidebar


def test_theme_colors_is_deterministic():
    assert theme_colors(True) == theme_colors(True)
    assert theme_colors(False) == theme_colors(False)
