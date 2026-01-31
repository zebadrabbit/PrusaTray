"""Factory for creating printer adapters based on configuration."""

import logging
from typing import Union

from .adapters import (
    BaseAdapter,
    DemoAdapter,
    PrusaConnectAdapter,
    PrusaLinkAdapter,
    OctoPrintAdapter,
)
from .models import AppConfig

logger = logging.getLogger(__name__)


# Type alias for all adapter types
AdapterType = Union[DemoAdapter, PrusaConnectAdapter, PrusaLinkAdapter, OctoPrintAdapter]


def create_adapter(config: AppConfig) -> AdapterType:
    """
    Create appropriate adapter based on configuration.
    
    This is the ONLY place where backend selection logic lives.
    Changing backends is literally just changing config.backend value.
    
    Args:
        config: Application configuration.
    
    Returns:
        Adapter instance for the configured backend.
    
    Raises:
        ValueError: If backend is unknown or config is invalid.
    """
    backend = config.backend.lower()
    
    logger.info(f"Creating adapter for backend: {backend}")
    
    if backend == "demo":
        # Demo mode: no URL needed
        return DemoAdapter()
    
    elif backend == "prusaconnect":
        # Prusa Connect cloud API
        if not config.printer_base_url:
            raise ValueError("printer_base_url required for prusaconnect backend")
        return PrusaConnectAdapter(config.printer_base_url, config)
    
    elif backend == "prusalink":
        # PrusaLink local API
        if not config.printer_base_url:
            raise ValueError("printer_base_url required for prusalink backend")
        return PrusaLinkAdapter(config.printer_base_url, config)
    
    elif backend == "octoprint":
        # OctoPrint API
        if not config.printer_base_url:
            raise ValueError("printer_base_url required for octoprint backend")
        return OctoPrintAdapter(config.printer_base_url, config)
    
    else:
        raise ValueError(
            f"Unknown backend: {backend}. "
            f"Valid options: demo, prusaconnect, prusalink, octoprint"
        )


def validate_config(config: AppConfig) -> None:
    """
    Validate configuration for selected backend.
    
    Args:
        config: Configuration to validate.
    
    Raises:
        ValueError: If configuration is invalid.
    """
    backend = config.backend.lower()
    
    # Demo doesn't need URL
    if backend == "demo":
        return
    
    # All other backends require a URL
    if backend in ("prusaconnect", "prusalink", "octoprint"):
        if not config.printer_base_url:
            raise ValueError(
                f"Backend '{backend}' requires printer_base_url to be set. "
                f"Set it in config or use backend='demo' for testing."
            )
        
        # Basic URL validation
        url = config.printer_base_url.lower()
        if not (url.startswith("http://") or url.startswith("https://")):
            raise ValueError(
                f"printer_base_url must start with http:// or https://, got: {config.printer_base_url}"
            )
    else:
        raise ValueError(f"Unknown backend: {backend}")
