"""Applying and persisting settings changes, with no Flet dependency."""

from pathlib import Path
from typing import Any, get_args, get_origin

from pydantic import BaseModel, ValidationError

from chronicler.core.config import SECTION_MODELS, Settings
from chronicler.core.config_sections import AUTO_LANGUAGE

LIST_SEPARATOR = "\n"


class SettingsEditor:
    """Reads and writes dotted setting paths, validating before anything is kept."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def _resolve(self, path: str) -> tuple[BaseModel, str]:
        if "." not in path:
            if path not in type(self.settings).model_fields:
                raise KeyError(f"Unknown setting {path!r}")
            return self.settings, path

        section_name, field = path.split(".", 1)
        if section_name not in SECTION_MODELS:
            raise KeyError(f"Unknown settings section {section_name!r}")
        section = getattr(self.settings, section_name)
        if field not in type(section).model_fields:
            raise KeyError(f"Unknown setting {path!r}")
        return section, field

    @staticmethod
    def _is_list_field(owner: BaseModel, field: str) -> bool:
        annotation = type(owner).model_fields[field].annotation
        return get_origin(annotation) is list

    @staticmethod
    def _allows_none(owner: BaseModel, field: str) -> bool:
        annotation = type(owner).model_fields[field].annotation
        return type(None) in get_args(annotation)

    def get(self, path: str) -> Any:
        owner, field = self._resolve(path)
        return getattr(owner, field)

    def as_text(self, path: str) -> str:
        """The value rendered for a text field - lists become one item per line."""
        value = self.get(path)
        if isinstance(value, list):
            return LIST_SEPARATOR.join(str(item) for item in value)
        return "" if value is None else str(value)

    def get_language(self) -> str:
        return self.settings.transcription.language or AUTO_LANGUAGE

    def would_change(self, path: str, value: Any) -> bool:
        """
        Whether writing `value` would actually alter the setting.

        Compares coerced values rather than the raw text, so re-typing `0.60` over a
        stored `0.6`, or leaving a trailing blank line in a list, is correctly seen as
        no edit at all. A value that cannot be coerced counts as a change so that `set()`
        still runs and reports why.
        """
        try:
            owner, field = self._resolve(path)
            return getattr(owner, field) != self._coerce(owner, field, value)
        except (ValueError, KeyError, TypeError):
            return True

    def _coerce(self, owner: BaseModel, field: str, value: Any) -> Any:
        """`value` as the section would store it, without storing it."""
        prepared = self._prepare(owner, field, value)
        candidate = owner.model_dump()
        candidate[field] = prepared
        try:
            return getattr(type(owner)(**candidate), field)
        except ValidationError as error:
            raise ValueError(self._first_message(error)) from error

    def _prepare(self, owner: BaseModel, field: str, value: Any) -> Any:
        """Text from a form field turned into the shape the model expects."""
        if self._is_list_field(owner, field) and isinstance(value, str):
            return [item.strip() for item in value.split(LIST_SEPARATOR) if item.strip()]
        if isinstance(value, str):
            cleaned = value.strip()
            if field == "language" and cleaned == AUTO_LANGUAGE:
                cleaned = ""
            if not cleaned and self._allows_none(owner, field):
                return None
            return cleaned
        return value

    def set(self, path: str, value: Any) -> None:
        """Validates `value` against the whole section before keeping it."""
        owner, field = self._resolve(path)
        setattr(owner, field, self._coerce(owner, field, value))

    def restore_defaults(self, section_name: str) -> None:
        if section_name not in SECTION_MODELS:
            raise KeyError(f"Unknown settings section {section_name!r}")
        setattr(self.settings, section_name, SECTION_MODELS[section_name]())

    def save(self) -> Path:
        return self.settings.save()

    @staticmethod
    def _first_message(error: ValidationError) -> str:
        first = error.errors()[0]
        location = ".".join(str(part) for part in first["loc"]) or "value"
        return f"{location}: {first['msg']}"
