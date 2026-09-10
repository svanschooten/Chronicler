import argparse
import logging


def main():
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

    # Only run console wizard for non-desktop modes
    if mode != "client:desktop":
        from chronicler.core.wizard import run_wizard

        if not is_config_initialized():
            run_wizard(mode=mode)
        else:
            settings = get_settings()
            if not settings.validate_for_mode(mode):
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
