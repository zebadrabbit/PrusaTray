# Secure Credential Storage

PrusaTray uses **python-keyring** to store passwords and API keys securely in Windows Credential Manager. Credentials are **never** stored in plaintext in the config file.

## Features

- **Secure storage**: Credentials stored in Windows Credential Manager via keyring
- **Environment variable fallback**: Works in headless/CI environments
- **Optional dependency**: App works even if keyring is not installed
- **Startup prompts**: Automatically prompts for missing credentials
- **Dual lookup methods**: Supports both legacy (URL+username) and modern (password_key) approaches

## Configuration

### Modern Method (password_key)

Configure with a reference key in `config.json`:

```json
{
  "printer_base_url": "http://192.168.1.100",
  "backend": "prusalink",
  "auth_mode": "digest",
  "username": "maker",
  "password_key": "prusalink:mk4-office"
}
```

**On first startup**, if the credential is not found in keyring or environment:
1. A dialog prompts you to enter the password
2. Credential is stored in Windows Credential Manager under service "PrusaTray"
3. Future startups retrieve it automatically

### Legacy Method (URL + username)

Still supported for backward compatibility:

```json
{
  "printer_base_url": "http://192.168.1.100",
  "backend": "prusalink",
  "auth_mode": "digest",
  "username": "maker"
}
```

Credentials are stored as `{printer_base_url}:{username}` in keyring.

## Environment Variable Fallback

If running **headless** (e.g., as a service) or if keyring is unavailable, credentials can be provided via environment variables:

```powershell
# Set environment variable for password_key "prusalink:mk4-office"
$env:PRUSATRAY_PASSWORD_PRUSALINK_MK4_OFFICE = "my_secret_password"

# Or for URL-like keys
$env:PRUSATRAY_PASSWORD_HTTP_192_168_1_100_MAKER = "my_password"
```

**Key sanitization rules:**
- Non-alphanumeric characters → underscores
- Converted to UPPERCASE
- Leading/trailing underscores removed

Examples:
- `prusalink:mk4-office` → `PRUSATRAY_PASSWORD_PRUSALINK_MK4_OFFICE`
- `http://192.168.1.100:maker` → `PRUSATRAY_PASSWORD_HTTP_192_168_1_100_MAKER`

## Credential Lookup Priority

When authentication is enabled, PrusaTray looks for credentials in this order:

1. **New method (password_key)**:
   - Windows Credential Manager (via keyring) using `password_key` as the key
   - Environment variable `PRUSATRAY_PASSWORD_<SANITIZED_KEY>`

2. **Legacy fallback (URL + username)**:
   - Windows Credential Manager using `{printer_base_url}:{username}` as the key
   - No env var fallback for legacy method

## API Reference

### keyring_util Module

#### `get_secret(key: str) -> Optional[str]`

Retrieve secret from keyring or environment variable.

```python
from tray_prusa.keyring_util import get_secret

password = get_secret("prusalink:mk4-office")
# Tries keyring first, then env var PRUSATRAY_PASSWORD_PRUSALINK_MK4_OFFICE
```

#### `set_secret(key: str, value: str) -> bool`

Store secret in keyring.

```python
from tray_prusa.keyring_util import set_secret

success = set_secret("prusalink:mk4-office", "my_password")
```

#### `prompt_for_credential(key: str, parent=None) -> Optional[str]`

Show Qt dialog to prompt user for credential.

```python
from tray_prusa.keyring_util import prompt_for_credential

credential = prompt_for_credential("prusalink:mk4-office")
if credential:
    set_secret("prusalink:mk4-office", credential)
```

## Manual Credential Management

### Store a credential manually

```python
from tray_prusa.keyring_util import set_secret

set_secret("prusalink:mk4-office", "my_secret_password")
```

### Retrieve a credential

```python
from tray_prusa.keyring_util import get_secret

password = get_secret("prusalink:mk4-office")
print(f"Password: {password}")
```

### Delete a credential

```python
from tray_prusa.keyring_util import delete_password

# Legacy method
delete_password("http://192.168.1.100", "maker")
```

Or use Windows Credential Manager GUI:
1. Press `Win+R`, type `control /name Microsoft.CredentialManager`
2. Find "PrusaTray" entries under "Windows Credentials"
3. Click entry → Remove

## Running Without Keyring

If keyring is **not installed** or **unavailable**:

1. PrusaTray logs a warning: `"keyring library not available - credentials will only be available via environment variables"`
2. Credential prompts won't appear
3. **Environment variables are the only option**

Install keyring:
```powershell
pip install keyring
```

## Security Notes

- **Windows Credential Manager**: Industry-standard secure storage on Windows
- **Encrypted at rest**: Credentials are encrypted by Windows
- **User-scoped**: Only accessible by the logged-in user
- **No plaintext**: Config file never contains passwords
- **Environment variables**: Less secure (visible in process list), use only when keyring unavailable

## Troubleshooting

### "Password not found in keyring"

**Cause**: Credential not stored yet.

**Solution**:
1. Run app - it will prompt you
2. Or set manually:
   ```python
   from tray_prusa.keyring_util import set_secret
   set_secret("prusalink:mk4-office", "your_password")
   ```
3. Or set env var:
   ```powershell
   $env:PRUSATRAY_PASSWORD_PRUSALINK_MK4_OFFICE = "your_password"
   ```

### "keyring library not available"

**Cause**: python-keyring not installed.

**Solution**:
```powershell
pip install keyring
```

Or use environment variables as fallback.

### No credential prompt appears

**Possible causes**:
1. Running headless (no QApplication) → Use env vars
2. `password_key` not configured in config.json
3. Credential already exists in keyring/env var

### Credential prompt shows wrong key name

Edit `config.json` and update `password_key`:
```json
{
  "password_key": "prusalink:mk4-office"  // ← Descriptive name
}
```

## Examples

### Example 1: PrusaLink with password_key

**config.json:**
```json
{
  "printer_base_url": "http://192.168.1.100",
  "backend": "prusalink",
  "auth_mode": "digest",
  "username": "maker",
  "password_key": "prusalink:mk4-office"
}
```

**First run:**
- Dialog prompts: "Enter credential for 'prusalink:mk4-office'"
- You enter the password
- Stored in Windows Credential Manager

**Subsequent runs:**
- Password retrieved automatically from keyring
- No prompt

### Example 2: OctoPrint with API key

**config.json:**
```json
{
  "printer_base_url": "http://192.168.1.200",
  "backend": "octoprint",
  "auth_mode": "apikey",
  "username": "octoprint-api",
  "password_key": "octoprint:office-mk3s"
}
```

**Store API key:**
```python
from tray_prusa.keyring_util import set_secret
set_secret("octoprint:office-mk3s", "A1B2C3D4E5F6G7H8")
```

### Example 3: Headless/Docker deployment

**Docker run:**
```bash
docker run -e PRUSATRAY_PASSWORD_PRUSALINK_MK4_OFFICE=secret123 prusa-tray
```

**Systemd service:**
```ini
[Service]
Environment="PRUSATRAY_PASSWORD_PRUSALINK_MK4_OFFICE=secret123"
ExecStart=/usr/bin/python -m tray_prusa
```

## Migration from Legacy to password_key

**Old config:**
```json
{
  "printer_base_url": "http://192.168.1.100",
  "auth_mode": "digest",
  "username": "maker"
}
```
Credential stored as: `http://192.168.1.100:maker`

**New config:**
```json
{
  "printer_base_url": "http://192.168.1.100",
  "auth_mode": "digest",
  "username": "maker",
  "password_key": "prusalink:mk4-office"  // ← Add this
}
```

**Migration steps:**
1. Retrieve old credential:
   ```python
   from tray_prusa.keyring_util import get_password
   old_pw = get_password("http://192.168.1.100", "maker")
   ```
2. Store with new key:
   ```python
   from tray_prusa.keyring_util import set_secret
   set_secret("prusalink:mk4-office", old_pw)
   ```
3. Update config.json with `password_key`
4. Restart app

Or just delete the old credential and let the app prompt you on next startup.
