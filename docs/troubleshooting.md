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
