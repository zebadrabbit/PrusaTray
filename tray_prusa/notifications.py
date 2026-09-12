"""Notification system for showing Windows toast notifications on state changes."""

import logging
from typing import Optional
from PySide6.QtWidgets import QSystemTrayIcon

from .models import PrinterState, PrinterStatus

logger = logging.getLogger(__name__)


class NotificationManager:
    """Manages notifications for printer state changes."""

    def __init__(self, tray_icon: QSystemTrayIcon):
        """
        Initialize notification manager.

        Args:
            tray_icon: System tray icon for showing notifications.
        """
        self.tray_icon = tray_icon
        self._last_state: Optional[PrinterState] = None

        # Notification preferences (set by config)
        self.notify_on_print_start = False
        self.notify_on_print_complete = False
        self.notify_on_print_paused = False
        self.notify_on_print_error = False
        self.notify_on_printer_offline = False

    def update_preferences(
        self,
        notify_on_print_start: bool = False,
        notify_on_print_complete: bool = False,
        notify_on_print_paused: bool = False,
        notify_on_print_error: bool = False,
        notify_on_printer_offline: bool = False,
    ) -> None:
        """
        Update notification preferences.

        Args:
            notify_on_print_start: Show notification when print starts.
            notify_on_print_complete: Show notification when print completes.
            notify_on_print_paused: Show notification when print pauses.
            notify_on_print_error: Show notification on printer error.
            notify_on_printer_offline: Show notification when printer goes offline.
        """
        self.notify_on_print_start = notify_on_print_start
        self.notify_on_print_complete = notify_on_print_complete
        self.notify_on_print_paused = notify_on_print_paused
        self.notify_on_print_error = notify_on_print_error
        self.notify_on_printer_offline = notify_on_printer_offline

    def handle_state_change(self, new_state: PrinterState) -> None:
        """
        Handle printer state update and show notifications if configured.

        Args:
            new_state: New printer state.
        """
        if self._last_state is None:
            # First state update - don't notify
            self._last_state = new_state
            return

        old_status = self._last_state.status
        new_status = new_state.status

        # Check for state transitions and notify accordingly
        if old_status == new_status:
            # No status change
            self._last_state = new_state
            return

        # Print started: was idle/paused, now printing
        if self.notify_on_print_start:
            if new_status == PrinterStatus.PRINTING and old_status in (
                PrinterStatus.IDLE,
                PrinterStatus.PAUSED,
            ):
                job_name = new_state.job_name or "Unknown"
                self._show_notification(
                    "Print Started",
                    f"Started printing: {job_name}",
                )

        # Print completed: was printing, now idle
        if self.notify_on_print_complete:
            if (
                new_status == PrinterStatus.IDLE
                and old_status == PrinterStatus.PRINTING
            ):
                job_name = self._last_state.job_name or "Print job"
                self._show_notification(
                    "Print Complete",
                    f"{job_name} finished successfully!",
                )

        # Print paused
        if self.notify_on_print_paused:
            if (
                new_status == PrinterStatus.PAUSED
                and old_status == PrinterStatus.PRINTING
            ):
                job_name = new_state.job_name or "Print"
                progress = (
                    f" ({new_state.progress_percent:.0f}%)"
                    if new_state.progress_percent
                    else ""
                )
                self._show_notification(
                    "Print Paused",
                    f"{job_name} paused{progress}",
                )

        # Print error
        if self.notify_on_print_error:
            if new_status == PrinterStatus.ERROR:
                error_msg = new_state.error_message or "Unknown error"
                self._show_notification(
                    "Printer Error",
                    error_msg,
                    icon=QSystemTrayIcon.MessageIcon.Critical,
                )

        # Printer went offline
        if self.notify_on_printer_offline:
            if (
                new_status == PrinterStatus.OFFLINE
                and old_status != PrinterStatus.OFFLINE
            ):
                error = new_state.last_error or "Connection lost"
                self._show_notification(
                    "Printer Offline",
                    error,
                    icon=QSystemTrayIcon.MessageIcon.Warning,
                )

        # Update last state
        self._last_state = new_state

    def _show_notification(
        self,
        title: str,
        message: str,
        icon: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.MessageIcon.Information,
    ) -> None:
        """
        Show a system tray notification.

        Args:
            title: Notification title.
            message: Notification message.
            icon: Notification icon type.
        """
        logger.info(f"Notification: {title} - {message}")
        self.tray_icon.showMessage(title, message, icon, 5000)  # 5 seconds
