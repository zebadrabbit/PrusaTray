# Notification System

## Overview

PrusaTray now includes a configurable notification system that displays Windows toast notifications when the printer state changes. All notifications are **disabled by default** and must be explicitly enabled by the user.

## Features

The notification system can alert you about:

1. **Print Started** - When a print job begins (from idle or paused)
2. **Print Complete** - When a print job finishes successfully
3. **Print Paused** - When an active print is paused
4. **Printer Error** - When the printer encounters an error
5. **Printer Offline** - When the printer becomes unreachable

## Configuration

### Via UI

1. Right-click the PrusaTray system tray icon
2. Select "Configuration..."
3. Scroll down to the "Notifications" section
4. Check the boxes for events you want to be notified about
5. Click "Save"

### Via Configuration File

Edit your `config.json` file (located at `%LOCALAPPDATA%\PrusaTray\config.json`):

```json
{
  "notify_on_print_start": true,
  "notify_on_print_complete": true,
  "notify_on_print_paused": false,
  "notify_on_print_error": true,
  "notify_on_printer_offline": true,
  ...
}
```

All notification settings default to `false` if not specified.

## Notification Examples

### Print Started
- **Title**: Print Started
- **Message**: Started printing: model.gcode
- **Icon**: Information
- **Duration**: 5 seconds

### Print Complete
- **Title**: Print Complete
- **Message**: model.gcode finished successfully!
- **Icon**: Information
- **Duration**: 5 seconds

### Print Paused
- **Title**: Print Paused
- **Message**: model.gcode paused (45%)
- **Icon**: Information
- **Duration**: 5 seconds

### Printer Error
- **Title**: Printer Error
- **Message**: [Error message from printer]
- **Icon**: Critical (red X)
- **Duration**: 5 seconds

### Printer Offline
- **Title**: Printer Offline
- **Message**: Connection timeout
- **Icon**: Warning (yellow triangle)
- **Duration**: 5 seconds

## Technical Details

### Implementation

The notification system is implemented in [`notifications.py`](tray_prusa/notifications.py) using:

- **State Tracking**: Compares previous and current printer states to detect transitions
- **Windows Toast Notifications**: Uses `QSystemTrayIcon.showMessage()` for native Windows notifications
- **Event-based**: Triggered automatically when the poller detects state changes

### State Transitions

The system detects these specific transitions:

- **Print Start**: `IDLE` → `PRINTING` or `PAUSED` → `PRINTING`
- **Print Complete**: `PRINTING` → `IDLE`
- **Print Paused**: `PRINTING` → `PAUSED`
- **Printer Error**: Any state → `ERROR`
- **Printer Offline**: Any state (except `OFFLINE`) → `OFFLINE`

### Configuration Fields

New fields in `AppConfig`:

```python
notify_on_print_start: bool = False
notify_on_print_complete: bool = False
notify_on_print_paused: bool = False
notify_on_print_error: bool = False
notify_on_printer_offline: bool = False
```

## Code Changes

### New Files

1. **[tray_prusa/notifications.py](tray_prusa/notifications.py)** - `NotificationManager` class
   - `update_preferences()` - Update notification settings
   - `handle_state_change()` - Process state changes and show notifications
   - `_show_notification()` - Display Windows toast notification

### Modified Files

1. **[tray_prusa/models.py](tray_prusa/models.py)**
   - Added 5 notification preference fields to `AppConfig`

2. **[tray_prusa/config.py](tray_prusa/config.py)**
   - Load and save notification preferences

3. **[tray_prusa/main.py](tray_prusa/main.py)**
   - Create `NotificationManager` instance
   - Connect to poller's `state_updated` signal
   - Update preferences when config changes

4. **[tray_prusa/tray.py](tray_prusa/tray.py)**
   - Added "Notifications" section to configuration dialog
   - 5 checkboxes for notification preferences
   - Increased dialog height to 500px

5. **[config.example.json](config.example.json)**
   - Added notification fields with examples

6. **[README.md](README.md)**
   - Updated features list

## Testing

Run the test script to see notifications in action:

```powershell
python test_notifications.py
```

This simulates various state changes and displays the corresponding notifications.

## Privacy & Performance

- **No external connections**: Notifications are generated locally based on state changes
- **Minimal overhead**: Only triggers on state transitions, not on every poll
- **Non-intrusive**: 5-second duration, doesn't require user action
- **User control**: All notifications are opt-in and can be individually enabled/disabled

## Default Behavior

By design, **all notifications are disabled by default** to avoid surprising users with unexpected toast popups. Users must explicitly enable the notifications they want through the configuration dialog or config file.
