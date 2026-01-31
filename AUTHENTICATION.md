# Authentication Documentation

## Overview

PrusaTray supports secure authentication for printer APIs using two modes:
- **Digest Authentication**: Username + password (HTTP Digest Auth)
- **API Key**: X-Api-Key header authentication

Passwords and API keys are stored **securely** in Windows Credential Manager using the `keyring` library, **not** in the config file.

## Authentication Modes

### None (Default)
No authentication required. Used for:
- Demo mode
- Printers without authentication
- Local development

**Config:**
```json
{
  "auth_mode": "none"
}
```

### Digest Authentication
Username and password authentication using HTTP Digest Auth (or Basic Auth fallback).

**Use cases:**
- PrusaLink with authentication enabled
- OctoPrint with authentication

**Config:**
```json
{
  "auth_mode": "digest",
  "username": "admin"
}
```

**Password storage:** Stored securely in Windows Credential Manager

### API Key Authentication
Uses `X-Api-Key` header for authentication.

**Use cases:**
- Prusa Connect
- OctoPrint with API key
- Custom printer APIs

**Config:**
```json
{
  "auth_mode": "apikey",
  "username": "api-user"
}
```

**API key storage:** Stored securely in Windows Credential Manager

## Setting Credentials

### Via UI (Recommended)

1. Right-click the tray icon
2. Select **"Set Credentials..."**
3. Enter printer details:
   - **Printer URL**: e.g., `http://192.168.1.100`
   - **Authentication Mode**: `none`, `digest`, or `apikey`
   - **Username**: Username or API key name
   - **Password/API Key**: Password or API key value (masked)
4. Click **"Test Connection"** to verify
5. Click **"Save"** to store credentials

### Manual Configuration

Edit `%LOCALAPPDATA%\PrusaTray\config.json`:

```json
{
  "printer_base_url": "http://192.168.1.100",
  "backend": "prusalink",
  "auth_mode": "digest",
  "username": "admin"
}
```

Then use Python to store password:
```python
from tray_prusa.keyring_util import set_password
set_password("http://192.168.1.100", "admin", "your_password")
```

## Security Features

### Secure Password Storage
- Passwords stored in **Windows Credential Manager**
- Uses `keyring` library (industry standard)
- Credentials encrypted by Windows
- **Never** stored in config file or logs
- Per-user storage (isolated from other Windows users)

### Key Format
Credentials are stored with the key:
```
Service: PrusaTray
Key: {printer_url}:{username}
```

Example: `http://192.168.1.100:admin`

### Viewing Stored Credentials
You can view/manage credentials in Windows:
1. Press Win+R
2. Type `control /name Microsoft.CredentialManager`
3. Look for "PrusaTray" entries under "Windows Credentials"

## Connection Testing

The "Test Connection" feature:
1. Builds authentication headers from entered credentials
2. Makes async GET request to `/api/v1/status`
3. Runs in background thread (UI never blocks)
4. Shows result in message box:
   - ✓ "Connection successful!" (HTTP 200)
   - ✗ "Authentication failed (HTTP 401/403)"
   - ✗ "Connection error: ..." (network issues)
   - ✗ "Connection timeout" (after 10 seconds)

**Test endpoint:** `{base_url}/api/v1/status`

## Authentication Flow

### Digest Mode
```
1. Load config → get username
2. Retrieve password from keyring
3. Build Authorization header: Basic {base64(username:password)}
4. Send request with Authorization header
5. Handle auth failures (401/403)
```

### API Key Mode
```
1. Load config → get username (API key name)
2. Retrieve API key from keyring
3. Build X-Api-Key header: {api_key}
4. Send request with X-Api-Key header
5. Handle auth failures (401/403)
```

## Error Handling

### Authentication Failures
When API returns 401 or 403:
- Printer state set to `ERROR`
- Tooltip shows: "Auth failed - check credentials"
- Error message: "Authentication failed (HTTP 401)"
- Polling continues (allows recovery after fixing credentials)

### Missing Credentials
If auth_mode is set but credentials missing:
- Warning logged: "Password not found in keyring"
- Request sent **without** authentication
- May succeed (if printer allows unauthenticated access)
- May fail with 401 (prompts user to set credentials)

### Network Errors
Handled separately from auth failures:
- Connection timeout
- DNS resolution failure
- Network unreachable
- etc.

## Configuration Examples

### PrusaLink with Digest Auth
```json
{
  "printer_base_url": "http://192.168.1.100",
  "backend": "prusalink",
  "auth_mode": "digest",
  "username": "maker"
}
```
Password stored in keyring: `http://192.168.1.100:maker`

### OctoPrint with API Key
```json
{
  "printer_base_url": "http://192.168.1.100:5000",
  "backend": "octoprint",
  "auth_mode": "apikey",
  "username": "octoprint-api"
}
```
API key stored in keyring: `http://192.168.1.100:5000:octoprint-api`

### Prusa Connect
```json
{
  "printer_base_url": "https://connect.prusa3d.com",
  "backend": "prusaconnect",
  "auth_mode": "apikey",
  "username": "connect-api"
}
```
API key stored in keyring: `https://connect.prusa3d.com:connect-api`

## Switching Authentication

### Change Password
1. Open "Set Credentials..."
2. Enter same URL and username
3. Enter new password
4. Click "Save"
5. Old password overwritten in keyring

### Change Auth Mode
1. Open "Set Credentials..."
2. Change authentication mode dropdown
3. Update username/password if needed
4. Click "Test Connection"
5. Click "Save"

### Remove Authentication
1. Open "Set Credentials..."
2. Select "none" auth mode
3. Click "Save"
4. Credentials remain in keyring but won't be used

### Delete Credentials
```python
from tray_prusa.keyring_util import delete_password
delete_password("http://192.168.1.100", "admin")
```

Or use Windows Credential Manager UI.

## Implementation Details

### Build Auth Headers
Pure function in `adapters.py`:
```python
def build_auth_headers(config: AppConfig) -> Dict[bytes, bytes]:
    """Build authentication headers based on config."""
    headers = {}
    
    if config.auth_mode == "apikey":
        api_key = keyring_util.get_password(config.printer_base_url, config.username)
        if api_key:
            headers[b"X-Api-Key"] = api_key.encode('utf-8')
    
    elif config.auth_mode == "digest":
        password = keyring_util.get_password(config.printer_base_url, config.username)
        if password:
            # Basic auth as fallback (full digest requires challenge/response)
            credentials = f"{config.username}:{password}"
            b64 = base64.b64encode(credentials.encode('utf-8')).decode('ascii')
            headers[b"Authorization"] = f"Basic {b64}".encode('utf-8')
    
    return headers
```

### HttpJsonAdapter
Updated to accept config and add auth headers:
```python
def fetch_state_async(self) -> None:
    request = QNetworkRequest(url)
    
    # Add auth headers
    if self.config:
        auth_headers = build_auth_headers(self.config)
        for header_name, header_value in auth_headers.items():
            request.setRawHeader(header_name, header_value)
    
    reply = self._network_manager.get(request)
```

### Auth Failure Handling
```python
def _handle_reply(self, reply: QNetworkReply) -> None:
    http_status = reply.attribute(HttpStatusCodeAttribute)
    
    if http_status == 401 or http_status == 403:
        # Return error state with auth failure message
        error_state = PrinterState(
            status=PrinterStatus.ERROR,
            error_message="Auth failed - check credentials"
        )
        self.state_fetched.emit(error_state)
```

## Troubleshooting

### "Authentication failed (HTTP 401)"
- Verify username is correct
- Verify password/API key is correct
- Check printer requires auth (some allow unauthenticated access)
- Try clearing credentials and re-entering

### "Password not found in keyring"
- Credentials not set via "Set Credentials..." dialog
- Manual config edit without storing password
- **Solution:** Use "Set Credentials..." dialog to store password

### Credentials not working after Windows update
- Windows Credential Manager may have been reset
- **Solution:** Re-enter credentials via "Set Credentials..." dialog

### "Test Connection" timeout
- Printer URL incorrect
- Printer offline/unreachable
- Network issues
- **Solution:** Verify printer is accessible via browser first

### API key auth not working
- Some printers expect different header name (e.g., `Authorization: Bearer {token}`)
- **Solution:** May need custom adapter implementation

## Best Practices

### Security
- ✅ Use "Set Credentials..." dialog (stores securely)
- ✅ Use strong passwords
- ✅ Use HTTPS when available (encrypts traffic)
- ❌ Don't manually edit config file for passwords
- ❌ Don't store passwords in plaintext anywhere

### Credential Management
- Test connection before saving
- Use unique passwords per printer
- Change passwords periodically
- Delete unused credentials from keyring

### Troubleshooting
- Check logs: `%LOCALAPPDATA%\PrusaTray\logs`
- Test with browser first
- Use "Test Connection" to verify
- Check Windows Event Viewer for credential manager issues

## API Reference

### keyring_util.py

#### `set_password(printer_url, username, password)`
Store password securely in Windows Credential Manager.

**Returns:** `bool` - True if successful

#### `get_password(printer_url, username)`
Retrieve password from Windows Credential Manager.

**Returns:** `Optional[str]` - Password if found, None otherwise

#### `delete_password(printer_url, username)`
Delete password from Windows Credential Manager.

**Returns:** `bool` - True if successful

#### `is_keyring_available()`
Check if keyring library is available.

**Returns:** `bool` - True if available

### adapters.py

#### `build_auth_headers(config)`
Build authentication headers dictionary.

**Returns:** `Dict[bytes, bytes]` - Header name -> header value

## Future Enhancements

Potential improvements:
- [ ] OAuth 2.0 support for cloud APIs
- [ ] Certificate-based authentication
- [ ] MQTT authentication
- [ ] Multi-factor authentication
- [ ] Automatic credential rotation
- [ ] Credential export/import (encrypted)
- [ ] Per-printer auth mode override
