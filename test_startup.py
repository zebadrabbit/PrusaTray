"""Test the startup utility module."""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from tray_prusa import startup_util


def test_startup_util():
    """Test basic startup utility functions."""
    print("Testing startup utility module...")
    
    # Test getting executable path
    exe_path = startup_util.get_executable_path()
    print(f"✓ Executable path: {exe_path}")
    
    # Check current startup status
    is_enabled = startup_util.is_startup_enabled()
    print(f"✓ Current startup status: {'Enabled' if is_enabled else 'Disabled'}")
    
    # Test enabling startup (will actually modify registry)
    print("\nTesting enable startup...")
    result = startup_util.set_startup_enabled(True)
    if result:
        print("✓ Successfully enabled startup")
        
        # Verify it was enabled
        if startup_util.is_startup_enabled():
            print("✓ Verified: Startup is enabled")
        else:
            print("✗ ERROR: Startup should be enabled but isn't")
    else:
        print("✗ Failed to enable startup (may need admin privileges)")
    
    # Test disabling startup
    print("\nTesting disable startup...")
    result = startup_util.set_startup_enabled(False)
    if result:
        print("✓ Successfully disabled startup")
        
        # Verify it was disabled
        if not startup_util.is_startup_enabled():
            print("✓ Verified: Startup is disabled")
        else:
            print("✗ ERROR: Startup should be disabled but isn't")
    else:
        print("✗ Failed to disable startup")
    
    print("\n✓ All tests completed!")


if __name__ == "__main__":
    test_startup_util()
