# Start with Windows Feature

## Overview

PrusaTray can now be configured to automatically start when Windows boots up. This ensures you never miss important printer status updates.

## How to Enable

### Via Configuration UI

1. Right-click the PrusaTray system tray icon
2. Select "Configuration..."
3. Check the box "Start PrusaTray with Windows"
4. Click "Save"

The application will automatically update the Windows registry to enable/disable startup.

### Via Configuration File

Edit your `config.json` file (located at `%LOCALAPPDATA%\PrusaTray\config.json`):

```json
{
  "start_with_windows": true,
  ...
}
```

When the application starts, it will sync the Windows startup registry entry with this configuration.

## Technical Details

### Implementation

The feature is implemented in [`startup_util.py`](tray_prusa/startup_util.py) and uses the Windows registry to manage startup applications:

- **Registry Key**: `HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run`
- **Value Name**: `PrusaTray`
- **Value**: Path to the executable or Python script

### Behavior

- **Compiled Executable**: Uses `sys.executable` to get the .exe path
- **Python Script**: Uses `pythonw.exe` (if available) to avoid showing a console window on startup
- **Auto-sync**: When the app starts, it checks if the Windows registry matches the configuration and syncs if needed

### Permissions

This feature requires:
- **Read access** to check if startup is enabled
- **Write access** to modify the startup registry entry (usually available to all users for their own HKCU registry)

No administrator privileges are required since it modifies `HKEY_CURRENT_USER` (not `HKEY_LOCAL_MACHINE`).

## Configuration Field

The new configuration field in `AppConfig`:

```python
start_with_windows: bool = False  # Auto-start with Windows
```

Default value is `False` (disabled) for backward compatibility.

## Code Changes

### Modified Files

1. **[tray_prusa/startup_util.py](tray_prusa/startup_util.py)** (new)
   - Functions for managing Windows startup registry entries
   - `is_startup_enabled()` - Check if startup is enabled
   - `set_startup_enabled(bool)` - Enable/disable startup
   - `get_executable_path()` - Get current executable path

2. **[tray_prusa/models.py](tray_prusa/models.py)**
   - Added `start_with_windows` field to `AppConfig`

3. **[tray_prusa/config.py](tray_prusa/config.py)**
   - Load and save `start_with_windows` from/to config file

4. **[tray_prusa/tray.py](tray_prusa/tray.py)**
   - Added checkbox to `CredentialsDialog` UI
   - Apply Windows startup setting when saving configuration

5. **[tray_prusa/main.py](tray_prusa/main.py)**
   - Sync Windows startup state with configuration on app start

6. **[config.example.json](config.example.json)**
   - Added example `start_with_windows` field

## Testing

Run the test script:

```powershell
python test_startup.py
```

This will:
1. Get the current executable path
2. Check current startup status
3. Test enabling startup (modifies registry)
4. Verify startup is enabled
5. Test disabling startup
6. Verify startup is disabled

## Notes

- The setting only affects the current user account
- If you move the application to a different location, you should disable and re-enable the setting
- When running from a Python script during development, it will use `pythonw.exe` to avoid console windows
