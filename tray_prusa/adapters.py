"""Adapter layer for different printer backends.

This module provides a clean abstraction over various printer APIs,
allowing backend swapping via config without touching UI code.
"""

import logging
import time
from datetime import datetime
from typing import Protocol, Dict, Any, Optional, Tuple

from PySide6.QtCore import QObject, Signal, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from .models import PrinterState, PrinterStatus, AppConfig
from . import keyring_util

logger = logging.getLogger(__name__)


# ============================================================================
# PURE PARSING FUNCTIONS (unit-testable, no I/O)
# ============================================================================

def normalize_status(status_str: Optional[str]) -> PrinterStatus:
    """
    Normalize various status strings to PrinterStatus enum.
    
    Args:
        status_str: Raw status string from API.
    
    Returns:
        Normalized PrinterStatus.
    """
    if not status_str:
        return PrinterStatus.UNKNOWN
    
    status_upper = status_str.upper()
    
    # Map common status strings to our enum
    if status_upper in ("IDLE", "READY", "OPERATIONAL"):
        return PrinterStatus.IDLE
    elif status_upper in ("PRINTING", "BUSY", "WORKING"):
        return PrinterStatus.PRINTING
    elif status_upper in ("PAUSED", "PAUSING"):
        return PrinterStatus.PAUSED
    elif status_upper in ("ERROR", "STOPPED", "FAILED"):
        return PrinterStatus.ERROR
    else:
        return PrinterStatus.UNKNOWN


def clamp(value: Optional[float], min_val: float = 0.0, max_val: float = 1.0) -> Optional[float]:
    """
    Clamp value to range, handling None.
    
    Args:
        value: Value to clamp.
        min_val: Minimum value.
        max_val: Maximum value.
    
    Returns:
        Clamped value or None.
    """
    if value is None:
        return None
    return max(min_val, min(max_val, value))


def build_auth_headers(config: AppConfig) -> Dict[bytes, bytes]:
    """
    Build authentication headers based on config.
    
    Args:
        config: Application configuration.
        
    Returns:
        Dictionary of header name -> header value (as bytes).
    """
    headers = {}
    
    if config.auth_mode == "apikey" and config.username and config.printer_base_url:
        # API key mode: retrieve key from keyring and add X-Api-Key header
        api_key = keyring_util.get_password(config.printer_base_url, config.username)
        if api_key:
            headers[b"X-Api-Key"] = api_key.encode('utf-8')
            logger.debug("Added X-Api-Key header for API key auth")
        else:
            logger.warning("API key not found in keyring")
    
    elif config.auth_mode == "digest" and config.username and config.printer_base_url:
        # Digest auth: retrieve password and add Basic auth header as fallback
        # Note: Full digest auth requires challenge/response, so we use Basic for initial request
        password = keyring_util.get_password(config.printer_base_url, config.username)
        if password:
            import base64
            credentials = f"{config.username}:{password}"
            b64_credentials = base64.b64encode(credentials.encode('utf-8')).decode('ascii')
            headers[b"Authorization"] = f"Basic {b64_credentials}".encode('utf-8')
            logger.debug("Added Basic Authorization header for digest auth")
        else:
            logger.warning("Password not found in keyring")
    
    return headers


# ============================================================================
# DEMO ADAPTER PARSING
# ============================================================================

def parse_demo_state(
    status: PrinterStatus,
    progress: float = 0.0,
    eta_seconds: Optional[int] = None,
    job_name: Optional[str] = None
) -> PrinterState:
    """
    Create demo state (pure function).
    
    Args:
        status: Printer status.
        progress: Progress 0.0-1.0.
        eta_seconds: ETA in seconds.
        job_name: Job name.
    
    Returns:
        PrinterState for demo.
    """
    return PrinterState(
        status=status,
        progress=clamp(progress, 0.0, 1.0),
        eta_seconds=eta_seconds,
        job_name=job_name,
        nozzle_temp=215.0 if status == PrinterStatus.PRINTING else None,
        bed_temp=60.0 if status == PrinterStatus.PRINTING else None,
        last_ok_timestamp=datetime.now()
    )


# ============================================================================
# PRUSA CONNECT PARSING (TODO: Implement when API docs available)
# ============================================================================

def parse_prusa_connect_state(data: Dict[str, Any]) -> PrinterState:
    """
    Parse Prusa Connect API response.
    
    TODO: Implement based on actual Prusa Connect API format.
    See: https://connect.prusa3d.com/docs
    
    Args:
        data: Parsed JSON from Prusa Connect API.
    
    Returns:
        PrinterState.
    
    Raises:
        KeyError, ValueError: If required fields missing or invalid.
    """
    # TODO: Replace with actual Prusa Connect format
    # Expected structure (example):
    # {
    #   "printer": {"state": "PRINTING", "temp_nozzle": 215, "temp_bed": 60},
    #   "job": {"progress": 0.45, "time_remaining": 1800, "file_name": "model.gcode"}
    # }
    
    raise NotImplementedError("Prusa Connect parsing not yet implemented")


# ============================================================================
# PRUSALINK PARSING
# ============================================================================

def parse_prusalink_state(data: Dict[str, Any]) -> PrinterState:
    """
    Parse PrusaLink API response.
    
    PrusaLink API endpoint: /api/v1/status
    Example response format:
    {
      "printer": {
        "state": "PRINTING",
        "temp_nozzle": 215.0,
        "temp_bed": 60.0
      },
      "job": {
        "id": 123,
        "progress": 45.5,
        "time_remaining": 1800,
        "time_printing": 900,
        "file": {
          "name": "model.gcode"
        }
      }
    }
    
    Args:
        data: Parsed JSON from PrusaLink API.
    
    Returns:
        PrinterState.
    
    Raises:
        KeyError, ValueError: If required fields missing or invalid.
    """
    # Extract printer info
    printer = data.get("printer", {})
    job = data.get("job", {})
    
    # Parse status
    status_str = printer.get("state", "UNKNOWN")
    status = normalize_status(status_str)
    
    # Parse temperatures
    nozzle_temp = printer.get("temp_nozzle")
    bed_temp = printer.get("temp_bed")
    
    # Parse job info
    progress_percent = job.get("progress")
    if progress_percent is not None:
        progress = clamp(progress_percent / 100.0, 0.0, 1.0)
    else:
        progress = None
    
    time_remaining = job.get("time_remaining")
    eta_seconds = int(time_remaining) if time_remaining is not None else None
    
    file_info = job.get("file", {})
    job_name = file_info.get("name") if file_info else None
    
    return PrinterState(
        status=status,
        progress=progress,
        eta_seconds=eta_seconds,
        job_name=job_name,
        nozzle_temp=nozzle_temp,
        bed_temp=bed_temp,
        last_ok_timestamp=datetime.now()
    )


# ============================================================================
# OCTOPRINT PARSING (TODO: Implement)
# ============================================================================

def parse_octoprint_state(data: Dict[str, Any]) -> PrinterState:
    """
    Parse OctoPrint API response.
    
    TODO: Implement based on OctoPrint REST API.
    See: https://docs.octoprint.org/en/master/api/
    
    Args:
        data: Parsed JSON from OctoPrint API.
    
    Returns:
        PrinterState.
    
    Raises:
        KeyError, ValueError: If required fields missing or invalid.
    """
    # TODO: Replace with actual OctoPrint format
    # Example endpoints:
    # - /api/printer (for temps and status)
    # - /api/job (for job info)
    
    raise NotImplementedError("OctoPrint parsing not yet implemented")


# ============================================================================
# ADAPTER PROTOCOL
# ============================================================================

class BaseAdapter(Protocol):
    """
    Protocol for printer adapters.
    
    All adapters must implement fetch_state() which returns a PrinterState
    or raises an exception on error.
    """
    
    def fetch_state(self) -> PrinterState:
        """
        Fetch current printer state.
        
        Returns:
            PrinterState with current status.
        
        Raises:
            Exception: On network, parse, or other errors.
        """
        ...


# ============================================================================
# DEMO ADAPTER
# ============================================================================

class DemoAdapter:
    """
    Demo adapter that simulates a print job.
    
    Does not make any network calls. Useful for testing and development.
    """
    
    def __init__(self):
        """Initialize demo adapter."""
        self._start_time = time.time()
        self._duration = 120  # 2 minute simulated print
    
    def fetch_state(self) -> PrinterState:
        """
        Generate simulated printer state.
        
        Returns:
            Simulated PrinterState.
        """
        elapsed = time.time() - self._start_time
        cycle_time = elapsed % (self._duration + 30)
        
        if cycle_time < self._duration:
            # Printing phase
            progress = cycle_time / self._duration
            remaining = int(self._duration - cycle_time)
            return parse_demo_state(
                status=PrinterStatus.PRINTING,
                progress=progress,
                eta_seconds=remaining,
                job_name="demo_model.gcode"
            )
        elif cycle_time < self._duration + 10:
            # Paused phase
            return parse_demo_state(
                status=PrinterStatus.PAUSED,
                progress=0.75,
                eta_seconds=30,
                job_name="demo_model.gcode"
            )
        else:
            # Idle phase
            return parse_demo_state(status=PrinterStatus.IDLE)


# ============================================================================
# HTTP JSON ADAPTER BASE CLASS
# ============================================================================

class HttpJsonAdapter(QObject):
    """
    Base class for HTTP/JSON-based printer adapters.
    
    Provides common functionality for making async HTTP requests
    with proper timeout and error handling.
    
    Subclasses must implement:
    - endpoint property: API endpoint path
    - parse_response: Parse JSON to PrinterState
    """
    
    # Signal emitted when state is fetched (async)
    state_fetched = Signal(PrinterState)
    state_error = Signal(str)
    
    def __init__(self, base_url: str, config: Optional[AppConfig] = None, parent: Optional[QObject] = None):
        """
        Initialize HTTP adapter.
        
        Args:
            base_url: Base URL of the printer (e.g., "http://192.168.1.100")
            config: Application configuration (for auth).
            parent: Parent QObject.
        """
        super().__init__(parent)
        self.base_url = base_url.rstrip('/')
        self.config = config
        self._network_manager = QNetworkAccessManager(self)
        self._last_http_status: Optional[int] = None
    
    @property
    def endpoint(self) -> str:
        """
        API endpoint path (e.g., "/api/printer/status").
        
        Subclasses must implement this property.
        
        Returns:
            Endpoint path string.
        """
        raise NotImplementedError("Subclasses must implement endpoint property")
    
    def parse_response(self, data: Dict[str, Any]) -> PrinterState:
        """
        Parse JSON response to PrinterState.
        
        Subclasses must implement this method.
        
        Args:
            data: Parsed JSON dictionary.
        
        Returns:
            PrinterState.
        
        Raises:
            Exception: On parse errors.
        """
        raise NotImplementedError("Subclasses must implement parse_response method")
    
    def fetch_state_async(self) -> None:
        """
        Fetch state asynchronously.
        
        Emits state_fetched on success or state_error on failure.
        Does NOT block.
        """
        url = QUrl(f"{self.base_url}{self.endpoint}")
        request = QNetworkRequest(url)
        request.setTransferTimeout(10000)  # 10s timeout
        request.setRawHeader(b"Accept", b"application/json")
        
        # Add authentication headers if configured
        if self.config:
            auth_headers = build_auth_headers(self.config)
            for header_name, header_value in auth_headers.items():
                request.setRawHeader(header_name, header_value)
        
        logger.debug(f"Fetching {url.toString()}")
        
        reply = self._network_manager.get(request)
        reply.finished.connect(lambda: self._handle_reply(reply))
    
    def _handle_reply(self, reply: QNetworkReply) -> None:
        """Handle network reply."""
        try:
            error = reply.error()
            http_status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            self._last_http_status = http_status
            
            if error == QNetworkReply.NetworkError.NoError:
                data = reply.readAll().data()
                import json
                parsed = json.loads(data.decode('utf-8'))
                state = self.parse_response(parsed)
                state.last_ok_timestamp = datetime.now()
                self.state_fetched.emit(state)
            elif http_status == 401 or http_status == 403:
                # Authentication failure
                error_msg = f"Authentication failed (HTTP {http_status})"
                logger.error(error_msg)
                # Emit error state with auth failure message
                error_state = PrinterState(
                    status=PrinterStatus.ERROR,
                    error_message="Auth failed - check credentials",
                    message=error_msg
                )
                self.state_fetched.emit(error_state)
            else:
                error_string = reply.errorString()
                logger.warning(f"Network error: {error_string}")
                self.state_error.emit(error_string)
        except Exception as e:
            logger.error(f"Parse error: {e}", exc_info=True)
            self.state_error.emit(str(e))
        finally:
            reply.deleteLater()
    
    def get_last_http_status(self) -> Optional[int]:
        """Get the last HTTP status code received."""
        return self._last_http_status


# ============================================================================
# CONCRETE HTTP ADAPTERS (Stubbed)
# ============================================================================

class PrusaConnectAdapter(HttpJsonAdapter):
    """
    Prusa Connect cloud API adapter.
    
    TODO: Implement when Prusa Connect API access is available.
    Requires API key authentication.
    """
    
    @property
    def endpoint(self) -> str:
        # TODO: Determine actual Prusa Connect endpoint
        return "/api/v1/status"
    
    def parse_response(self, data: Dict[str, Any]) -> PrinterState:
        return parse_prusa_connect_state(data)


class PrusaLinkAdapter(HttpJsonAdapter):
    """
    PrusaLink local API adapter.
    
    PrusaLink API documentation: https://github.com/prusa3d/Prusa-Link-Web/wiki/API-documentation
    Endpoint: /api/v1/status
    """
    
    @property
    def endpoint(self) -> str:
        return "/api/v1/status"
    
    def parse_response(self, data: Dict[str, Any]) -> PrinterState:
        return parse_prusalink_state(data)


class OctoPrintAdapter(HttpJsonAdapter):
    """
    OctoPrint API adapter.
    
    TODO: Implement based on OctoPrint REST API.
    May require combining multiple endpoints (/api/printer + /api/job).
    """
    
    @property
    def endpoint(self) -> str:
        # TODO: OctoPrint requires multiple endpoints
        # This is simplified; real implementation may need multiple requests
        return "/api/printer"
    
    def parse_response(self, data: Dict[str, Any]) -> PrinterState:
        return parse_octoprint_state(data)
