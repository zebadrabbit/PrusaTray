# PrusaTray

Windows system tray application for monitoring Prusa printers via PrusaLink and OctoPrint. Shows live status, print progress, and estimated time remaining.

## Preview

<img width="178" height="179" alt="screenshot" src="https://github.com/user-attachments/assets/b22cd316-75f1-4005-95ea-82b692401a2d" />

*System tray icon with progress ring indicator and detailed tooltip showing printer status, print progress, and estimated time remaining.*

## Features

- **Tray-only interface**: No windows, runs entirely in the system tray
- **Config UI**: Set printer URL directly from tray menu - no manual file editing
- **Hot-swapping**: Switch from demo to real printer without restarting app
- **Secure Authentication**: 
  - Digest auth (username + password) and API key support
  - Passwords stored securely in Windows Credential Manager (never in config file)
  - Connection testing before saving credentials
  - Graceful auth failure handling (401/403)
- **Dynamic icons**: 
  - Multi-size support (16, 20, 24, 32, 48, 64 px)
  - Ring progress indicator with auto-scaling
  - Status-specific overlays (pause `||`, alert `!`)
  - Icon caching (99% render reduction)
  - Anti-aliasing and transparency
- **Status colors**: Different colors for idle, printing, paused, error, and offline states
- **Rich tooltips**: Shows status, progress, ETA, job name, temperatures, and last error
- **Robust polling**: 
  - Non-blocking async requests (QNetworkAccessManager)
  - Never freezes UI thread
  - 5s read timeout per request
  - Exponential backoff with jitter on failures (3s → 30s)
  - Automatic recovery when printer comes back online
  - No request spam when offline
- **Demo mode**: Built-in simulation when no printer is configured
- **Configurable**: Polling interval and printer URL stored in config file
- **Well-tested**: 86 comprehensive unit tests covering all backends and edge cases

## Security & Privacy

- **Credential storage**: Passwords and API keys are stored in Windows Credential Manager via the `keyring` library—never in plaintext config files
- **Local network only**: The app polls your printer directly on your local network with no external connections
- **No telemetry**: No data collection, tracking, or analytics of any kind
- **Open source**: All code is available for inspection in this repository

## Releases

Download the latest `PrusaTray.exe` from the [Releases page](https://github.com/zebadrabbit/PrusaTray/releases). No installation required—just run the executable.

**Note:** Windows SmartScreen may show a warning on first run since the executable is not code-signed. This is expected for unsigned applications. Click "More info" → "Run anyway" to proceed.

For ongoing use, you'll need to manually download new versions from the Releases page when they become available.

## Installation

### For Development

1. Clone the repository
2. Create virtual environment:
```powershell
python -m venv .venv
```

3. Activate virtual environment:
```powershell
# PowerShell
.\.venv\Scripts\Activate.ps1
```
```cmd
# CMD
.\.venv\Scripts\activate.bat
```

4. Install dependencies:
```powershell
pip install -r requirements.txt
```

### For End Users (Windows Executable)

Download the latest `PrusaTray.exe` from releases and run it - no installation needed!

## Running

### Development Mode

Run from source:
```powershell
python -m tray_prusa
```

### Standalone Executable

Simply double-click `PrusaTray.exe` or run from PowerShell:
```powershell
.\dist\PrusaTray.exe
```

## Building Windows Executable

To create a standalone `.exe` file:

```powershell
.\build_windows.ps1
```

This will:
1. Create/activate virtual environment
2. Install all dependencies
3. Run smoke tests
4. Build `PrusaTray.exe` using PyInstaller
5. Output to `dist\PrusaTray.exe`

**Build options:**
```powershell
# Clean build (removes previous builds)
.\build_windows.ps1 -Clean

# Skip tests (faster build)
.\build_windows.ps1 -SkipTests

# Both
.\build_windows.ps1 -Clean -SkipTests
```

**Build requirements:**
- Python 3.10 or later
- Windows 10/11
- PowerShell 5.1 or later

## Configuration

### Quick Setup (Recommended)

1. Launch the app (starts in demo mode)
2. Right-click the tray icon
3. Select **"Set Printer URL..."** for basic setup
4. Or select **"Set Credentials..."** for authenticated printers:
   - Enter printer URL
   - Choose auth mode (none, digest, or apikey)
   - Enter username and password/API key
   - Click "Test Connection" to verify
   - Click "Save"
5. App switches to your printer immediately!

See [CONFIG_UI.md](CONFIG_UI.md) and [AUTHENTICATION.md](AUTHENTICATION.md) for details.

### Manual Configuration

Configuration is stored in `%LOCALAPPDATA%\PrusaTray\config.json`:

```json
{
  "printer_base_url": "http://192.168.1.100",
  "poll_interval_s": 3.0,
  "backend": "prusalink",
  "open_ui_path": "/",
  "icon_style": "ring",
  "username": "admin",
  "auth_mode": "digest"
}
```

- **printer_base_url**: Base URL of your Prusa printer. Set to `null` for demo mode.
- **poll_interval_s**: How often to poll the printer (default: 3.0 seconds, min: 1.0)
- **backend**: Printer API backend - `"demo"`, `"prusaconnect"`, `"prusalink"`, or `"octoprint"`
- **open_ui_path**: Path appended to base URL when opening printer UI (default: `"/"`)
- **icon_style**: Icon visualization style - `"ring"` or `"bar"`
- **username**: Username for authentication (optional)
- **auth_mode**: Authentication mode - `"none"`, `"digest"`, or `"apikey"` (default: `"none"`)
- **password_key**: Reference key for credential in keyring (e.g., `"prusalink:mk4-office"`) - **recommended**

**Security:** Passwords/API keys are stored securely in Windows Credential Manager via python-keyring, **NOT** in config file.

**Credential Management:**
- On first startup, if `password_key` is configured but credential is missing, you'll be prompted once
- Credentials can also be provided via environment variables (e.g., for headless deployments)
- See [CREDENTIAL_STORAGE.md](CREDENTIAL_STORAGE.md) for detailed documentation

### Backend-Specific Configuration

#### Demo Backend (Default)

For testing without a real printer:

```json
{
  "backend": "demo",
  "printer_base_url": null,
  "poll_interval_s": 3.0,
  "icon_style": "ring"
}
```

Simulates a 2-minute print cycle with pause and idle phases. No network calls - perfect for development and testing.

**Features:**
- No printer required
- Simulates realistic print progression
- Shows all printer states (PRINTING → PAUSED → IDLE)
- Safe to leave running continuously

---

#### PrusaConnect Backend

For **PrusaConnect** cloud monitoring:

```json
{
  "backend": "prusaconnect",
  "printer_base_url": "https://connect.prusa3d.com",
  "bearer_token": "your_bearer_token_here",
  "printer_id": "your_printer_id",
  "status_path": "/api/v1/status",
  "poll_interval_s": 10.0
}
```

**Required fields:**
- **bearer_token**: Bearer token from Prusa Connect account
- **printer_id**: Your printer's unique identifier

**Optional fields:**
- **status_path**: Custom API endpoint (defaults to `/api/v1/status`)
- **poll_interval_s**: Recommended 10+ seconds for cloud API (to avoid rate limiting)

**How to get your bearer token:**
1. Log in to [connect.prusa3d.com](https://connect.prusa3d.com)
2. Navigate to account settings → API settings
3. Generate an API token/bearer token
4. Copy and paste into `bearer_token` field

**Timeouts:** 5-second request timeout. Cloud API should respond quickly.

> **Note:** PrusaConnect uses bearer token authentication. The `auth_mode` and `username` settings are ignored.

---

#### PrusaLink Backend

For **PrusaLink** (local printer API with digest auth):

```json
{
  "backend": "prusalink",
  "printer_base_url": "http://192.168.1.100",
  "auth_mode": "digest",
  "username": "maker",
  "password_key": "prusalink:mk4-office",
  "poll_interval_s": 3.0,
  "icon_style": "ring"
}
```

**Required fields:**
- **printer_base_url**: Local IP address of your Prusa printer (e.g., `http://192.168.1.100`)
- **auth_mode**: Set to `"digest"` for PrusaLink
- **username**: PrusaLink username (default is `"maker"`)
- **password_key**: Reference name for secure credential storage

**Features:**
- Automatic endpoint detection (tries `/api/v1/status` → falls back to `/api/job`)
- Digest authentication
- Supports both modern and legacy PrusaLink formats
- 5-second timeout for local network

**First-time setup:**
1. Configure as above with `password_key`
2. Start PrusaTray - you'll be prompted for the password
3. Password is stored securely in Windows Credential Manager
4. Future startups retrieve it automatically

---

#### OctoPrint Backend

For **OctoPrint** (API key authentication):

```json
{
  "backend": "octoprint",
  "printer_base_url": "http://192.168.1.200",
  "auth_mode": "apikey",
  "username": "octoprint-api",
  "password_key": "octoprint:mk3s-garage",
  "poll_interval_s": 3.0,
  "icon_style": "ring"
}
```

**Required fields:**
- **printer_base_url**: OctoPrint server URL (e.g., `http://192.168.1.200` or `http://octopi.local`)
- **auth_mode**: Set to `"apikey"` for OctoPrint
- **username**: Descriptive name (not used by OctoPrint, but required for credential storage)
- **password_key**: Reference name for API key storage

**How to get your API key:**
1. Open OctoPrint web interface
2. Settings → Application Keys → Generate
3. Copy the generated API key
4. Store it via:
   ```python
   from tray_prusa.keyring_util import set_secret
   set_secret("octoprint:mk3s-garage", "YOUR_API_KEY_HERE")
   ```
   Or let PrusaTray prompt you on first startup

**Features:**
- Uses `/api/job` endpoint
- API key authentication via `X-Api-Key` header
- 5-second timeout for local network
- Supports state as string or dict format

---

### Quick Backend Comparison

| Backend | Network | Auth | Timeout | Endpoints |
|---------|---------|------|---------|-----------|
| **demo** | None | None | N/A | N/A - simulated |
| **prusaconnect** | Cloud | Bearer token | 5s | `/api/v1/status` |
| **prusalink** | Local | Digest | 5s | `/api/v1/status` + `/api/job` fallback |
| **octoprint** | Local | API key | 5s | `/api/job` |

### Backend Swapping

Changing backends requires only a config change:

```json
// Switch from demo to PrusaLink:
{
  "backend": "prusalink",
  "printer_base_url": "http://192.168.1.100",
  "auth_mode": "digest",
  "username": "maker",
  "password_key": "prusalink:office"
}
```

No code changes needed! See [ADAPTER_ARCHITECTURE.md](ADAPTER_ARCHITECTURE.md) for details.

## Demo Mode

When `printer_base_url` is `null` or not set, the app runs in demo mode, simulating:
- A 2-minute print job with progress
- A 10-second pause state
- A 20-second idle state
- Then repeats the cycle

## Tray Menu

Right-click the tray icon for:
- **Open printer UI**: Opens printer web interface (disabled in demo mode)
- **Refresh now**: Triggers immediate poll
- **Quit**: Exit the application

## Project Structure

```
tray_prusa/
├── __init__.py          # Package initialization
├── __main__.py          # Module entry point
├── main.py              # Application setup and event loop
├── tray.py              # QSystemTrayIcon + menu + tooltip
├── icon.py              # Dynamic icon generation (ring/bar)
├── poller.py            # Backend-agnostic polling with backoff
├── adapters.py          # All adapter implementations (Demo, PrusaConnect, PrusaLink, OctoPrint)
├── adapter_factory.py   # Factory for creating adapters based on config
├── models.py            # Data classes (PrinterState, AppConfig, PrinterStatus)
├── config.py            # Configuration management
├── keyring_util.py      # Secure credential storage utilities
└── logging_setup.py     # Logging configuration

tests/
├── test_demo_adapter.py      # Demo adapter tests (5 tests)
├── test_prusalink.py         # PrusaLink parser tests (12 tests)
├── test_octoprint.py         # OctoPrint parser tests (13 tests)
├── test_prusaconnect.py      # PrusaConnect parser tests (18 tests)
├── test_keyring_util.py      # Credential storage tests (19 tests)
├── test_fixtures.py          # Integration tests with real API responses (7 tests)
└── fixtures/                 # Real API response samples for testing
    ├── prusalink_v1_status_printing.json
    ├── prusalink_legacy_job_printing.json
    ├── octoprint_job_printing.json
    └── prusaconnect_status_sample.json
```

### Adapter Pattern

The app uses a **clean adapter abstraction** with full backend implementations:

- **BaseAdapter protocol**: All adapters implement `fetch_state() -> PrinterState`
- **Pure parsing functions**: Separate from network I/O for comprehensive unit testing
- **Factory pattern**: Single source of truth for backend selection
- **Normalized state**: All backends map to unified `PrinterState` structure
- **Comprehensive error handling**: 5s timeouts, graceful degradation, never crashes on malformed JSON

**Implemented Adapters:**
- ✅ **DemoAdapter**: Simulated printer for testing (5 tests)
- ✅ **PrusaConnectAdapter**: Cloud API with bearer token auth (18 tests)
- ✅ **PrusaLinkAdapter**: Local API with digest auth, dual endpoint support (12 tests)
- ✅ **OctoPrintAdapter**: OctoPrint REST API with API key auth (13 tests)

All adapters include real API fixture tests using actual response samples.

See [ADAPTER_ARCHITECTURE.md](ADAPTER_ARCHITECTURE.md) for complete architecture docs.

## Adding New Backends

See [ADAPTER_ARCHITECTURE.md](ADAPTER_ARCHITECTURE.md#-adding-a-new-backend) for step-by-step guide.

**Key points:**
- Write pure parsing function: `parse_X_state(data: Dict) -> PrinterState`
- Create adapter class (inherit from `HttpJsonAdapter`)
- Add case to `adapter_factory.create_adapter()`
- Update config: `backend: "your_backend"`

**No UI changes needed!**

## Testing

All backends have comprehensive test coverage (86 tests total):
- **12 tests**: PrusaLink parser (both v1 and legacy formats)
- **13 tests**: OctoPrint parser
- **18 tests**: PrusaConnect parser
- **19 tests**: Credential storage (keyring integration)
- **7 tests**: Real API fixture integration tests
- **5 tests**: Demo adapter
- **12 tests**: Parser edge cases

### Running Tests

Run all unit tests:
```powershell
python -m unittest discover tests -v
```

Run specific test modules:
```powershell
# Test specific backend
python -m unittest tests.test_prusalink -v
python -m unittest tests.test_octoprint -v
python -m unittest tests.test_prusaconnect -v

# Test credential storage
python -m unittest tests.test_keyring_util -v

# Test fixtures
python -m unittest tests.test_fixtures -v
```

### Icon Renderer Test
Generate test icons for visual inspection:
```powershell
python -m tray_prusa.icon
```

This creates 48 PNG files in `icon_test_output/` showing all status types and progress levels at multiple sizes. See [ICON_RENDERER.md](ICON_RENDERER.md) for details.

### Manual Testing
See [TESTING_CONFIG_UI.md](TESTING_CONFIG_UI.md) for comprehensive manual testing procedures.

## Troubleshooting

### Build Issues

#### "PyInstaller not found"
Install dependencies:
```powershell
pip install -r requirements.txt
```

#### Build fails with import errors
Clean build and try again:
```powershell
.\build_windows.ps1 -Clean
```

#### Executable size is very large (>100 MB)
This is normal for PyInstaller builds. The executable includes:
- Python runtime
- PySide6 Qt libraries
- All dependencies

To reduce size, consider:
- Using `--onedir` instead of `--onefile` (faster startup, smaller total size)
- Using UPX compression (may trigger antivirus warnings)

### Runtime Issues

#### "VCRUNTIME140.dll not found"
Install Microsoft Visual C++ Redistributable:
- Download from: https://aka.ms/vs/17/release/vc_redist.x64.exe
- Or install via Windows Update

#### Tray icon doesn't appear
- Check Windows notification area settings
- Ensure "PrusaTray" is allowed to show notifications
- Try restarting Windows Explorer:
  ```powershell
  Stop-Process -Name explorer -Force
  ```

#### Firewall blocks network requests
- Add exception in Windows Firewall
- Or run as administrator (not recommended for normal use)

#### "Authentication failed" errors
- Verify credentials via "Configuration..." menu
- Use "Test Connection" to diagnose
- Check printer is accessible via browser first
- See [AUTHENTICATION.md](AUTHENTICATION.md) for details

#### App crashes on startup
Check logs in:
```
%LOCALAPPDATA%\PrusaTray\logs\
```

Common causes:
- Corrupted config file (delete `%LOCALAPPDATA%\PrusaTray\config.json`)
- Missing keyring backend (reinstall app)
- Network timeout (check printer connectivity)

#### Executable flagged by antivirus
This is a false positive common with PyInstaller builds. Solutions:
- Add exception in antivirus software
- Submit executable to antivirus vendor for whitelisting
- Build from source and compare checksums

### Development Issues

#### Import errors when running from source
Activate virtual environment:
```powershell
.\.venv\Scripts\Activate.ps1
```

#### Tests fail
Ensure all dependencies installed:
```powershell
pip install -r requirements.txt
```

Run tests individually to identify issue:
```powershell
python -m unittest test_parser -v
python test_config_ui.py
python test_auth.py
```

#### "keyring not available" warnings
Install keyring:
```powershell
pip install keyring
```

On Windows, keyring uses Windows Credential Manager (built-in).

## Code Quality

The codebase follows strict code quality standards:

- **Formatting**: [Black](https://github.com/psf/black) code formatter (line length 100)
- **Linting**: [Ruff](https://github.com/astral-sh/ruff) for fast Python linting
- **Type hints**: Full type annotations throughout codebase
- **Testing**: 86 comprehensive unit tests covering all adapters

To check code quality:
```powershell
# Check formatting
black --check tray_prusa/ tests/

# Run linter
ruff check tray_prusa/ tests/

# Run all tests
python -m unittest discover tests -v
```

To auto-fix issues:
```powershell
# Format code
black tray_prusa/ tests/

# Fix linting issues
ruff check --fix tray_prusa/ tests/
```

## Documentation

- **[README.md](README.md)** - This file (overview and quick start)
- **[AUTHENTICATION.md](AUTHENTICATION.md)** - Authentication system documentation
- **[CONFIG_UI.md](CONFIG_UI.md)** - Configuration UI user guide
- **[CONFIG_UI_SUMMARY.md](CONFIG_UI_SUMMARY.md)** - Config UI implementation details
- **[ADAPTER_ARCHITECTURE.md](ADAPTER_ARCHITECTURE.md)** - Backend adapter pattern guide
- **[BACKEND_SWAP_VALIDATION.md](BACKEND_SWAP_VALIDATION.md)** - Backend switching validation
- **[CREDENTIAL_STORAGE.md](CREDENTIAL_STORAGE.md)** - Secure credential management guide
- **[ICON_RENDERER.md](ICON_RENDERER.md)** - Icon rendering system documentation
- **[ROBUSTNESS_TESTING.md](ROBUSTNESS_TESTING.md)** - Polling robustness testing guide
- **[TESTING_CONFIG_UI.md](TESTING_CONFIG_UI.md)** - Manual config UI testing procedures

## License

MIT License - see [LICENSE](LICENSE) file for details.
