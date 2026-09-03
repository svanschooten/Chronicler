"""Application message catalogue and the `t()` lookup used across the UI."""

from typing import Any

from chronicler.i18n.messages import MESSAGES
from chronicler.i18n.translator import DEFAULT_LOCALE, MessageMap, Translator

_translator = Translator(MESSAGES)


def t(key: str, **params: Any) -> str:
    """The message at `key` for the active locale, with `{named}` parameters filled in."""
    return _translator.t(key, **params)


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
    "get_locale",
    "set_locale",
    "t",
]
