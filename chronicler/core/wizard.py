import secrets
import sys
from pathlib import Path

from chronicler.core.config import Settings


class WizardStep:
    def run(self, settings: Settings) -> None:
        """Run this wizard step."""
        pass

    def is_satisfied(self, settings: Settings) -> bool:
        """Check if this step is already satisfied."""
        return False


class WorkspaceStep(WizardStep):
    def run(self, settings: Settings) -> None:
        default_path = Path.home() / "ChroniclerWorkspace"
        print("\n--- Local Workspace Setup ---")
        print("Chronicler stores your data in a workspace.")
        path_str = input(f"Enter workspace path [{default_path}]: ").strip()
        settings.workspace_path = Path(path_str) if path_str else default_path

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

        api_key = input("Enter API key [leave blank to generate]: ").strip()
        if not api_key:
            api_key = secrets.token_urlsafe(32)
            print(f"No API key provided. Generated: {api_key}")
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
                self._run_step(WorkspaceStep())
                self._run_step(ApiKeyStep())
            elif mode == "client:web":
                self._run_step(RemoteServerStep())
            elif mode == "client:desktop":
                # For desktop we don't know if they want full stack or thin client
                # so we show the main choice
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
                break
            elif choice == "2":
                self._run_step(RemoteServerStep())
                break
            elif choice == "3":
                self._run_step(WorkspaceStep())
                self._run_step(ApiKeyStep())
                break
            elif choice == "4":
                self._run_step(RemoteServerStep())
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
