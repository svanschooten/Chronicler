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

Config files are read and written as UTF-8 on every platform. A file that is not valid
UTF-8 is read in the locale's encoding instead (an "ANSI" file from an older Windows
editor), and the next save rewrites it as UTF-8. `save()` writes a temp file beside the
config, syncs it, and swaps it in, so a crash cannot truncate it. A symlinked config is
written where the link points. If the existing file cannot be parsed, it is copied to
`<name>.bak`, readable by its owner only, before being replaced.

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

One `Mode` enum (`core/config.py`) names the three setups everywhere: `full_stack`,
`thin_client` and `server`. The wizards store it once they know which was chosen.

It is recorded rather than re-derived because desktop's two modes are not otherwise
distinguishable from settings alone — both can have `workspace_path` and `server_url`
set at once, for example after switching modes once.

Loading accepts what earlier versions saved: `desktop:full_stack` and
`desktop:thin_client` map to the new values, and `client:web` or any unknown value reads
as unset, with a warning.

Three members of `Settings` answer every mode question, so validation, `build_runtime`
and the Settings page cannot disagree:

| Member | Answers |
| ------ | ------- |
| `effective_mode` | The stored mode. Without one: thin client when there is a server URL and no workspace, else full stack |
| `desktop_mode` | `effective_mode`, with `server` read as full stack: a server's configuration opens its workspace locally |
| `validate_for_mode(mode)` | Whether the settings are complete for that mode: a workspace for full stack, a server URL and API key for thin client, a workspace and API key for server |

The command line takes `desktop` or `server`. `desktop` runs in `desktop_mode`.

## Serialisation

`save()` round-trips through JSON before dumping YAML, so pydantic serialises `Path`
and enum values into plain YAML scalars rather than Python object tags.

### Environment values are not saved

A setting that came from the environment (`CHRONICLER_API_KEY`,
`CHRONICLER_LLM__API_KEY`, ...) or from a `.env` file is left out of what `save()` writes.
The file keeps whatever value it already had for that setting, or none. A file value
equal to the environment's is dropped as well: that is a secret an earlier version leaked
into the file, and the environment still supplies it. Before this, the
first save after any change, even toggling dark mode, copied environment secrets into the
file in plain text.

The consequence: a setting the environment overrides cannot be changed from the app.
Unset the variable first.

The file is written with mode 600 on POSIX, because it can hold `api_key` and
`llm.api_key`. An existing file is restricted before anything is written to it.

## Desktop wizard and server setup

The desktop has a wizard; the server does not, because it often has no terminal either.

| Mode | Setup | Where |
| ---- | ----- | ----- |
| desktop | `FletSetupWizard` | `desktop/views/wizard.py`, on screen |
| `server` | `configure_server` | `core/wizard.py`, from flags or the environment |

The packaged desktop build is windowless and has no stdin at all - see
[packaging.md](packaging.md) - so `__main__.main()` never prompts for it, and
`desktop.main.start()` gates the Flet wizard on `validate_for_mode()` inside the Flet
session so it can draw. Both write the same `Settings` fields. The Flet one covers only full
stack and thin client, and asks for the language first, rebuilding every step from `t()`.

### Configuring the server

```bash
chronicler server --workspace /srv/chronicler --api-key "$KEY"
```

or, with the environment (what a container or a systemd unit would set):

```bash
CHRONICLER_WORKSPACE_PATH=/srv/chronicler CHRONICLER_API_KEY=... chronicler server
```

`configure_server` runs when a flag is given or the configuration is incomplete for server
mode. A flag wins over the saved value and is saved. A value that came from the environment
is used but not written to the file (see `Settings.save`). What is still missing is handled
by whether a terminal is attached:

- **Workspace:** asked for, with the default offered, if stdin is a terminal. Otherwise the
  server exits with a message naming `--workspace` and `CHRONICLER_WORKSPACE_PATH`.
- **API key:** generated if there is none, and printed once. A key you passed is not echoed.

An existing folder that cannot be written to is refused with the same kind of message. The
language is no longer asked on the server; set `ui.locale` in the file if it should differ.

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
