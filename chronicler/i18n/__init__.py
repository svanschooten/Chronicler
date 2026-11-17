"""Application message catalogue and the `t()` lookup used across the UI."""

from typing import Any

from chronicler.i18n.messages import MESSAGES
from chronicler.i18n.translator import DEFAULT_LOCALE, MessageMap, Translator

_translator = Translator(MESSAGES)


def t(key: str, **params: Any) -> str:
    """The message at `key` for the active locale, with `{named}` parameters filled in."""
    return _translator.t(key, **params)


def format_count(number: int) -> str:
    """
    A whole number with the active locale's thousands separator: "1,686" in English,
    "1.686" in Dutch and German, where a comma would read as a decimal point.
    """
    return f"{number:,}".replace(",", t("common.thousands_separator"))


def set_locale(locale: str) -> None:
    """Switches the locale every subsequent `t()` call resolves against."""
    _translator.locale = locale


def get_locale() -> str:
    return _translator.locale


def available_locales() -> list[str]:
    return _translator.available_locales()


__all__ = [
    "DEFAULT_LOCALE",
    "MESSAGES",
    "MessageMap",
    "Translator",
    "available_locales",
    "format_count",
    "get_locale",
    "set_locale",
    "t",
]
