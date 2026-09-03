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

    def set(self, path: str, value: Any) -> None:
        """Validates `value` against the whole section before keeping it."""
        owner, field = self._resolve(path)

        if self._is_list_field(owner, field) and isinstance(value, str):
            value = [item.strip() for item in value.split(LIST_SEPARATOR) if item.strip()]
        elif isinstance(value, str):
            cleaned = value.strip()
            if field == "language" and cleaned == AUTO_LANGUAGE:
                cleaned = ""
            if not cleaned and self._allows_none(owner, field):
                value = None
            else:
                value = cleaned

        candidate = owner.model_dump()
        candidate[field] = value
        try:
            validated = type(owner)(**candidate)
        except ValidationError as error:
            raise ValueError(self._first_message(error)) from error

        setattr(owner, field, getattr(validated, field))

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
