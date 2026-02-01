"""Main entry point for PrusaTray application."""

import logging
import sys

from PySide6.QtWidgets import QApplication

from tray_prusa.config import ConfigManager
from tray_prusa.logging_setup import setup_logging
from tray_prusa.tray import PrusaTrayIcon
from tray_prusa.poller import PrinterPoller
from tray_prusa.adapter_factory import create_adapter, validate_config
from tray_prusa.models import AppConfig
from tray_prusa import keyring_util

logger = logging.getLogger(__name__)


def check_and_prompt_for_credentials(config: AppConfig) -> None:
    """
    Check if credentials are required and prompt user if missing.

    If password_key is configured but no credential exists in keyring or env var,
    prompts the user once and stores the credential in keyring.

    Args:
        config: Application configuration.
    """
    # Only prompt if auth is enabled and password_key is configured
    if config.auth_mode in ("digest", "apikey") and config.password_key:
        # Check if credential exists
        credential = keyring_util.get_secret(config.password_key)

        if credential is None:
            logger.info(
                f"Credential not found for '{config.password_key}' - prompting user"
            )

            # Prompt user for credential
            credential = keyring_util.prompt_for_credential(config.password_key)

            if credential:
                # Store in keyring
                if keyring_util.set_secret(config.password_key, credential):
                    logger.info(f"Stored credential for '{config.password_key}'")
                else:
                    logger.warning(
                        f"Failed to store credential for '{config.password_key}'"
                    )
                    env_var = f"PRUSATRAY_PASSWORD_{keyring_util._sanitize_key_for_env(config.password_key)}"
                    logger.info(f"You can set environment variable: {env_var}")
            else:
                logger.warning(f"No credential provided for '{config.password_key}'")
                env_var = f"PRUSATRAY_PASSWORD_{keyring_util._sanitize_key_for_env(config.password_key)}"
                logger.info(
                    f"Authentication may fail. Set environment variable: {env_var}"
                )


class PrusaTrayApp:
    """Main application class."""

    def __init__(self):
        """Initialize the application."""
        # Set up logging
        setup_logging()
        logger.info("PrusaTray starting...")

        # Create QApplication
        self.app = QApplication(sys.argv)
        self.app.setApplicationName("PrusaTray")
        self.app.setQuitOnLastWindowClosed(False)  # Keep running when no windows open

        # Load configuration
        self.config_manager = ConfigManager()
        config = self.config_manager.load()

        # Validate configuration
        try:
            validate_config(config)
        except ValueError as e:
            logger.warning(f"Config validation warning: {e}")

        # Check for required credentials and prompt if missing
        check_and_prompt_for_credentials(config)

        # Create adapter based on config
        adapter = create_adapter(config)

        # Create tray icon with config change callback
        self.tray_icon = PrusaTrayIcon(
            self.config_manager, on_config_changed=self._on_config_changed
        )

        # Create poller with adapter
        self.poller = PrinterPoller(
            adapter=adapter, interval_seconds=config.polling_interval_seconds
        )

        # Connect signals
        self.poller.state_updated.connect(self.tray_icon.update_state)

        # Show startup message
        backend_info = f"backend={config.backend}"
        if config.printer_base_url:
            backend_info += f" @ {config.printer_base_url}"

        self.tray_icon.show_message(
            "PrusaTray Started", f"Monitoring printer ({backend_info})"
        )

        logger.info("Application initialized")

    def _on_config_changed(self, new_config: AppConfig) -> None:
        """
        Handle configuration changes (e.g., URL change from tray menu).

        Args:
            new_config: New configuration.
        """
        logger.info(
            f"Configuration changed: backend={new_config.backend}, URL={new_config.printer_base_url}"
        )

        try:
            # Validate new config
            try:
                validate_config(new_config)
            except ValueError as e:
                logger.warning(f"Config validation warning: {e}")

            # Create new adapter
            new_adapter = create_adapter(new_config)

            # Hot-swap adapter in poller
            self.poller.set_adapter(new_adapter)

            # Update polling interval if changed
            if new_config.poll_interval_s != self.config_manager.config.poll_interval_s:
                self.poller.interval_seconds = new_config.poll_interval_s

            logger.info("Adapter hot-swapped successfully")

        except Exception as e:
            logger.error(f"Failed to apply config change: {e}")
            self.tray_icon.show_message(
                "Configuration Error", f"Failed to apply changes: {e}"
            )

    def run(self) -> int:
        """
        Run the application.

        Returns:
            Exit code.
        """
        # Start polling
        self.poller.start()

        logger.info("Entering main event loop")

        # Run event loop
        exit_code = self.app.exec()

        # Cleanup
        self.poller.stop()
        logger.info(f"Application exiting with code {exit_code}")

        return exit_code


def main() -> int:
    """
    Main entry point.

    Returns:
        Exit code.
    """
    app = PrusaTrayApp()
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
