"""Locale-aware message lookup over nested message maps."""

import string
from typing import Any

MessageMap = dict[str, Any]

DEFAULT_LOCALE = "en"

_FORMATTER = string.Formatter()


class _Forgiving(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


class Translator:
    """Resolves dotted message paths against a locale, falling back to English."""

    def __init__(self, messages: dict[str, MessageMap], locale: str = DEFAULT_LOCALE):
        self._messages = messages
        self._locale = DEFAULT_LOCALE
        self.locale = locale

    @property
    def locale(self) -> str:
        return self._locale

    @locale.setter
    def locale(self, value: str) -> None:
        self._locale = (value or DEFAULT_LOCALE).strip().lower()

    def available_locales(self) -> list[str]:
        return sorted(self._messages)

    def _candidates(self) -> list[str]:
        chain = [self._locale]
        if "-" in self._locale:
            chain.append(self._locale.split("-", 1)[0])
        chain.append(DEFAULT_LOCALE)
        seen: list[str] = []
        for locale in chain:
            if locale not in seen and locale in self._messages:
                seen.append(locale)
        return seen

    def _lookup(self, locale: str, key: str) -> str | None:
        node: Any = self._messages[locale]
        for part in key.split("."):
            if not isinstance(node, dict) or part not in node:
                return None
            node = node[part]
        return node if isinstance(node, str) else None

    def t(self, key: str, **params: Any) -> str:
        for locale in self._candidates():
            template = self._lookup(locale, key)
            if template is not None:
                return _FORMATTER.vformat(template, (), _Forgiving(params))
        return key
