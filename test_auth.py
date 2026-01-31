"""Test authentication functionality."""

import sys
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication

from tray_prusa.config import ConfigManager
from tray_prusa.models import AppConfig
from tray_prusa.keyring_util import set_password, get_password, delete_password, is_keyring_available
from tray_prusa.adapters import build_auth_headers


def test_keyring_availability():
    """Test keyring is available."""
    print("Testing keyring availability...")
    assert is_keyring_available(), "keyring library not available"
    print("✓ Keyring is available")


def test_password_storage():
    """Test password storage and retrieval."""
    print("\nTesting password storage...")
    
    test_url = "http://test-printer.local"
    test_username = "testuser"
    test_password = "testpassword123"
    
    # Store password
    assert set_password(test_url, test_username, test_password), "Failed to store password"
    print(f"  Stored password for {test_username}@{test_url}")
    
    # Retrieve password
    retrieved = get_password(test_url, test_username)
    assert retrieved == test_password, f"Password mismatch: expected '{test_password}', got '{retrieved}'"
    print(f"  Retrieved password successfully")
    
    # Delete password
    assert delete_password(test_url, test_username), "Failed to delete password"
    print(f"  Deleted password")
    
    # Verify deleted
    retrieved_after = get_password(test_url, test_username)
    assert retrieved_after is None, "Password still exists after deletion"
    print(f"  Verified password was deleted")
    
    print("✓ Password storage tests passed")


def test_auth_headers_none():
    """Test auth headers with no auth."""
    print("\nTesting auth headers (none mode)...")
    
    config = AppConfig(
        printer_base_url="http://192.168.1.100",
        auth_mode="none"
    )
    
    headers = build_auth_headers(config)
    assert headers == {}, f"Expected empty headers, got {headers}"
    
    print("✓ No auth headers added for 'none' mode")


def test_auth_headers_apikey():
    """Test auth headers with API key."""
    print("\nTesting auth headers (apikey mode)...")
    
    test_url = "http://192.168.1.100"
    test_username = "apiuser"
    test_apikey = "test-api-key-12345"
    
    # Store API key
    set_password(test_url, test_username, test_apikey)
    
    try:
        config = AppConfig(
            printer_base_url=test_url,
            username=test_username,
            auth_mode="apikey"
        )
        
        headers = build_auth_headers(config)
        assert b"X-Api-Key" in headers, "X-Api-Key header not found"
        assert headers[b"X-Api-Key"] == test_apikey.encode('utf-8'), "API key mismatch"
        
        print(f"  Added X-Api-Key header: {test_apikey[:10]}...")
        print("✓ API key auth headers added correctly")
        
    finally:
        delete_password(test_url, test_username)


def test_auth_headers_digest():
    """Test auth headers with digest auth."""
    print("\nTesting auth headers (digest mode)...")
    
    test_url = "http://192.168.1.100"
    test_username = "digestuser"
    test_password = "digestpass"
    
    # Store password
    set_password(test_url, test_username, test_password)
    
    try:
        config = AppConfig(
            printer_base_url=test_url,
            username=test_username,
            auth_mode="digest"
        )
        
        headers = build_auth_headers(config)
        assert b"Authorization" in headers, "Authorization header not found"
        
        # Should contain Basic auth as fallback
        auth_value = headers[b"Authorization"].decode('utf-8')
        assert auth_value.startswith("Basic "), "Expected Basic auth header"
        
        print(f"  Added Authorization header: {auth_value[:20]}...")
        print("✓ Digest auth headers added correctly")
        
    finally:
        delete_password(test_url, test_username)


def test_config_with_auth():
    """Test config load/save with auth fields."""
    print("\nTesting config with auth fields...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        
        # Create config with auth
        config = AppConfig(
            printer_base_url="http://192.168.1.100",
            username="testuser",
            auth_mode="apikey",
            poll_interval_s=5.0,
            backend="prusalink"
        )
        
        # Save config
        cm = ConfigManager(config_path)
        cm.save(config)
        
        # Verify file content
        import json
        with open(config_path, 'r') as f:
            data = json.load(f)
        
        assert data["username"] == "testuser"
        assert data["auth_mode"] == "apikey"
        assert "password" not in data, "Password should NOT be in config file"
        assert "api_key" not in data, "API key should NOT be in config file"
        
        print("  Config file does NOT contain password (✓ secure)")
        
        # Load config
        cm2 = ConfigManager(config_path)
        loaded = cm2.load()
        
        assert loaded.username == "testuser"
        assert loaded.auth_mode == "apikey"
        
        print("✓ Config with auth fields works correctly")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Authentication Tests")
    print("=" * 60)
    
    # Create QApplication for Qt tests
    app = QApplication(sys.argv)
    
    try:
        test_keyring_availability()
        test_password_storage()
        test_auth_headers_none()
        test_auth_headers_apikey()
        test_auth_headers_digest()
        test_config_with_auth()
        
        print("\n" + "=" * 60)
        print("✓ All authentication tests passed!")
        print("=" * 60)
        
        return 0
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
