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

    args = parser.parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )

    from chronicler.core.config import get_settings, is_config_initialized
    from chronicler.core.wizard import run_wizard

    # Map friendly names to internal mode names
    mode_map = {
        "desktop": "client:desktop",
        "web": "client:web",
        "server": "server",
        "client:web": "client:web",
        "client:desktop": "client:desktop",
    }
    mode = mode_map.get(args.mode, args.mode)

    if not is_config_initialized():
        run_wizard(mode=mode)
    else:
        # Check if settings are valid for the chosen mode
        settings = get_settings()
        if not settings.validate_for_mode(mode):
            run_wizard(mode=mode)

    if mode == "server":
        server_main()
        return

    if mode == "client:web":
        webclient_main()
        return

    from chronicler.desktop.main import run_desktop

    run_desktop()


def webclient_main():
    from chronicler.webclient.main import run_server

    run_server()


def server_main():
    from chronicler.server.main import run_server

    run_server()


if __name__ == "__main__":
    main()
