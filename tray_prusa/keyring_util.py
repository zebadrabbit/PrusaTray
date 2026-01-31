"""Secure credential storage using Windows Credential Manager via keyring."""

import logging
from typing import Optional

try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False

logger = logging.getLogger(__name__)

# Service name for keyring storage
SERVICE_NAME = "PrusaTray"


def is_keyring_available() -> bool:
    """
    Check if keyring is available.
    
    Returns:
        True if keyring is available, False otherwise.
    """
    return KEYRING_AVAILABLE


def set_password(printer_url: str, username: str, password: str) -> bool:
    """
    Securely store password using Windows Credential Manager.
    
    Args:
        printer_url: Printer base URL (used to create unique key).
        username: Username.
        password: Password to store securely.
        
    Returns:
        True if stored successfully, False otherwise.
    """
    if not KEYRING_AVAILABLE:
        logger.error("keyring library not available")
        return False
    
    try:
        # Create unique key from URL and username
        key = f"{printer_url}:{username}"
        keyring.set_password(SERVICE_NAME, key, password)
        logger.info(f"Stored password for {username}@{printer_url}")
        return True
    except Exception as e:
        logger.error(f"Failed to store password: {e}")
        return False


def get_password(printer_url: str, username: str) -> Optional[str]:
    """
    Retrieve password from Windows Credential Manager.
    
    Args:
        printer_url: Printer base URL.
        username: Username.
        
    Returns:
        Password if found, None otherwise.
    """
    if not KEYRING_AVAILABLE:
        logger.warning("keyring library not available")
        return None
    
    try:
        key = f"{printer_url}:{username}"
        password = keyring.get_password(SERVICE_NAME, key)
        if password:
            logger.debug(f"Retrieved password for {username}@{printer_url}")
        else:
            logger.debug(f"No password found for {username}@{printer_url}")
        return password
    except Exception as e:
        logger.error(f"Failed to retrieve password: {e}")
        return None


def delete_password(printer_url: str, username: str) -> bool:
    """
    Delete password from Windows Credential Manager.
    
    Args:
        printer_url: Printer base URL.
        username: Username.
        
    Returns:
        True if deleted successfully, False otherwise.
    """
    if not KEYRING_AVAILABLE:
        logger.warning("keyring library not available")
        return False
    
    try:
        key = f"{printer_url}:{username}"
        keyring.delete_password(SERVICE_NAME, key)
        logger.info(f"Deleted password for {username}@{printer_url}")
        return True
    except keyring.errors.PasswordDeleteError:
        logger.debug(f"No password to delete for {username}@{printer_url}")
        return True  # Not an error if password doesn't exist
    except Exception as e:
        logger.error(f"Failed to delete password: {e}")
        return False
