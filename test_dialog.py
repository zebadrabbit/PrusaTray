"""Quick test to display the credentials dialog."""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from PySide6.QtWidgets import QApplication
from tray_prusa.config import ConfigManager
from tray_prusa.tray import CredentialsDialog


def test_dialog():
    """Display the credentials dialog."""
    app = QApplication(sys.argv)
    
    # Create config manager with default config
    config_manager = ConfigManager()
    config_manager.load()
    
    # Show dialog
    dialog = CredentialsDialog(config_manager)
    dialog.show()
    
    # Run app
    sys.exit(app.exec())


if __name__ == "__main__":
    test_dialog()
