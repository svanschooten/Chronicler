# Configuration

`chronicler/core/config.py`, `chronicler/core/wizard.py`

Configuration is machine-specific: where the workspace is, which deployment mode this
install runs in, how to reach a remote server. It is deliberately separate from user
data, which lives in the workspace.

## Where the config file lives

`resolve_config_file()` returns the file Chronicler will actually read, searching in
priority order:

1. `~/.chronicler_config.yaml`
2. `<user config dir>/settings.yaml`
3. `<user config dir>/settings.json`

The `.json` entry is legacy and read-only. `Settings.save()` always writes YAML.

`_read_config` warns and falls back to defaults on a parse failure rather than raising.
A corrupt config should not make the app unstartable — the wizard can then fix it. It
names the offending file in the warning; this was once a bare `except: pass`, which
made a typo in the config indistinguishable from no config at all.

## `--config PATH` and `CHRONICLER_CONFIG_FILE`

Points Chronicler at one specific file, bypassing the search above. Use it to run an
isolated instance, a throwaway workspace, a smoke test, or a second workspace on one
machine. Before this existed, isolating an instance meant overriding `HOME` for the
whole process.

Two rules make it trustworthy:

* **An explicitly requested file that does not exist resolves to `None`**, not to the
  default search. `--config` is how a caller isolates an instance; quietly loading the
  developer's real config instead would defeat the point.
* **`save_path()` honours it even when the file does not exist yet.** A `--config` run
  that changes a setting must persist it where the caller asked.

`set_config_file_override()` communicates the choice through the environment rather
than as an argument, because `Settings` is constructed by pydantic-settings deep inside
`get_settings()`, which every entry point calls without any plumbing for it. Going
through the environment also means a spawned subprocess inherits the same config, which
is what you want for a worker. It must be called before the first `get_settings()` —
that result is `lru_cache`d, and the setter clears the cache.

## `FileConfigSettingsSource.get_field_value`

Vestigial. `__call__` is fully overridden and never calls it, but
`PydanticBaseSettingsSource` declares it `@abstractmethod`, so it must exist with a
matching signature. The parameter order matters: an earlier version declared
`(field_name, field)` against a supertype of `(field, field_name)`, which would have
misdirected the two values into each other's parameters had pydantic-settings ever
called it directly.

## `Settings.mode`

One of `server`, `client:web`, `desktop:full_stack`, `desktop:thin_client`, set by
`ConfigWizard` once it knows which of the four concrete setups was chosen.

It is recorded rather than re-derived because desktop's two sub-modes are not otherwise
distinguishable from settings alone — both can have `workspace_path` and `server_url`
set at once, for example after switching modes once.

`DesktopRuntime` infers the mode the way `desktop/main.py` used to for configs saved
before this field existed, rather than forcing a re-run of the wizard.

## Serialisation

`save()` round-trips through JSON before dumping YAML, so pydantic serialises `Path`
and enum values into plain YAML scalars rather than Python object tags.

## The two wizards

There are two, and which one runs depends on whether the mode being started has a
console to ask questions through.

| Mode | Wizard | Where |
| ---- | ------ | ----- |
| `client:desktop` | `FletSetupWizard` | `desktop/views/wizard.py`, on screen |
| `server`, `client:web` | `ConfigWizard` | `core/wizard.py`, on stdin |

The split exists because the packaged desktop build is windowless and has no stdin at
all — see [packaging.md](packaging.md). `__main__.main()` simply does not call
`run_wizard` for `client:desktop`; `desktop.main.start()` gates the Flet one on the same
`validate_for_mode()` check, inside the Flet session so it can draw.

Both write the same `Settings` fields, so a config produced by either is
indistinguishable. The Flet one covers only full stack and thin client — the two modes a
desktop window can actually run in — and asks for the language first, rebuilding every
step from `t()` so the rest of the wizard is in the language just chosen.

### The console wizard

`ConfigWizard` runs when no config exists, or when `validate_for_mode()` says the
existing one is incomplete for the mode being started. Each `WizardStep` reports
`is_satisfied()` so an already-configured step is skipped.

`RemoteServerStep` will not generate an API key, unlike `ApiKeyStep`. When setting up a
new server, generating a fresh key is correct. When connecting to someone else's
server, the key must match one the operator already configured — generating a random
one there would silently guarantee every request 403s. `FletSetupWizard.show_server()`
enforces the same rule by requiring both fields.

### The desktop wizard

It renders as page content rather than a dialog: until setup finishes it *is* the whole
screen, and a dialog would only add sizing and scroll constraints to work around.

`run()` returns an `asyncio.Future` that the final step resolves, so `desktop.main.start()`
can `await` it and treat the return as "config now exists" before building the runtime —
the same await-a-choice pattern `desktop/dialogs.py` uses.

Every step is rebuilt from `t()` rather than having its labels updated in place. That is
what lets the language step relabel the wizard around it the moment it is answered.

`apply_theme()` sets `page.theme_mode`. Material paints the dropdown, text fields and
buttons from that, not from the colours the wizard applies to its own containers — left
at its default the page follows the OS, so a dark workspace on a light desktop drew dark
text on the dark card.
