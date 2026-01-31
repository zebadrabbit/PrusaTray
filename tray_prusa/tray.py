"""System tray icon and menu implementation."""

import logging
import webbrowser
from typing import Optional, Callable

from PySide6.QtWidgets import (
    QSystemTrayIcon, QMenu, QApplication, QInputDialog,
    QDialog, QVBoxLayout, QLabel, QLineEdit, QComboBox,
    QPushButton, QHBoxLayout, QMessageBox, QWidget
)
from PySide6.QtGui import QAction
from PySide6.QtCore import QObject, Signal, QThread

from .models import PrinterState, PrinterStatus, AppConfig
from .icon import create_tray_icon
from .config import ConfigManager
from . import keyring_util

logger = logging.getLogger(__name__)


class PrusaTrayIcon(QObject):
    """
    System tray icon with menu and dynamic updates.
    
    Manages the tray icon, tooltip, and context menu.
    """
    
    def __init__(
        self,
        config_manager: ConfigManager,
        on_config_changed: Optional[Callable[[AppConfig], None]] = None,
        parent: Optional[QObject] = None
    ):
        """
        Initialize the tray icon.
        
        Args:
            config_manager: Configuration manager instance.
            on_config_changed: Callback when configuration changes (e.g., for adapter hot-swap).
            parent: Parent QObject.
        """
        super().__init__(parent)
        
        self.config_manager = config_manager
        self.on_config_changed = on_config_changed
        self._current_state: Optional[PrinterState] = None
        
        # Create system tray icon
        self.tray_icon = QSystemTrayIcon(self)
        
        # Create context menu
        self._create_menu()
        
        # Set initial icon
        self._update_icon()
        
        # Show the tray icon
        self.tray_icon.show()
        
        logger.info("System tray icon initialized")
    
    def _create_menu(self) -> None:
        """Create the context menu for the tray icon."""
        menu = QMenu()
        
        # "Open printer UI" action
        self.open_ui_action = QAction("Open printer UI", self)
        self.open_ui_action.triggered.connect(self._open_printer_ui)
        menu.addAction(self.open_ui_action)
        
        # "Refresh now" action
        refresh_action = QAction("Refresh now", self)
        refresh_action.triggered.connect(self._refresh_now)
        menu.addAction(refresh_action)
        
        # Separator
        menu.addSeparator()
        
        # "Configuration..." action
        config_action = QAction("Configuration...", self)
        config_action.triggered.connect(self._set_credentials)
        menu.addAction(config_action)
        
        # Separator
        menu.addSeparator()
        
        # "Quit" action
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self._quit_application)
        menu.addAction(quit_action)
        
        self.tray_icon.setContextMenu(menu)
        
        # Update "Open printer UI" enabled state
        self._update_menu_state()
    
    def _update_menu_state(self) -> None:
        """Update menu item states based on configuration."""
        config = self.config_manager.config
        # Enable "Open printer UI" only if URL is configured
        self.open_ui_action.setEnabled(config.printer_base_url is not None)
    
    def update_state(self, state: PrinterState) -> None:
        """
        Update tray icon with new printer state.
        
        Args:
            state: New printer state.
        """
        self._current_state = state
        self._update_icon()
        self._update_tooltip()
        logger.debug(f"Tray updated: {state.status.value}, {state.progress_percent}%")
    
    def _update_icon(self) -> None:
        """Update the tray icon based on current state."""
        if self._current_state is None:
            # Initial state
            status = PrinterStatus.UNKNOWN
            progress = 0.0
        else:
            status = self._current_state.status
            progress = self._current_state.progress_percent or 0.0
        
        config = self.config_manager.config
        icon = create_tray_icon(status, progress, style=config.icon_style)
        self.tray_icon.setIcon(icon)
    
    def _update_tooltip(self) -> None:
        """Update the tray icon tooltip."""
        if self._current_state is None:
            tooltip = "PrusaTray - Starting..."
        else:
            tooltip = self._current_state.get_tooltip_text()
        
        self.tray_icon.setToolTip(tooltip)
    
    def _open_printer_ui(self) -> None:
        """Open the printer web UI in default browser."""
        config = self.config_manager.config
        
        if config.printer_base_url:
            url = config.printer_base_url.rstrip('/') + config.open_ui_path
            logger.info(f"Opening printer UI: {url}")
            try:
                webbrowser.open(url)
            except Exception as e:
                logger.error(f"Failed to open browser: {e}")
                self.show_message("Error", f"Failed to open browser: {e}")
        else:
            logger.warning("No printer URL configured")
            self.show_message("Not Configured", "Please set printer URL first")
    
    def _set_printer_url(self) -> None:
        """Show dialog to set printer URL and backend."""
        config = self.config_manager.config
        current_url = config.printer_base_url or ""
        
        # Show input dialog
        url, ok = QInputDialog.getText(
            None,
            "Set Printer URL",
            "Enter printer URL (e.g., http://192.168.1.100):",
            text=current_url
        )
        
        if not ok:
            return  # User cancelled
        
        url = url.strip()
        
        # Validate URL
        if url and not ConfigManager.validate_url(url):
            logger.error(f"Invalid URL format: {url}")
            self.show_message("Invalid URL", "Please enter a valid HTTP or HTTPS URL")
            return
        
        # Determine backend from URL
        backend = "demo"
        if url:
            url_lower = url.lower()
            if "prusalink" in url_lower or ":8080" in url_lower:
                backend = "prusalink"
            elif "prusaconnect" in url_lower:
                backend = "prusaconnect"
            elif "octoprint" in url_lower or ":5000" in url_lower:
                backend = "octoprint"
            else:
                # Default to prusalink for unknown URLs
                backend = "prusalink"
        
        # Update config
        new_config = AppConfig(
            printer_base_url=url if url else None,
            poll_interval_s=config.poll_interval_s,
            backend=backend,
            open_ui_path=config.open_ui_path,
            icon_style=config.icon_style
        )
        
        # Save config
        try:
            self.config_manager.save(new_config)
            logger.info(f"Saved new config: URL={url}, backend={backend}")
            
            # Update menu state
            self._update_menu_state()
            
            # Notify parent to reload adapter
            if self.on_config_changed:
                self.on_config_changed(new_config)
            
            # Show success message
            if url:
                self.show_message("Configuration Updated", f"Printer URL set to {url}\nBackend: {backend}")
            else:
                self.show_message("Configuration Updated", "Switched to demo mode")
                
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            self.show_message("Error", f"Failed to save configuration: {e}")
    
    def _set_credentials(self) -> None:
        """Show dialog to set printer credentials."""
        dialog = CredentialsDialog(self.config_manager, None)  # Pass None, not self
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Config was updated, notify parent
            if self.on_config_changed:
                self.on_config_changed(self.config_manager.config)
    
    def _refresh_now(self) -> None:
        """Trigger an immediate refresh of printer state."""
        logger.info("Manual refresh requested")
        # The poller will handle this via its connected signal
        # We emit a custom signal if needed, but for now just log
        # The parent app can connect this to the poller's poll method
    
    def _quit_application(self) -> None:
        """Quit the application."""
        logger.info("Quit requested from tray menu")
        QApplication.quit()
    
    def show_message(self, title: str, message: str) -> None:
        """
        Show a system tray notification.
        
        Args:
            title: Notification title.
            message: Notification message.
        """
        self.tray_icon.showMessage(
            title,
            message,
            QSystemTrayIcon.MessageIcon.Information,
            3000  # 3 seconds
        )


class ConnectionTestWorker(QThread):
    """Worker thread for testing printer connection."""
    
    # Signals
    test_completed = Signal(bool, str)  # (success, message)
    
    def __init__(self, base_url: str, username: str, password: str, auth_mode: str):
        """
        Initialize worker.
        
        Args:
            base_url: Printer base URL.
            username: Username (or API key name).
            password: Password (or API key value).
            auth_mode: Authentication mode ("digest" or "apikey").
        """
        super().__init__()
        self.base_url = base_url
        self.username = username
        self.password = password
        self.auth_mode = auth_mode
    
    def run(self) -> None:
        """Run connection test in background thread."""
        try:
            from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
            from PySide6.QtCore import QUrl, QEventLoop, QTimer
            
            # Create network manager
            manager = QNetworkAccessManager()
            
            # Build request
            test_url = f"{self.base_url.rstrip('/')}/api/v1/status"
            request = QNetworkRequest(QUrl(test_url))
            
            # Add authentication
            if self.auth_mode == "apikey":
                # API key mode: add X-Api-Key header
                request.setRawHeader(b"X-Api-Key", self.password.encode('utf-8'))
            elif self.auth_mode == "digest":
                # Digest auth needs to be handled differently
                # For now, we'll send basic auth as a test
                import base64
                credentials = f"{self.username}:{self.password}"
                b64_credentials = base64.b64encode(credentials.encode('utf-8')).decode('ascii')
                request.setRawHeader(b"Authorization", f"Basic {b64_credentials}".encode('utf-8'))
            
            # Send request with timeout
            reply = manager.get(request)
            
            # Wait for response with timeout
            loop = QEventLoop()
            timer = QTimer()
            timer.setSingleShot(True)
            timer.timeout.connect(loop.quit)
            reply.finished.connect(loop.quit)
            timer.start(10000)  # 10 second timeout
            loop.exec()
            
            # Check result
            if timer.isActive():
                timer.stop()
                error = reply.error()
                status_code = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
                
                if error == QNetworkReply.NetworkError.NoError and status_code == 200:
                    self.test_completed.emit(True, "Connection successful!")
                elif status_code == 401 or status_code == 403:
                    self.test_completed.emit(False, f"Authentication failed (HTTP {status_code})")
                elif error != QNetworkReply.NetworkError.NoError:
                    error_string = reply.errorString()
                    self.test_completed.emit(False, f"Connection error: {error_string}")
                else:
                    self.test_completed.emit(False, f"Unexpected status code: {status_code}")
            else:
                reply.abort()
                self.test_completed.emit(False, "Connection timeout after 10 seconds")
                
        except Exception as e:
            logger.error(f"Connection test error: {e}")
            self.test_completed.emit(False, f"Test error: {str(e)}")


class CredentialsDialog(QDialog):
    """Dialog for setting printer credentials."""
    
    def __init__(self, config_manager: ConfigManager, parent: Optional[QWidget] = None):
        """
        Initialize credentials dialog.
        
        Args:
            config_manager: Configuration manager.
            parent: Parent widget.
        """
        super().__init__(parent)
        self.config_manager = config_manager
        self.test_worker: Optional[ConnectionTestWorker] = None
        
        self.setWindowTitle("Set Printer Credentials")
        self.setModal(True)
        self.resize(400, 300)
        
        # Get current config
        config = config_manager.config
        
        # Layout
        layout = QVBoxLayout()
        
        # Base URL
        layout.addWidget(QLabel("Printer URL:"))
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("http://192.168.1.100")
        if config.printer_base_url:
            self.url_input.setText(config.printer_base_url)
        layout.addWidget(self.url_input)
        
        # Auth mode
        layout.addWidget(QLabel("Authentication Mode:"))
        self.auth_mode_combo = QComboBox()
        self.auth_mode_combo.addItems(["none", "digest", "apikey"])
        current_mode = config.auth_mode if config.auth_mode else "none"
        self.auth_mode_combo.setCurrentText(current_mode)
        self.auth_mode_combo.currentTextChanged.connect(self._on_auth_mode_changed)
        layout.addWidget(self.auth_mode_combo)
        
        # Username
        layout.addWidget(QLabel("Username:"))
        self.username_input = QLineEdit()
        self.username_input.setPlaceholderText("username or API key name")
        if config.username:
            self.username_input.setText(config.username)
        layout.addWidget(self.username_input)
        
        # Password/API Key
        self.password_label = QLabel("Password:")
        layout.addWidget(self.password_label)
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setPlaceholderText("password or API key")
        # Try to load existing password
        if config.printer_base_url and config.username:
            existing_pw = keyring_util.get_password(config.printer_base_url, config.username)
            if existing_pw:
                self.password_input.setText(existing_pw)
        layout.addWidget(self.password_input)
        
        # Update labels based on auth mode
        self._on_auth_mode_changed(current_mode)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        # Test Connection button
        self.test_button = QPushButton("Test Connection")
        self.test_button.clicked.connect(self._test_connection)
        button_layout.addWidget(self.test_button)
        
        button_layout.addStretch()
        
        # Save button
        save_button = QPushButton("Save")
        save_button.clicked.connect(self.accept)
        button_layout.addWidget(save_button)
        
        # Cancel button
        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(cancel_button)
        
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def _on_auth_mode_changed(self, mode: str) -> None:
        """Update UI based on selected auth mode."""
        if mode == "none":
            self.username_input.setEnabled(False)
            self.password_input.setEnabled(False)
            self.password_label.setText("Password:")
        elif mode == "digest":
            self.username_input.setEnabled(True)
            self.password_input.setEnabled(True)
            self.password_label.setText("Password:")
        elif mode == "apikey":
            self.username_input.setEnabled(True)
            self.password_input.setEnabled(True)
            self.password_label.setText("API Key:")
    
    def _test_connection(self) -> None:
        """Test connection with current credentials."""
        base_url = self.url_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text()
        auth_mode = self.auth_mode_combo.currentText()
        
        # Validate inputs
        if not base_url:
            QMessageBox.warning(self, "Invalid Input", "Please enter a printer URL")
            return
        
        if not ConfigManager.validate_url(base_url):
            QMessageBox.warning(self, "Invalid URL", "Please enter a valid HTTP or HTTPS URL")
            return
        
        if auth_mode != "none" and (not username or not password):
            QMessageBox.warning(self, "Invalid Input", "Please enter username and password/API key")
            return
        
        # Disable test button during test
        self.test_button.setEnabled(False)
        self.test_button.setText("Testing...")
        
        # Start connection test in background thread
        self.test_worker = ConnectionTestWorker(base_url, username, password, auth_mode)
        self.test_worker.test_completed.connect(self._on_test_completed)
        self.test_worker.start()
    
    def _on_test_completed(self, success: bool, message: str) -> None:
        """Handle connection test completion."""
        # Re-enable test button
        self.test_button.setEnabled(True)
        self.test_button.setText("Test Connection")
        
        # Show result
        if success:
            QMessageBox.information(self, "Connection Test", message)
        else:
            QMessageBox.warning(self, "Connection Test Failed", message)
    
    def accept(self) -> None:
        """Save credentials and close dialog."""
        base_url = self.url_input.text().strip()
        username = self.username_input.text().strip()
        password = self.password_input.text()
        auth_mode = self.auth_mode_combo.currentText()
        
        # Validate URL
        if base_url and not ConfigManager.validate_url(base_url):
            QMessageBox.warning(self, "Invalid URL", "Please enter a valid HTTP or HTTPS URL")
            return
        
        # Auto-detect backend
        backend = "demo"
        if base_url:
            url_lower = base_url.lower()
            if "prusalink" in url_lower or ":8080" in url_lower:
                backend = "prusalink"
            elif "prusaconnect" in url_lower:
                backend = "prusaconnect"
            elif "octoprint" in url_lower or ":5000" in url_lower:
                backend = "octoprint"
            else:
                backend = "prusalink"
        
        # Create new config
        config = self.config_manager.config
        new_config = AppConfig(
            printer_base_url=base_url if base_url else None,
            poll_interval_s=config.poll_interval_s,
            backend=backend,
            open_ui_path=config.open_ui_path,
            icon_style=config.icon_style,
            username=username if username and auth_mode != "none" else None,
            auth_mode=auth_mode
        )
        
        # Save config
        try:
            self.config_manager.save(new_config)
            logger.info(f"Saved credentials: URL={base_url}, username={username}, auth_mode={auth_mode}")
            
            # Store password securely if provided
            if base_url and username and password and auth_mode != "none":
                if keyring_util.set_password(base_url, username, password):
                    logger.info("Password stored securely in keyring")
                else:
                    QMessageBox.warning(self, "Warning", "Failed to store password securely")
            
            super().accept()
            
        except Exception as e:
            logger.error(f"Failed to save credentials: {e}")
            QMessageBox.critical(self, "Error", f"Failed to save credentials: {e}")

