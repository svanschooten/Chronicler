"""Every shipped message catalogue, keyed by locale."""

from chronicler.i18n.messages.de import MESSAGES as DE
from chronicler.i18n.messages.en import MESSAGES as EN
from chronicler.i18n.messages.nl import MESSAGES as NL

MESSAGES: dict[str, dict] = {"en": EN, "nl": NL, "de": DE}

__all__ = ["MESSAGES"]
