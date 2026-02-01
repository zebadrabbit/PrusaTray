"""Configuration management for the application."""

import json
import logging
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from .models import AppConfig

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages loading and saving application configuration."""

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize configuration manager.

        Args:
            config_path: Path to config file. If None, uses default location.
        """
        if config_path is None:
            # Default to user's AppData/Local directory on Windows
            app_data = Path.home() / "AppData" / "Local" / "PrusaTray"
            app_data.mkdir(parents=True, exist_ok=True)
            config_path = app_data / "config.json"

        self.config_path = config_path
        self._config: Optional[AppConfig] = None

    @staticmethod
    def validate_url(url: str) -> bool:
        """
        Validate URL format.

        Args:
            url: URL string to validate.

        Returns:
            True if valid HTTP/HTTPS URL, False otherwise.
        """
        if not url:
            return False

        try:
            result = urlparse(url)
            return all([result.scheme in ("http", "https"), result.netloc])
        except Exception:
            return False

    def load(self) -> AppConfig:
        """
        Load configuration from file. Never crashes on malformed config.

        Returns:
            AppConfig instance (uses defaults if file doesn't exist or is malformed).
        """
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Validate URL if provided
                base_url = data.get("printer_base_url")
                if base_url and not self.validate_url(base_url):
                    logger.warning(f"Invalid URL in config: {base_url}, ignoring")
                    base_url = None

                # Validate polling interval
                poll_interval = data.get(
                    "poll_interval_s", data.get("polling_interval_seconds", 3.0)
                )
                try:
                    poll_interval = max(1.0, float(poll_interval))
                except (ValueError, TypeError):
                    logger.warning(
                        f"Invalid poll interval: {poll_interval}, using default 3.0s"
                    )
                    poll_interval = 3.0

                self._config = AppConfig(
                    printer_base_url=base_url,
                    poll_interval_s=poll_interval,
                    backend=data.get("backend", "demo"),
                    open_ui_path=data.get("open_ui_path", "/"),
                    icon_style=data.get("icon_style", "ring"),
                    username=data.get("username"),
                    auth_mode=data.get("auth_mode", "none"),
                )
                logger.info(f"Loaded configuration from {self.config_path}")
            except json.JSONDecodeError as e:
                logger.error(f"Malformed JSON in config: {e}. Using defaults.")
                self._config = AppConfig()
            except Exception as e:
                logger.error(f"Failed to load config: {e}. Using defaults.")
                self._config = AppConfig()
        else:
            logger.info("Config file not found. Using defaults.")
            self._config = AppConfig()

        return self._config

    def save(self, config: AppConfig) -> None:
        """
        Save configuration to file.

        Args:
            config: AppConfig instance to save.
        """
        self._config = config

        data = {
            "printer_base_url": config.printer_base_url,
            "poll_interval_s": config.poll_interval_s,
            "backend": config.backend,
            "open_ui_path": config.open_ui_path,
            "icon_style": config.icon_style,
            "username": config.username,
            "auth_mode": config.auth_mode,
        }

        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            logger.info(f"Saved configuration to {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    @property
    def config(self) -> AppConfig:
        """Get current configuration (loads if not already loaded)."""
        if self._config is None:
            return self.load()
        return self._config
