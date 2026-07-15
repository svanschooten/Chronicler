import sys


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "server":
        server_main()
        return

    from chronicler.desktop.main import run_desktop

    run_desktop()


def server_main():
    from chronicler.server.main import run_server

    run_server()


if __name__ == "__main__":
    main()
