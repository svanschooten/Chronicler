# Optional extras

`chronicler/core/extras.py`, `chronicler/desktop/extras_prompt.py`

Four features need dependencies too large to ship with the base install. Each is a
`[project.optional-dependencies]` group in `pyproject.toml` and an entry in `EXTRAS`:

| Extra | Module | Feature | Download |
| ----- | ------ | ------- | -------- |
| `transcription` | `faster_whisper` | Whisper transcription | ~120 MB |
| `normalization` | `av` | Loudness normalisation | ~35 MB |
| `llm` | `llama_cpp` | Local `.gguf` summarisation | ~30 MB |
| `recording` | `sounddevice` | Recording from a microphone | ~1 MB |

## One registry, not four hand-written strings

Before this existed, each of the four call sites wrote its own "install the extra"
message. They drifted, and the desktop had no way to know *which* extra had failed —
it could only print whatever string it was handed.

`EXTRAS` is now the single source: the module a guard imports, the pip requirement, what
the feature is for, roughly how big the download is, and any system package pip cannot
supply. Every guard asks `missing_message()`; the desktop asks `is_available()`.

## `is_available()` imports, it does not look

A `find_spec` check is not good enough. `sounddevice` is 32 kB of pure Python — a CFFI
binding to PortAudio that the operating system has to provide. With the module installed
and PortAudio absent, `find_spec` succeeds and the import then raises `OSError`. So
availability means *the import actually completed*, and the result is not cached: an
install during the session has to become visible without a restart.

That distinction is why `missing_message()` takes the exception. An `ImportError` means
pip can fix it. Anything else, for an extra with `system_packages`, means the Python
package is there and its library is not — a different problem with a different answer.

## A release ships them; a checkout installs them

Since the binaries started being built with the extras installed, a packaged Chronicler
transcribes, normalises and records out of the box. The release workflow installs
`.[transcription,normalization,recording]` before PyInstaller runs, and PyInstaller
collects what it finds — the imports are inside functions, which its analysis follows.
This is not free: the Linux binary goes from roughly 57 MB to roughly 170 MB.

The Linux job also installs `libportaudio2` first. `sounddevice`'s Linux wheel contains
no PortAudio — it binds to the system library, and PyInstaller's hook copies whatever
`ctypes.util.find_library` turns up. Without it the hook logs a warning and the packaged
build cannot record. The Windows wheel ships its own DLL and needs nothing.

`llm` is deliberately left out. `llama-cpp-python` is large and CPU-feature specific, and
the OpenAI-compatible path — which is how most people reach a model — needs nothing at
all. A local `.gguf` therefore still means a source install.

### Nothing can be installed from a packaged build

`can_install()` returns False whenever `sys.frozen` is set, and that is not a policy
choice:

* there is no pip in the bundle;
* `sys.prefix` and `sys.base_prefix` are both the extraction directory, so the virtualenv
  check cannot pass, and the `site-packages` it names does not exist;
* `sys.executable` is **Chronicler**, so `sys.executable -m pip install …` would relaunch
  the app with arguments argparse rejects rather than install anything.

So `missing_message()` does not name a pip command in a packaged build. It says the
feature is not included in this build, which is the whole truth there.

## Buttons that go quiet rather than wrong

Nothing prompts for an install it cannot perform, and nothing queues work that is certain
to fail.

| Feature | Asks | Disabled when |
| ------- | ---- | ------------- |
| Record | the **local** extras, via `is_usable("recording")` | missing and not installable |
| Transcribe | the service layer's `capabilities` | `transcribe` absent |
| Normalize | the service layer's `capabilities` | `normalize` absent |
| Summarize | the service layer's `capabilities` | `summarize` absent |

`is_usable()` is `is_available() or can_install()`: a source checkout missing an extra is
one prompt away from having it, so the button stays live and `ExtraInstaller` does its
job. A packaged build missing one is not, so the button greys out and its tooltip says
so. The install prompt that used to appear and then fail is gone.

Recording asks locally on purpose — the microphone is on the machine running the UI in
every deployment mode. Transcription and normalisation run in the worker, which is the
server in thin-client mode, so those ask the server. Unknown capabilities mean "assume it
works": a handshake that has not landed yet should not grey out half the interface.

## Installing on demand

`ExtraInstaller.ensure(page, name)` returns True when the extra is usable by the time it
returns:

1. Already importable → True, no dialog.
2. Not installable here → the message, and False. `can_install()` is true inside a
   virtualenv, or when `site-packages` is writable; a read-only system Python gets
   instructions instead of a button that would fail.
3. `extras.auto_install` set → install, with a notification saying so.
4. Otherwise → confirm first. The dialog names the requirement and its size, and offers
   **Install optional components without asking**, which writes `extras.auto_install`
   to the config file so the question is not asked again.

A download is never started without either a confirmation or a setting that waived it.

### The install command

`install_command()` installs the *requirement* (`sounddevice>=0.4,<1`), not
`chronicler[recording]`. Chronicler is not published to an index, so resolving itself
would fail on a checkout. The user-facing message still names the extra, because that is
what a person types when installing by hand from the repository:

```bash
pip install '.[recording]'
```

pip runs through `sys.executable -m pip`, never a bare `pip`, so it installs into the
interpreter that is running rather than whatever is first on `PATH`.

### pip succeeding is not the same as the extra working

After a successful pip run, `install()` re-checks the import. If it still fails, the
result is *not* ok, and the output is the system-library message. That is the PortAudio
case: pip is entirely happy and recording still cannot start.

## What is not translated

The registry's messages are English, and deliberately not in the message catalogue.
They are made of package names, pip commands and apt commands, which do not translate;
the dialog *around* them — title, buttons, the remember checkbox — is translated
normally. See [i18n.md](i18n.md).

## Where the prompt belongs

Only recording prompts to install, and that is not an oversight.

Recording runs on the machine with the microphone, so a client-side install fixes it.
Transcription, normalisation and local summarisation run in the **worker**, which in
thin-client mode is on the server — installing something locally would change nothing
there. Those are reported the other way round: the server advertises what it can do via
`ServerInfo.capabilities` (see [deployment-and-rpc.md](deployment-and-rpc.md)) and the
buttons that need a missing capability explain themselves instead of queueing a task
that is certain to fail.

## What pip cannot do

`sounddevice` needs PortAudio from the system package manager:

```bash
sudo apt install libportaudio2
```

Chronicler will not run that for you. The message names it, and
[troubleshooting.md](troubleshooting.md) covers the case where both are installed and
there is still no input device — under WSL that needs WSLg's audio bridge.

## Testing

`tests/chronicler/core/test_extras.py` covers the registry, the message split between
pip and apt, `can_install()` in and out of a virtualenv, and the pip-succeeded-but-import-
still-fails path. `tests/chronicler/desktop/test_extras_prompt.py` covers the four
branches of `ensure()`.

Tests that decode real audio call `pytest.importorskip("av", exc_type=ImportError)`, so
the suite passes with and without the extras installed — see [testing.md](testing.md).
