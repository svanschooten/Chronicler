# Troubleshooting

## The file dialog does nothing, or reports a socket error

Symptom, on Linux or WSL:

```text
SocketException: Connection failed (OS Error: No such file or directory, errno = 2),
address = /run/user/1000/bus
```

File dialogs go through the **XDG desktop portal**, which is reached over the session
D-Bus at `$XDG_RUNTIME_DIR/bus`. The error means that socket does not exist.

Check whether the runtime directory exists at all:

```bash
ls -la /run/user/$(id -u)
```

If it is missing while `XDG_RUNTIME_DIR` is still set, your login never registered a
systemd session, so `pam_systemd` never created it. This is the normal state in WSL,
because `wsl.exe` does not go through PAM login. Confirm with:

```bash
loginctl list-sessions
```

If that lists no session for your user — or only a root one — the fix is to let systemd
start your user manager independently of logins:

```bash
sudo loginctl enable-linger $USER
```

Then restart the WSL instance (`wsl --shutdown` from Windows) and check again. You should
see `/run/user/1000` owned by you, and `systemctl status user@1000.service` active.

`chown`-ing the directory is not the fix — it usually does not exist to be chowned, and
recreating it by hand is lost on the next boot and still leaves no bus running on it.

Chronicler detects this case and reports the fix rather than the raw errno; see
`describe_desktop_integration_error` in `chronicler/desktop/reveal.py`.

## The portal is missing entirely

```text
org.freedesktop.portal.Desktop was not provided by any .service files
```

The session bus is running but no portal is installed:

```bash
sudo apt install xdg-desktop-portal xdg-desktop-portal-gtk
```

## dconf warnings on startup

```text
dconf-CRITICAL: unable to create directory '/run/user/1000/dconf': Permission denied
```

Same root cause as above, and harmless on its own — GTK falls back to defaults. It stops
once the runtime directory exists.

## A chronicle fails to open with "table already exists"

A project database was migrated by a build that ran Alembic concurrently. See
[storage.md](storage.md#migrations-are-serialised-process-wide) for why, and for how to
recover the affected `project.db`.

## Recording says the extra is missing after installing it

`sounddevice` is a binding to PortAudio, not a bundle of it. The wheel is 32 kB of pure
Python with no binaries inside, so pip installing it is only half the job on Linux:

```bash
sudo apt install libportaudio2
```

The message tells the two apart. "requires the 'recording' extra" means the Python
package is missing; "needs the system library libportaudio2" means it is installed and
the library it binds to is not.

## Recording finds no input devices

Both libraries present and the device list empty means PortAudio started and found
nothing to capture with. Under WSL2, audio input arrives through WSLg's PulseAudio
bridge; without it there is no microphone to enumerate, however well the libraries are
installed.

This is reported rather than fixed — Chronicler cannot conjure a capture device — but it
is reported as itself instead of as an empty dropdown.

## A missing optional component is not offered for install

The install prompt only appears when `extras.can_install()` is true: inside a virtualenv,
or when `site-packages` is writable. A read-only system Python gets the pip command to
run by hand instead of a button that would fail. See [optional-extras.md](optional-extras.md).

## Deleting a chronicle fails with WinError 32

```text
[WinError 32] The process cannot access the file because it is being used by
another process: '...\chronicles\<id>\project.db'
```

Something still had the project database open when the directory was removed. Chronicler
closes its own handle first — `delete_chronicle` disposes the chronicle's engine before
removing anything — so if this still appears, the file is held by something else: a
sqlite browser left open on it, a sync client, or a virus scanner mid-scan. The removal
is retried for about a second before it gives up, and the failure is reported in the app
rather than crashing it. The chronicle is gone from the archive either way; the folder is
safe to delete by hand afterwards.

Linux never showed this, because unlinking a file that is still open is allowed there.
See [storage.md](storage.md).

## "greenlet is being finalized" when closing the app

```text
ERROR sqlalchemy.pool - Exception terminating connection
  RuntimeError: greenlet is being finalized
SAWarning: The garbage collector is trying to clean up non-checked-in connection
```

This means a database session was still open when the process exited, so the garbage
collector terminated its pooled connection during interpreter finalisation - by which
point the greenlet machinery aiosqlite runs on is already gone. The error is a symptom of
the leak, not of anything going wrong with the data: every write commits explicitly, and
the leaked session was doing a read.

The cause was `DesktopApp.refresh_models` resolving `SystemService` off the **root**
container instead of a scope. `Container.resolve` caches, so the `AsyncSession` its
repository needed was cached there for the life of the process - with a read transaction
open, and nothing in `cleanup` to close it.

Two rules came out of it, both now enforced by tests in
`tests/chronicler/desktop/test_app.py`:

* **Resolve through a scope, always.** The root container holds things meant to live for
  the app's lifetime; a session is not one of them. See
  [dependency-injection.md](dependency-injection.md).
* **Check what a scope built, do not resolve it.** `Container.cached()` exists because
  asking `resolve` whether a session exists would *create* one to answer, and that one
  would then leak instead.

`WorkerManager.stop()` only asks the loop to finish its current sleep, so `cleanup` now
also holds the task handle and cancels it rather than leaving it to outlive the shutdown.
