import logging
import sys


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )
    from chronicler.core.config import get_settings, is_config_initialized
    from chronicler.core.wizard import run_wizard

    mode = "client:desktop"
    if len(sys.argv) > 1:
        if sys.argv[1] == "server":
            mode = "server"
        elif sys.argv[1] == "client:web":
            mode = "client:web"

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
