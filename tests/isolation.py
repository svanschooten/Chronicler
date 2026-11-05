"""Keeping tests away from the developer's real home and config directories."""


def isolate_home(monkeypatch, home):
    """
    Points the home and per-user config directories at `home`.

    Windows reads `USERPROFILE` rather than `HOME`, and platformdirs asks Windows for
    `AppData` directly, so setting `HOME` alone leaves the real directories in reach.
    """
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(
        "chronicler.core.config.user_config_dir", lambda app: str(home / "config" / app)
    )
