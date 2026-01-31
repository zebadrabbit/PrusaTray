# Manual Testing Guide for Config UI

## Test 1: Initial Setup from Demo Mode

1. Launch the app:
   ```bash
   python -m tray_prusa
   ```

2. Verify the tray icon appears in the system tray (bottom-right corner, near the clock)

3. Verify the app starts in demo mode:
   - Check console output: `Creating adapter for backend: demo`
   - Icon should show progress cycling through demo states

4. Right-click the tray icon

5. Verify menu contains:
   - ✓ Open printer UI (should be **disabled**)
   - ✓ Refresh now
   - ✓ Separator
   - ✓ **Set Printer URL...** ← New menu item
   - ✓ Separator
   - ✓ Quit

## Test 2: Set Invalid URL

1. Click **"Set Printer URL..."**

2. Enter an invalid URL: `not a url`

3. Click OK

4. Verify error dialog appears: "Invalid URL - Please enter a valid HTTP or HTTPS URL"

5. Verify config is NOT changed (still demo mode)

## Test 3: Set Valid URL (PrusaLink)

1. Click **"Set Printer URL..."**

2. Enter: `http://192.168.1.100`

3. Click OK

4. Verify success notification appears:
   - Title: "Configuration Updated"
   - Message: "Printer URL set to http://192.168.1.100" + "Backend: prusalink"

5. Check console output:
   - `Saved new config: URL=http://192.168.1.100, backend=prusalink`
   - `Configuration changed: backend=prusalink, URL=http://192.168.1.100`
   - `Creating adapter for backend: prusalink`
   - `Adapter hot-swapped successfully`

6. Verify config file was created:
   ```bash
   type %LOCALAPPDATA%\PrusaTray\config.json
   ```
   Should show:
   ```json
   {
     "printer_base_url": "http://192.168.1.100",
     "poll_interval_s": 3.0,
     "backend": "prusalink",
     "open_ui_path": "/",
     "icon_style": "ring"
   }
   ```

7. Right-click tray icon again

8. Verify **"Open printer UI"** is now **enabled**

## Test 4: Open Printer UI

1. Click **"Open printer UI"**

2. Verify browser opens to: `http://192.168.1.100/`

## Test 5: Change URL (Hot-Swap)

1. Click **"Set Printer URL..."**

2. Enter different URL: `http://192.168.1.200:8080`

3. Click OK

4. Verify notification shows new URL and backend

5. Verify console shows hot-swap occurred

6. Verify **app did NOT restart** (no "PrusaTray starting..." message)

## Test 6: Return to Demo Mode

1. Click **"Set Printer URL..."**

2. Clear the text field (empty string)

3. Click OK

4. Verify notification: "Switched to demo mode"

5. Check console: `backend=demo`

6. Verify **"Open printer UI"** is **disabled** again

7. Verify demo mode cycling resumes

## Test 7: Cancel Dialog

1. Click **"Set Printer URL..."**

2. Enter some text

3. Click **Cancel**

4. Verify config is NOT changed

5. Verify no notification appears

## Test 8: Auto-Detection

Test that backend is auto-detected correctly:

| URL | Expected Backend |
|-----|------------------|
| `http://printer.local:8080` | `prusalink` (port 8080) |
| `http://192.168.1.100/prusalink` | `prusalink` (contains "prusalink") |
| `http://connect.prusa3d.com` | `prusaconnect` (contains "prusaconnect") |
| `http://printer.local:5000` | `octoprint` (port 5000) |
| `http://192.168.1.100/octoprint` | `octoprint` (contains "octoprint") |
| `http://192.168.1.100` | `prusalink` (default for unknown) |

## Test 9: Malformed Config Recovery

1. Quit the app

2. Manually corrupt the config file:
   ```bash
   echo "{invalid json" > %LOCALAPPDATA%\PrusaTray\config.json
   ```

3. Launch the app again:
   ```bash
   python -m tray_prusa
   ```

4. Verify console shows:
   - `Malformed JSON in config: ... Using defaults.`

5. Verify app starts in demo mode (does NOT crash)

6. Verify config file still exists but is invalid

7. Use "Set Printer URL..." to fix it

8. Verify config is now valid JSON

## Test 10: URL Validation Edge Cases

Test these URLs in "Set Printer URL..." dialog:

| URL | Should Accept? | Reason |
|-----|---------------|--------|
| `http://192.168.1.100` | ✓ Yes | Valid HTTP |
| `https://printer.local` | ✓ Yes | Valid HTTPS |
| `http://printer.local:8080/path` | ✓ Yes | Valid with path and port |
| `192.168.1.100` | ✗ No | Missing scheme |
| `ftp://192.168.1.100` | ✗ No | Wrong scheme |
| `not a url` | ✗ No | Invalid format |
| (empty string) | ✓ Yes | Switches to demo |

## Test 11: Persistence

1. Set a printer URL

2. Quit the app

3. Launch the app again

4. Verify it remembers the URL (no "Set Printer URL..." needed)

5. Verify it connects to the same backend

## Expected Results Summary

✅ All tests should pass without:
- Crashes
- UI freezing
- Config corruption
- Manual file editing required

✅ User experience should be:
- Simple: Just enter URL, everything else auto-detected
- Immediate: No app restart needed
- Safe: Invalid inputs rejected with clear errors
- Transparent: Notifications confirm changes

## Troubleshooting

If tests fail:

1. **Check console output** for error messages

2. **Check config file**:
   ```bash
   type %LOCALAPPDATA%\PrusaTray\config.json
   ```

3. **Delete config to reset**:
   ```bash
   del %LOCALAPPDATA%\PrusaTray\config.json
   ```

4. **Run unit tests**:
   ```bash
   python test_config_ui.py
   ```

5. **Check Python/Qt versions**:
   ```bash
   python --version
   python -c "from PySide6.QtCore import qVersion; print(qVersion())"
   ```
