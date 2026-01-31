"""Secure credential storage using Windows Credential Manager via keyring."""

import logging
import os
import re
from typing import Optional

try:
    import keyring
    KEYRING_AVAILABLE = True
except ImportError:
    KEYRING_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("keyring library not available - credentials will only be available via environment variables")

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


def _sanitize_key_for_env(key: str) -> str:
    """
    Sanitize a key for use in environment variable name.
    
    Replaces non-alphanumeric characters with underscores and converts to uppercase.
    
    Args:
        key: The key to sanitize (e.g., "prusalink:mk4-office").
        
    Returns:
        Sanitized key suitable for env var (e.g., "PRUSALINK_MK4_OFFICE").
    """
    # Replace non-alphanumeric chars with underscore
    sanitized = re.sub(r'[^a-zA-Z0-9]+', '_', key)
    # Remove leading/trailing underscores and convert to uppercase
    return sanitized.strip('_').upper()


def get_secret(key: str) -> Optional[str]:
    """
    Retrieve secret from keyring or environment variable fallback.
    
    Tries in order:
    1. Windows Credential Manager via keyring (if available)
    2. Environment variable PRUSATRAY_PASSWORD_<SANITIZED_KEY>
    
    This allows running in headless environments or when keyring is unavailable.
    
    Args:
        key: Secret key/reference name (e.g., "prusalink:mk4-office").
        
    Returns:
        Secret value if found, None otherwise.
        
    Examples:
        >>> get_secret("prusalink:mk4-office")
        # Tries keyring first, then env var PRUSATRAY_PASSWORD_PRUSALINK_MK4_OFFICE
    """
    # Try keyring first (if available)
    if KEYRING_AVAILABLE:
        try:
            secret = keyring.get_password(SERVICE_NAME, key)
            if secret:
                logger.debug(f"Retrieved secret '{key}' from keyring")
                return secret
            else:
                logger.debug(f"Secret '{key}' not found in keyring, trying env var")
        except Exception as e:
            logger.warning(f"Error accessing keyring for '{key}': {e}")
    
    # Fallback to environment variable
    env_var_name = f"PRUSATRAY_PASSWORD_{_sanitize_key_for_env(key)}"
    secret = os.environ.get(env_var_name)
    if secret:
        logger.info(f"Retrieved secret '{key}' from environment variable {env_var_name}")
        return secret
    
    logger.debug(f"Secret '{key}' not found in keyring or environment")
    return None


def set_secret(key: str, value: str) -> bool:
    """
    Store secret in keyring.
    
    Args:
        key: Secret key/reference name.
        value: Secret value to store.
        
    Returns:
        True if stored successfully, False otherwise.
    """
    if not KEYRING_AVAILABLE:
        logger.error("keyring library not available - cannot store secret")
        logger.info(f"To use this secret, set environment variable: PRUSATRAY_PASSWORD_{_sanitize_key_for_env(key)}")
        return False
    
    try:
        keyring.set_password(SERVICE_NAME, key, value)
        logger.info(f"Stored secret '{key}' in keyring")
        return True
    except Exception as e:
        logger.error(f"Failed to store secret '{key}': {e}")
        return False


def prompt_for_credential(key: str, parent=None) -> Optional[str]:
    """
    Prompt user for credential using Qt dialog.
    
    Args:
        key: Credential key/reference name (shown in dialog).
        parent: Optional parent widget for dialog.
        
    Returns:
        Entered credential, or None if cancelled/failed.
    """
    try:
        from PySide6.QtWidgets import QInputDialog, QApplication
        import sys
        
        # Ensure QApplication exists
        app = QApplication.instance()
        if app is None:
            logger.warning("No QApplication instance - cannot show credential prompt")
            return None
        
        credential, ok = QInputDialog.getText(
            parent,
            "Credential Required",
            f"Enter credential for '{key}':",
            echo=QInputDialog.EchoMode.Password
        )
        
        if ok and credential:
            return credential
        else:
            logger.info("User cancelled credential prompt")
            return None
            
    except Exception as e:
        logger.error(f"Failed to show credential prompt: {e}")
        return None
