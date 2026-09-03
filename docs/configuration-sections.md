# Configuration sections

`chronicler/core/config_sections.py`

`Settings` carries five nested groups alongside its flat machine-level fields. Every
group has working defaults, so a config file that predates them — or no config file at
all — still loads.

| Section | Covers |
| ------- | ------ |
| `transcription` | Model size, language, silence threshold, normalise-first, device |
| `cleaning` | Which cleaning rules run and how — see [cleaning.md](cleaning.md) |
| `normalization` | Loudness targets in EBU R128 units |
| `llm` | Which language model backs summarisation and how to reach it |
| `ui` | Interface locale |

## In a config file

```yaml
transcription:
  language: nl
  model_size: small
  no_speech_threshold: 0.45
cleaning:
  hallucination_phrases:
    - "Ondertiteling door"
llm:
  provider: openai_compatible
  base_url: http://localhost:8080/v1
  model: qwen3
ui:
  locale: nl
```

A partial section keeps the rest of its defaults — writing only
`transcription.language` leaves `model_size` at `base`.

## From the environment

`env_nested_delimiter="__"`, so:

```bash
CHRONICLER_TRANSCRIPTION__LANGUAGE=nl
CHRONICLER_LLM__PROVIDER=openai_compatible
```

This is what makes the two-process thin-client test scriptable without editing files.

## An invalid section does not stop the app

A section that fails validation is dropped with a warning and its defaults are used
instead. This follows the same rule as a corrupt config file: a hand-edited
`no_speech_threshold: 99` should be ignorable and fixable, not a startup crash.

Note this applies to the **file** source. Values from the environment are validated
normally, since those come from whoever launched the process.

## `is_configured` rather than required fields

`LlmSettings` does not mark `base_url` required when the provider is
`openai_compatible`, because settings are edited incrementally — through the settings
panel, a field at a time — and a half-filled form should be saveable. `is_configured`
answers "can this actually be used yet", and callers check it before trying.

## `protected_namespaces`

`TranscriptionSettings.model_size` and `LlmSettings.model` / `model_path` collide with
Pydantic's reserved `model_` prefix, so both models set
`ConfigDict(protected_namespaces=())`. The names are the domain's own — Whisper model
size, LLM model name — and renaming them to satisfy the framework would be worse.
