import ast
from pathlib import Path

import pytest

from chronicler.i18n import Translator, available_locales, set_locale, t
from chronicler.i18n.messages import MESSAGES

PACKAGE_ROOT = Path(__file__).resolve().parents[3] / "chronicler"


@pytest.fixture(autouse=True)
def reset_locale():
    yield
    set_locale("en")


def _flatten(mapping, prefix=""):
    for key, value in mapping.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            yield from _flatten(value, path)
        else:
            yield path, value


class TestLookup:
    def test_resolves_a_dotted_path(self):
        translator = Translator({"en": {"settings": {"title": "Settings"}}})

        assert translator.t("settings.title") == "Settings"

    def test_resolves_a_deeply_nested_path(self):
        translator = Translator({"en": {"a": {"b": {"c": "deep"}}}})

        assert translator.t("a.b.c") == "deep"

    def test_a_missing_key_returns_the_key_itself(self):
        translator = Translator({"en": {}})

        assert translator.t("settings.title") == "settings.title"

    def test_a_path_that_stops_at_a_branch_returns_the_key(self):
        translator = Translator({"en": {"settings": {"title": "Settings"}}})

        assert translator.t("settings") == "settings"

    def test_a_path_that_walks_through_a_leaf_returns_the_key(self):
        translator = Translator({"en": {"settings": {"title": "Settings"}}})

        assert translator.t("settings.title.extra") == "settings.title.extra"


class TestInterpolation:
    def test_named_parameters_are_substituted(self):
        translator = Translator({"en": {"tasks": {"queued": "Queued {name}"}}})

        assert translator.t("tasks.queued", name="track.wav") == "Queued track.wav"

    def test_a_missing_parameter_leaves_the_placeholder_rather_than_raising(self):
        translator = Translator({"en": {"tasks": {"queued": "Queued {name}"}}})

        assert translator.t("tasks.queued") == "Queued {name}"

    def test_unused_parameters_are_ignored(self):
        translator = Translator({"en": {"a": "plain"}})

        assert translator.t("a", unused=1) == "plain"


class TestFallback:
    def test_falls_back_to_english_for_an_untranslated_key(self):
        translator = Translator(
            {"en": {"a": "English", "b": "Only english"}, "nl": {"a": "Nederlands"}},
            locale="nl",
        )

        assert translator.t("a") == "Nederlands"
        assert translator.t("b") == "Only english"

    def test_an_unknown_locale_falls_back_to_english(self):
        translator = Translator({"en": {"a": "English"}}, locale="kl")

        assert translator.t("a") == "English"

    def test_a_regional_locale_falls_back_to_its_base_language(self):
        translator = Translator({"en": {"a": "English"}, "nl": {"a": "Nederlands"}}, locale="nl-be")

        assert translator.t("a") == "Nederlands"

    def test_switching_locale_changes_resolution(self):
        translator = Translator({"en": {"a": "English"}, "nl": {"a": "Nederlands"}})

        assert translator.t("a") == "English"
        translator.locale = "nl"
        assert translator.t("a") == "Nederlands"


class TestModuleLevelApi:
    def test_t_resolves_against_the_shipped_messages(self):
        assert t("app.name") == "Chronicler"

    def test_set_locale_switches_the_active_translator(self):
        english = t("nav.archive")
        set_locale("nl")

        assert t("nav.archive") != english

    def test_available_locales_reports_what_ships(self):
        assert "en" in available_locales()
        assert "nl" in available_locales()


class TestMessageCatalogueIntegrity:
    def test_english_is_the_complete_catalogue(self):
        assert "en" in MESSAGES
        assert dict(_flatten(MESSAGES["en"]))

    @pytest.mark.parametrize("locale", [loc for loc in MESSAGES if loc != "en"])
    def test_no_orphan_keys_in_a_translation(self, locale):
        english = set(dict(_flatten(MESSAGES["en"])))
        translated = set(dict(_flatten(MESSAGES[locale])))

        assert translated - english == set()

    @pytest.mark.parametrize("locale", list(MESSAGES))
    def test_every_leaf_is_a_string(self, locale):
        for key, value in _flatten(MESSAGES[locale]):
            assert isinstance(value, str), f"{locale}.{key} is not a string"

    @pytest.mark.parametrize("locale", [loc for loc in MESSAGES if loc != "en"])
    def test_placeholders_match_the_english_source(self, locale):
        import string

        def placeholders(text):
            return {f for _, f, _, _ in string.Formatter().parse(text) if f}

        english = dict(_flatten(MESSAGES["en"]))
        for key, value in _flatten(MESSAGES[locale]):
            assert placeholders(value) == placeholders(english[key]), key


class TestCallSitesResolve:
    def test_every_t_call_in_the_package_uses_a_key_that_exists(self):
        english = dict(_flatten(MESSAGES["en"]))
        missing = []

        for path in PACKAGE_ROOT.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                name = getattr(func, "id", None) or getattr(func, "attr", None)
                if name != "t" or not node.args:
                    continue
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    if first.value not in english:
                        missing.append(f"{path.name}:{node.lineno} {first.value}")

        assert missing == []
