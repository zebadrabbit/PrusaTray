"""Utility for managing Windows startup configuration."""

import logging
import os
import sys
import winreg

logger = logging.getLogger(__name__)

# Registry key for Windows startup applications
STARTUP_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
APP_NAME = "PrusaTray"


def get_executable_path() -> str:
    """
    Get the path to the current executable.

    Returns:
        Path to the executable or script.
    """
    if getattr(sys, "frozen", False):
        # Running as compiled executable
        return sys.executable
    else:
        # Running as script - use pythonw to avoid console window
        python_exe = sys.executable
        script_path = os.path.abspath(sys.argv[0])

        # Try to use pythonw.exe instead of python.exe to avoid console window
        if python_exe.endswith("python.exe"):
            pythonw_exe = python_exe.replace("python.exe", "pythonw.exe")
            if os.path.exists(pythonw_exe):
                python_exe = pythonw_exe

        return f'"{python_exe}" "{script_path}"'


def is_startup_enabled() -> bool:
    """
    Check if the application is configured to start with Windows.

    Returns:
        True if startup is enabled, False otherwise.
    """
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, STARTUP_KEY_PATH, 0, winreg.KEY_READ
        ) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
            current_path = get_executable_path()
            # Check if the registry value matches current executable path
            return value.strip('"') in current_path or current_path.strip('"') in value
    except FileNotFoundError:
        return False
    except Exception as e:
        logger.error(f"Error checking startup status: {e}")
        return False


def set_startup_enabled(enabled: bool) -> bool:
    """
    Enable or disable the application to start with Windows.

    Args:
        enabled: True to enable startup, False to disable.

    Returns:
        True if successful, False otherwise.
    """
    try:
        if enabled:
            # Add to startup
            exe_path = get_executable_path()
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, STARTUP_KEY_PATH, 0, winreg.KEY_WRITE
            ) as key:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, exe_path)
            logger.info(f"Added {APP_NAME} to Windows startup: {exe_path}")
            return True
        else:
            # Remove from startup
            try:
                with winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER, STARTUP_KEY_PATH, 0, winreg.KEY_WRITE
                ) as key:
                    winreg.DeleteValue(key, APP_NAME)
                logger.info(f"Removed {APP_NAME} from Windows startup")
                return True
            except FileNotFoundError:
                # Already not in startup
                logger.debug(f"{APP_NAME} was not in Windows startup")
                return True
    except PermissionError:
        logger.error("Permission denied when modifying registry")
        return False
    except Exception as e:
        logger.error(f"Error modifying startup status: {e}")
        return False
