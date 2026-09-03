import secrets
import sys
from pathlib import Path

from chronicler.core.config import Settings

LANGUAGE_NAMES = {"en": "English", "nl": "Nederlands", "de": "Deutsch"}


def supported_languages() -> list[str]:
    """The locales Chronicler ships, offered for both the interface and transcription."""
    return list(LANGUAGE_NAMES)


def default_workspace_path() -> Path:
    """A sensible per-OS home for the workspace, preferring the user's Documents folder."""
    home = Path.home()
    documents = home / "Documents"
    base = documents if documents.is_dir() else home
    return (base / "Chronicler").expanduser()


class WizardStep:
    def run(self, settings: Settings) -> None:
        """Run this wizard step."""
        pass

    def is_satisfied(self, settings: Settings) -> bool:
        """Check if this step is already satisfied."""
        return False


class LanguageStep(WizardStep):
    def run(self, settings: Settings) -> None:
        languages = supported_languages()
        print("\n--- Language ---")
        print("Used for Chronicler's own labels and as the default for new transcriptions.")
        for index, code in enumerate(languages, start=1):
            print(f"{index}. {LANGUAGE_NAMES[code]} ({code})")

        while True:
            choice = input(f"\nSelect a language (1-{len(languages)}) [1]: ").strip() or "1"
            if choice.isdigit() and 1 <= int(choice) <= len(languages):
                code = languages[int(choice) - 1]
                settings.ui.locale = code
                settings.transcription.language = code
                return
            print(f"Invalid choice. Please select 1-{len(languages)}.")

    def is_satisfied(self, settings: Settings) -> bool:
        return settings.transcription.language is not None


class WorkspaceStep(WizardStep):
    def run(self, settings: Settings) -> None:
        default_path = default_workspace_path()
        print("\n--- Local Workspace Setup ---")
        print("Chronicler stores your chronicles, recordings and databases in a workspace.")
        path_str = input(f"Enter workspace path [{default_path}]: ").strip()
        settings.workspace_path = (
            Path(path_str).expanduser().resolve() if path_str else default_path
        )

    def is_satisfied(self, settings: Settings) -> bool:
        return settings.workspace_path is not None


class ApiKeyStep(WizardStep):
    def run(self, settings: Settings) -> None:
        print("\n--- API Key Setup ---")
        print("An API key is required for remote access (Thin Client or Web Client).")
        print("1. Generate a new API key (recommended)")
        print("2. Enter an existing API key")
        print("3. Skip (no remote access)")

        while True:
            choice = input("\nSelect an option (1-3) [1]: ").strip() or "1"
            if choice == "1":
                settings.api_key = secrets.token_urlsafe(32)
                print(f"Generated API key: {settings.api_key}")
                break
            elif choice == "2":
                key = input("Enter API key [leave blank to generate]: ").strip()
                if not key:
                    settings.api_key = secrets.token_urlsafe(32)
                    print(f"Generated API key: {settings.api_key}")
                else:
                    settings.api_key = key
                break
            elif choice == "3":
                settings.api_key = None
                break
            else:
                print("Invalid choice. Please select 1, 2 or 3.")

    def is_satisfied(self, settings: Settings) -> bool:
        return bool(settings.api_key)


class RemoteServerStep(WizardStep):
    def run(self, settings: Settings) -> None:
        print("\n--- Remote Server Setup ---")
        print("Connect to an existing Chronicler Server.")
        settings.server_url = input("Enter server URL (e.g. http://localhost:8000): ").strip()

        while True:
            api_key = input("Enter API key (ask the server operator for it): ").strip()
            if api_key:
                break
            print("An API key is required and must match the target server's - it")
            print("cannot be generated here.")
        settings.api_key = api_key

    def is_satisfied(self, settings: Settings) -> bool:
        return bool(settings.server_url) and bool(settings.api_key)


class ConfigWizard:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()

    def run(self, mode: str | None = None):
        if mode:
            if self.settings.validate_for_mode(mode):
                return
            print("========================================")
            print("       Chronicler Configuration         ")
            print("========================================")
            print(f"Configuration is missing or incomplete for mode: {mode}")

            if mode == "server":
                self._run_step(LanguageStep())
                self._run_step(WorkspaceStep())
                self._run_step(ApiKeyStep())
                self.settings.mode = "server"
            elif mode == "client:web":
                self._run_step(LanguageStep())
                self._run_step(RemoteServerStep())
                self.settings.mode = "client:web"
            elif mode == "client:desktop":
                self._show_main_choice()
        else:
            print("========================================")
            print("       Chronicler Configuration         ")
            print("========================================")
            print("No configuration found. Let's set it up.")
            self._show_main_choice()

        config_file = self.settings.save()
        print(f"\nConfiguration saved to {config_file}")
        print("========================================\n")

    def _run_step(self, step: WizardStep, force: bool = False):
        if force or not step.is_satisfied(self.settings):
            step.run(self.settings)

    def _show_main_choice(self):
        self._run_step(LanguageStep())
        print("\nHow would you like to run Chronicler?")
        print("1. Full Stack (Local processing and storage)")
        print("2. Thin Client (Connect to a remote Chronicler Server)")
        print("3. Server (Run as a server for other clients)")
        print("4. Web Client (Run a web server for the browser frontend)")

        while True:
            choice = input("\nSelect an option (1-4) [1]: ").strip() or "1"
            if choice == "1":
                self._run_step(WorkspaceStep())
                self._run_step(ApiKeyStep())
                self.settings.mode = "desktop:full_stack"
                break
            elif choice == "2":
                self._run_step(RemoteServerStep())
                self.settings.mode = "desktop:thin_client"
                break
            elif choice == "3":
                self._run_step(WorkspaceStep())
                self._run_step(ApiKeyStep())
                self.settings.mode = "server"
                break
            elif choice == "4":
                self._run_step(RemoteServerStep())
                self.settings.mode = "client:web"
                break
            else:
                print("Invalid choice. Please select 1, 2, 3 or 4.")


def run_wizard(mode: str | None = None):
    try:
        from chronicler.core.config import get_settings

        wizard = ConfigWizard(settings=get_settings())
        wizard.run(mode=mode)
    except KeyboardInterrupt:
        print("\nConfiguration cancelled.")
        sys.exit(1)
