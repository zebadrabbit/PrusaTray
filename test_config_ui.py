"""Test config UI functionality."""

import sys
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication

from tray_prusa.config import ConfigManager
from tray_prusa.models import AppConfig


def test_url_validation():
    """Test URL validation."""
    print("Testing URL validation...")
    
    # Valid URLs
    assert ConfigManager.validate_url("http://192.168.1.100")
    assert ConfigManager.validate_url("https://printer.local")
    assert ConfigManager.validate_url("http://192.168.1.100:8080")
    assert ConfigManager.validate_url("https://connect.prusa3d.com")
    
    # Invalid URLs
    assert not ConfigManager.validate_url("")
    assert not ConfigManager.validate_url("not a url")
    assert not ConfigManager.validate_url("192.168.1.100")  # Missing scheme
    assert not ConfigManager.validate_url("ftp://invalid.com")  # Wrong scheme
    
    print("✓ URL validation tests passed")


def test_config_load_save():
    """Test config load and save with new fields."""
    print("\nTesting config load/save...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        
        # Create config manager
        cm = ConfigManager(config_path)
        
        # Create and save config
        config = AppConfig(
            printer_base_url="http://192.168.1.100",
            poll_interval_s=5.0,
            backend="prusalink",
            open_ui_path="/ui",
            icon_style="ring"
        )
        
        cm.save(config)
        assert config_path.exists()
        print(f"  Saved config to {config_path}")
        
        # Load config
        cm2 = ConfigManager(config_path)
        loaded_config = cm2.load()
        
        assert loaded_config.printer_base_url == "http://192.168.1.100"
        assert loaded_config.poll_interval_s == 5.0
        assert loaded_config.backend == "prusalink"
        assert loaded_config.open_ui_path == "/ui"
        assert loaded_config.icon_style == "ring"
        
        print("✓ Config load/save tests passed")


def test_malformed_config():
    """Test that malformed config doesn't crash."""
    print("\nTesting malformed config handling...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        
        # Write malformed JSON
        config_path.write_text("{invalid json", encoding='utf-8')
        
        # Should not crash, should use defaults
        cm = ConfigManager(config_path)
        config = cm.load()
        
        assert config.backend == "demo"
        assert config.poll_interval_s == 3.0
        print("✓ Malformed config handled gracefully")


def test_invalid_url_in_config():
    """Test that invalid URL in config is rejected."""
    print("\nTesting invalid URL in config...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        
        # Write config with invalid URL
        config_path.write_text('{"printer_base_url": "not a url"}', encoding='utf-8')
        
        # Should load but reject the URL
        cm = ConfigManager(config_path)
        config = cm.load()
        
        assert config.printer_base_url is None  # Invalid URL should be rejected
        print("✓ Invalid URL rejected correctly")


def test_backward_compatibility():
    """Test backward compatibility with old polling_interval_seconds field."""
    print("\nTesting backward compatibility...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        
        # Write old-style config
        config_path.write_text('{"polling_interval_seconds": 7.0}', encoding='utf-8')
        
        # Should load with new field name
        cm = ConfigManager(config_path)
        config = cm.load()
        
        assert config.poll_interval_s == 7.0
        assert config.polling_interval_seconds == 7.0  # Compatibility property
        print("✓ Backward compatibility works")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Config UI Tests")
    print("=" * 60)
    
    # Create QApplication for Qt tests (needed for QInputDialog, etc.)
    app = QApplication(sys.argv)
    
    try:
        test_url_validation()
        test_config_load_save()
        test_malformed_config()
        test_invalid_url_in_config()
        test_backward_compatibility()
        
        print("\n" + "=" * 60)
        print("✓ All tests passed!")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
