import argparse
import logging
import sys

logger = logging.getLogger(__name__)


def attach_windows_console() -> bool:
    """
    Reconnects a windowless Windows build to the terminal it was launched from.

    The packaged executable is built for the GUI subsystem so double-clicking it does not
    flash up a console (see Chronicler.spec). The cost is that it gets no console at all,
    not even the one it was started from, leaving `--help`, `chronicler server` and the
    console wizard with nowhere to write or read.

    AttachConsole borrows the parent's console when there is one. When there isn't - a
    double-click, or a detached service - it fails, and the caller carries on as a pure GUI
    app. Running from source is unaffected: the process already owns a console, so the
    call fails with ERROR_ACCESS_DENIED and the working streams are left alone.
    """
    if sys.platform != "win32":
        return False

    import ctypes

    attach_parent_process = -1
    if not ctypes.windll.kernel32.AttachConsole(attach_parent_process):
        return False

    for stream, device, mode in (
        ("stdin", "CONIN$", "r"),
        ("stdout", "CONOUT$", "w"),
        ("stderr", "CONOUT$", "w"),
    ):
        try:
            setattr(sys, stream, open(device, mode, buffering=1))
        except OSError:
            logger.debug(f"Could not reopen {stream} on the parent console", exc_info=True)
    return True


def main():
    """
    Parses the command line and starts the requested mode.

    Setup is split by where each mode can actually ask a question. Desktop collects its
    configuration on screen, in `desktop.views.wizard`, because the packaged build is
    windowless and has nothing for `input()` to read from. Server and web client keep the
    console wizard in `core.wizard`, since a terminal is where they are started anyway.
    See docs/configuration.md.
    """
    attach_windows_console()

    parser = argparse.ArgumentParser(prog="chronicler")
    parser.add_argument(
        "mode",
        nargs="?",
        default="desktop",
        choices=["desktop", "server", "web", "client:web", "client:desktop"],
        help="Run mode (default: %(default)s)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--host",
        help="Address to bind when running as a server or web client (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        help="Port to bind when running as a server or web client",
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        help=(
            "Read and write configuration at PATH instead of the default location. "
            "Useful for running an isolated instance or a second workspace on one machine."
        ),
    )

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )

    from chronicler.core.config import get_settings, is_config_initialized, set_config_file_override

    if args.config:
        set_config_file_override(args.config)

    mode_map = {
        "desktop": "client:desktop",
        "web": "client:web",
        "server": "server",
        "client:web": "client:web",
        "client:desktop": "client:desktop",
    }
    mode = mode_map.get(args.mode, args.mode)

    if mode != "client:desktop":
        from chronicler.core.wizard import run_wizard

        if not is_config_initialized() or not get_settings().validate_for_mode(mode):
            run_wizard(mode=mode)

    if mode == "server":
        server_main(host=args.host, port=args.port)
        return

    if mode == "client:web":
        webclient_main(host=args.host, port=args.port)
        return

    from chronicler.desktop.main import run_desktop

    run_desktop()


def webclient_main(host: str | None = None, port: int | None = None):
    from chronicler.webclient.main import run_server

    run_server(**_binding(host, port, default_port=8080))


def server_main(host: str | None = None, port: int | None = None):
    from chronicler.server.main import run_server

    run_server(**_binding(host, port, default_port=8000))


def _binding(host: str | None, port: int | None, default_port: int) -> dict:
    return {"host": host or "0.0.0.0", "port": port or default_port}


if __name__ == "__main__":
    main()
