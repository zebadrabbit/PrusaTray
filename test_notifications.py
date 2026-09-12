"""Test the notification system."""

import sys
import time
from PySide6.QtWidgets import QApplication, QSystemTrayIcon
from PySide6.QtGui import QIcon

# Add parent directory to path
sys.path.insert(0, 'c:\\Users\\broca\\OneDrive\\Desktop\\Work\\PrusaTray')

from tray_prusa.notifications import NotificationManager
from tray_prusa.models import PrinterState, PrinterStatus


def test_notifications():
    """Test notification system with simulated state changes."""
    app = QApplication(sys.argv)
    
    # Create a simple tray icon
    tray_icon = QSystemTrayIcon()
    tray_icon.setIcon(QIcon())  # Empty icon for testing
    tray_icon.show()
    
    # Create notification manager
    notifier = NotificationManager(tray_icon)
    
    # Enable all notifications for testing
    notifier.update_preferences(
        notify_on_print_start=True,
        notify_on_print_complete=True,
        notify_on_print_paused=True,
        notify_on_print_error=True,
        notify_on_printer_offline=True,
    )
    
    print("Testing notification system...")
    print("You should see Windows toast notifications for each state change")
    print()
    
    # Test 1: Idle state (initial)
    print("1. Initial idle state (no notification expected)")
    idle_state = PrinterState(status=PrinterStatus.IDLE)
    notifier.handle_state_change(idle_state)
    time.sleep(2)
    
    # Test 2: Print starts
    print("2. Print starts (should show notification)")
    printing_state = PrinterState(
        status=PrinterStatus.PRINTING,
        job_name="test_model.gcode",
        progress=0.0,
    )
    notifier.handle_state_change(printing_state)
    time.sleep(3)
    
    # Test 3: Print pauses
    print("3. Print pauses (should show notification)")
    paused_state = PrinterState(
        status=PrinterStatus.PAUSED,
        job_name="test_model.gcode",
        progress=0.45,
    )
    notifier.handle_state_change(paused_state)
    time.sleep(3)
    
    # Test 4: Print resumes
    print("4. Print resumes (should show notification)")
    printing_state2 = PrinterState(
        status=PrinterStatus.PRINTING,
        job_name="test_model.gcode",
        progress=0.46,
    )
    notifier.handle_state_change(printing_state2)
    time.sleep(3)
    
    # Test 5: Print completes
    print("5. Print completes (should show notification)")
    complete_state = PrinterState(status=PrinterStatus.IDLE)
    notifier.handle_state_change(complete_state)
    time.sleep(3)
    
    # Test 6: Printer goes offline
    print("6. Printer goes offline (should show notification)")
    offline_state = PrinterState(
        status=PrinterStatus.OFFLINE,
        last_error="Connection timeout",
    )
    notifier.handle_state_change(offline_state)
    time.sleep(3)
    
    # Test 7: Printer error
    print("7. Printer error (should show notification)")
    error_state = PrinterState(
        status=PrinterStatus.ERROR,
        error_message="Temperature sensor failure",
    )
    notifier.handle_state_change(error_state)
    time.sleep(3)
    
    print()
    print("✓ Test completed!")
    print("Press Ctrl+C to exit")
    
    sys.exit(app.exec())


if __name__ == "__main__":
    test_notifications()
