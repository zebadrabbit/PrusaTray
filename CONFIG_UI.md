# Configuration UI Documentation

## Overview

PrusaTray provides a simple configuration UI accessible from the system tray menu. You can switch between demo mode and real printer monitoring without restarting the application.

## Setting Printer URL

1. Right-click the tray icon
2. Select **"Set Printer URL..."**
3. Enter your printer's URL (e.g., `http://192.168.1.100`)
4. Click OK

The application will:
- Validate the URL format
- Auto-detect the backend type (PrusaLink, OctoPrint, etc.)
- Save the configuration
- Hot-swap to the new backend immediately
- Show a confirmation notification

## URL Format

Valid URL formats:
- `http://192.168.1.100` - IP address
- `http://192.168.1.100:8080` - IP with custom port
- `http://printer.local` - mDNS hostname
- `https://connect.prusa3d.com` - HTTPS URL

Invalid formats will be rejected with an error message.

## Backend Auto-Detection

The backend is automatically detected from the URL:
- URLs containing `prusalink` or port `:8080` → PrusaLink
- URLs containing `prusaconnect` → PrusaConnect
- URLs containing `octoprint` or port `:5000` → OctoPrint
- Other HTTP(S) URLs → PrusaLink (default)
- Empty URL → Demo mode

## Configuration Storage

Configuration is stored in JSON format at:
```
%LOCALAPPDATA%\PrusaTray\config.json
```

Example config file:
```json
{
  "printer_base_url": "http://192.168.1.100",
  "poll_interval_s": 3.0,
  "backend": "prusalink",
  "open_ui_path": "/",
  "icon_style": "ring"
}
```

## Configuration Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `printer_base_url` | string or null | `null` | Base URL of the printer |
| `poll_interval_s` | float | `3.0` | Polling interval in seconds (min 1.0) |
| `backend` | string | `"demo"` | Backend type: `demo`, `prusalink`, `octoprint`, `prusaconnect` |
| `open_ui_path` | string | `"/"` | Path appended to base URL when opening printer UI |
| `icon_style` | string | `"ring"` | Icon rendering style: `ring` or `bar` |

## Robustness Features

### Error Handling
- **Malformed JSON**: Uses default configuration
- **Invalid URL**: Rejects URL and shows error dialog
- **Invalid values**: Falls back to safe defaults
- **Never crashes**: All errors are logged and handled gracefully

### Validation
- URL must be HTTP or HTTPS
- Polling interval must be ≥ 1.0 seconds
- Unknown fields are ignored (forward compatibility)

### Hot-Swapping
When you change the printer URL:
1. Configuration is saved to disk
2. New adapter is created
3. Poller switches to new adapter **without restart**
4. New backend starts polling immediately
5. Previous state is cleared

This allows seamless switching from demo mode to real printer monitoring.

## Example Workflows

### Initial Setup (Demo → PrusaLink)
1. Launch app (starts in demo mode)
2. Right-click tray icon → "Set Printer URL..."
3. Enter `http://192.168.1.100`
4. App switches to PrusaLink backend immediately

### Changing Printers
1. Right-click tray icon → "Set Printer URL..."
2. Enter new URL `http://192.168.1.200`
3. App hot-swaps to new printer

### Return to Demo Mode
1. Right-click tray icon → "Set Printer URL..."
2. Clear the text field (leave empty)
3. App switches back to demo mode

## Opening Printer UI

Once a URL is configured:
1. Right-click tray icon → "Open printer UI"
2. Default browser opens to `{printer_base_url}{open_ui_path}`
3. Example: `http://192.168.1.100/` opens in browser

If no URL is configured, you'll see a notification: "Please set printer URL first"

## Manual Configuration

You can manually edit `config.json` while the app is **not running**:

```json
{
  "printer_base_url": "http://192.168.1.100:8080",
  "poll_interval_s": 5.0,
  "backend": "prusalink",
  "open_ui_path": "/",
  "icon_style": "ring"
}
```

The app will load these settings on next launch.

## Troubleshooting

### "Invalid URL" error
- Ensure URL starts with `http://` or `https://`
- Check for typos in the hostname/IP
- Verify the printer is accessible on your network

### Config changes not taking effect
- Check logs for validation errors
- Verify config file is not corrupted JSON
- Try deleting config.json to reset to defaults

### Adapter not switching
- Check logs for adapter creation errors
- Verify backend implementation is complete
- Try restarting the app

## Technical Details

### Config Validation Flow
```
User enters URL
  ↓
ConfigManager.validate_url(url)
  ↓
URL format validated (http/https, has netloc)
  ↓
Backend auto-detected from URL
  ↓
AppConfig created
  ↓
ConfigManager.save(config)
  ↓
Tray calls on_config_changed callback
  ↓
Main app creates new adapter
  ↓
Poller.set_adapter(new_adapter)
  ↓
Polling resumes with new backend
```

### Backward Compatibility
Old config files using `polling_interval_seconds` are automatically upgraded:
```json
{
  "polling_interval_seconds": 5.0  // Old field name
}
```
is loaded as:
```python
config.poll_interval_s = 5.0  // New field name
config.polling_interval_seconds  // Compatibility property
```

## Security Notes

- Passwords/API keys should not be stored in config.json (use environment variables or OS keyring)
- Config file has default permissions (user-readable/writable)
- HTTPS URLs are validated but no certificate pinning is performed
- Network requests use 10s timeout to prevent hanging

## Future Enhancements

Potential future additions:
- [ ] API key/password storage (via OS keyring)
- [ ] Multiple printer profiles with quick-switch
- [ ] Config import/export
- [ ] Advanced settings UI (polling interval, icon style, etc.)
- [ ] Config validation on startup with user prompts
- [ ] Automatic printer discovery (mDNS)
