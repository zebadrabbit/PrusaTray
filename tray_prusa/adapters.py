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
    elif status_upper == "OFFLINE":
        return PrinterStatus.OFFLINE
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
    
    Supports two credential lookup methods:
    1. Legacy: username + printer_base_url (stored as "url:username" in keyring)
    2. New: password_key reference (e.g., "prusalink:mk4-office")
    
    Args:
        config: Application configuration.
        
    Returns:
        Dictionary of header name -> header value (as bytes).
    """
    headers = {}
    
    if config.auth_mode == "apikey":
        # API key mode: retrieve key from keyring and add X-Api-Key header
        api_key = None
        
        # Try password_key first (new method)
        if config.password_key:
            api_key = keyring_util.get_secret(config.password_key)
            if not api_key:
                logger.warning(f"API key not found for password_key '{config.password_key}'")
        
        # Fallback to legacy method (url:username)
        elif config.username and config.printer_base_url:
            api_key = keyring_util.get_password(config.printer_base_url, config.username)
            if not api_key:
                logger.warning("API key not found in keyring (legacy lookup)")
        
        if api_key:
            headers[b"X-Api-Key"] = api_key.encode('utf-8')
            logger.debug("Added X-Api-Key header for API key auth")
    
    elif config.auth_mode == "digest":
        # Digest auth: retrieve password and add Basic auth header as fallback
        # Note: Full digest auth requires challenge/response, so we use Basic for initial request
        password = None
        
        # Try password_key first (new method)
        if config.password_key:
            password = keyring_util.get_secret(config.password_key)
            if not password:
                logger.warning(f"Password not found for password_key '{config.password_key}'")
        
        # Fallback to legacy method (url:username)
        elif config.username and config.printer_base_url:
            password = keyring_util.get_password(config.printer_base_url, config.username)
            if not password:
                logger.warning("Password not found in keyring (legacy lookup)")
        
        if password:
            import base64
            credentials = f"{config.username}:{password}"
            b64_credentials = base64.b64encode(credentials.encode('utf-8')).decode('ascii')
            headers[b"Authorization"] = f"Basic {b64_credentials}".encode('utf-8')
            logger.debug("Added Basic Authorization header for digest auth")
    
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
# PRUSA CONNECT PARSING
# ============================================================================

def parse_prusa_connect_state(data: Dict[str, Any]) -> PrinterState:
    """
    Parse Prusa Connect API response.
    
    This parser is designed to be flexible since the PrusaConnect API
    may evolve. It extracts common fields and logs unknown fields at debug level.
    
    Expected structure (based on typical REST API patterns):
    {
      "state": "PRINTING" | "IDLE" | "PAUSED" | "ERROR",
      "progress": 45.5,  // 0-100 percentage
      "time_remaining": 1800,  // seconds
      "temp_nozzle": 215.0,
      "temp_bed": 60.0,
      "file_name": "model.gcode"
    }
    
    Or nested format:
    {
      "printer": {"state": "PRINTING", "temp_nozzle": 215, "temp_bed": 60},
      "job": {"progress": 45.5, "time_remaining": 1800, "file_name": "model.gcode"}
    }
    
    Args:
        data: Parsed JSON from Prusa Connect API.
    
    Returns:
        PrinterState.
    """
    try:
        # Try to extract state from various possible locations
        status_str = None
        if "state" in data:
            status_str = data.get("state")
        elif "printer" in data:
            printer = data.get("printer", {})
            status_str = printer.get("state") or printer.get("status")
        elif "status" in data:
            status_str = data.get("status")
        
        status = normalize_status(status_str) if status_str else PrinterStatus.UNKNOWN
        
        # Try to extract progress from various locations
        progress = None
        progress_value = data.get("progress")
        if progress_value is None and "job" in data:
            job_data = data.get("job", {})
            if isinstance(job_data, dict):
                progress_value = job_data.get("progress") or job_data.get("completion")
        
        if progress_value is not None:
            # Normalize to 0-1 range (handle both 0-1 and 0-100 formats)
            if progress_value <= 1.0:
                progress = clamp(progress_value, 0.0, 1.0)
            else:
                progress = clamp(progress_value / 100.0, 0.0, 1.0)
        
        # Try to extract time remaining
        eta_seconds = None
        time_remaining = data.get("time_remaining")
        if time_remaining is None and "job" in data:
            job_data = data.get("job", {})
            if isinstance(job_data, dict):
                time_remaining = job_data.get("time_remaining") or job_data.get("printTimeLeft")
        
        if time_remaining is not None:
            eta_seconds = int(time_remaining)
        
        # Try to extract temperatures
        nozzle_temp = data.get("temp_nozzle") or data.get("nozzle_temp")
        bed_temp = data.get("temp_bed") or data.get("bed_temp")
        
        if nozzle_temp is None and "printer" in data:
            printer = data.get("printer", {})
            if isinstance(printer, dict):
                nozzle_temp = printer.get("temp_nozzle") or printer.get("nozzle_temp")
                bed_temp = printer.get("temp_bed") or printer.get("bed_temp")
        
        if nozzle_temp is None and "temperature" in data:
            temp_data = data.get("temperature", {})
            if isinstance(temp_data, dict):
                nozzle_temp = temp_data.get("nozzle") or temp_data.get("tool0", {}).get("actual")
                bed_temp = temp_data.get("bed", {}).get("actual") if isinstance(temp_data.get("bed"), dict) else temp_data.get("bed")
        
        # Try to extract file name
        job_name = data.get("file_name") or data.get("filename")
        if job_name is None and "job" in data:
            job_data = data.get("job", {})
            if isinstance(job_data, dict):
                job_name = job_data.get("file_name") or job_data.get("filename")
                if job_name is None and "file" in job_data:
                    file_info = job_data.get("file", {})
                    if isinstance(file_info, dict):
                        job_name = file_info.get("name")
        
        # Log unknown fields at debug level
        known_fields = {"state", "status", "progress", "time_remaining", "temp_nozzle", 
                       "temp_bed", "nozzle_temp", "bed_temp", "file_name", "filename",
                       "printer", "job", "temperature"}
        unknown_fields = set(data.keys()) - known_fields
        if unknown_fields:
            logger.debug(f"PrusaConnect response contains unknown fields: {unknown_fields}")
        
        return PrinterState(
            status=status,
            progress=progress,
            eta_seconds=eta_seconds,
            job_name=job_name,
            nozzle_temp=nozzle_temp,
            bed_temp=bed_temp,
            last_ok_timestamp=datetime.now()
        )
    
    except Exception as e:
        logger.error(f"Error parsing PrusaConnect state: {e}", exc_info=True)
        return PrinterState(
            status=PrinterStatus.ERROR,
            error_message=f"Parse error: {str(e)}",
            last_ok_timestamp=datetime.now()
        )


# ============================================================================
# PRUSALINK PARSING
# ============================================================================

def parse_prusalink_state(data: Dict[str, Any]) -> PrinterState:
    """
    Parse PrusaLink API response (v1 or legacy format).
    
    Supports two API formats:
    
    1. PrusaLink API v1 (/api/v1/status):
    {
      "printer": {"state": "PRINTING", "temp_nozzle": 215.0, "temp_bed": 60.0},
      "job": {"progress": 45.5, "time_remaining": 1800, "file": {"name": "model.gcode"}}
    }
    
    2. Legacy format (/api/job):
    {
      "state": "Printing",
      "job": {"file": {"name": "model.gcode"}},
      "progress": {"completion": 0.88, "printTimeLeft": 960},
      "temperature": {"tool0": {"actual": 215}, "bed": {"actual": 60}}
    }
    
    Args:
        data: Parsed JSON from PrusaLink API.
    
    Returns:
        PrinterState.
    """
    try:
        # Detect format by checking for "printer" key (v1) or "state" at root (legacy)
        if "printer" in data:
            # V1 format
            printer = data.get("printer", {})
            job = data.get("job")
            
            # Parse status
            status_str = printer.get("state", "UNKNOWN")
            status = normalize_status(status_str)
            
            # Parse temperatures
            nozzle_temp = printer.get("temp_nozzle")
            bed_temp = printer.get("temp_bed")
            
            # Parse job info (job may be null if no print)
            progress = None
            eta_seconds = None
            job_name = None
            
            if job:
                progress_percent = job.get("progress")
                if progress_percent is not None:
                    # V1 uses 0-100 percentage
                    progress = clamp(progress_percent / 100.0, 0.0, 1.0)
                
                time_remaining = job.get("time_remaining")
                eta_seconds = int(time_remaining) if time_remaining is not None else None
                
                file_info = job.get("file", {})
                job_name = file_info.get("name") if isinstance(file_info, dict) else None
            
        else:
            # Legacy format
            status_str = data.get("state", "UNKNOWN")
            status = normalize_status(status_str)
            
            # Parse temperatures
            temp_data = data.get("temperature", {})
            tool_temp = temp_data.get("tool0", {}) if temp_data else {}
            bed_temp_data = temp_data.get("bed", {}) if temp_data else {}
            
            nozzle_temp = tool_temp.get("actual") if isinstance(tool_temp, dict) else None
            bed_temp = bed_temp_data.get("actual") if isinstance(bed_temp_data, dict) else None
            
            # Parse job info
            progress = None
            eta_seconds = None
            job_name = None
            
            job = data.get("job")
            progress_data = data.get("progress")
            
            if progress_data:
                completion = progress_data.get("completion")
                if completion is not None:
                    # Legacy format may use 0-1 OR 0-100, normalize both
                    if completion <= 1.0:
                        progress = clamp(completion, 0.0, 1.0)
                    else:
                        progress = clamp(completion / 100.0, 0.0, 1.0)
                
                time_left = progress_data.get("printTimeLeft")
                eta_seconds = int(time_left) if time_left is not None else None
            
            if job and isinstance(job, dict):
                file_info = job.get("file", {})
                job_name = file_info.get("name") if isinstance(file_info, dict) else None
            
            # Handle edge case: Operational with null job/progress = idle
            if status == PrinterStatus.IDLE and not job and not progress_data:
                progress = None
        
        return PrinterState(
            status=status,
            progress=progress,
            eta_seconds=eta_seconds,
            job_name=job_name,
            nozzle_temp=nozzle_temp,
            bed_temp=bed_temp,
            last_ok_timestamp=datetime.now()
        )
    
    except Exception as e:
        logger.error(f"Error parsing PrusaLink state: {e}", exc_info=True)
        return PrinterState(
            status=PrinterStatus.ERROR,
            error_message=f"Parse error: {str(e)}",
            last_ok_timestamp=datetime.now()
        )


# ============================================================================
# OCTOPRINT PARSING
# ============================================================================

def parse_octoprint_state(data: Dict[str, Any]) -> PrinterState:
    """
    Parse OctoPrint API response from /api/job endpoint.
    
    OctoPrint /api/job response format:
    {
      "state": "Printing",  // or {"text": "Printing", "flags": {...}}
      "job": {
        "file": {"name": "model.gcode"},
        "estimatedPrintTime": 3600,
        "filament": {...}
      },
      "progress": {
        "completion": 42.5,      // 0-100 percentage
        "printTime": 1200,       // seconds elapsed
        "printTimeLeft": 1800    // seconds remaining
      }
    }
    
    Also supports /api/printer response with temperature data.
    
    Args:
        data: Parsed JSON from OctoPrint API.
    
    Returns:
        PrinterState.
    """
    try:
        # Parse state - can be string or dict with "text" field
        state_data = data.get("state")
        if isinstance(state_data, dict):
            status_str = state_data.get("text", "UNKNOWN")
        elif isinstance(state_data, str):
            status_str = state_data
        else:
            status_str = "UNKNOWN"
        
        status = normalize_status(status_str)
        
        # Parse progress data
        progress = None
        eta_seconds = None
        
        progress_data = data.get("progress")
        if progress_data and isinstance(progress_data, dict):
            completion = progress_data.get("completion")
            if completion is not None:
                # OctoPrint uses 0-100 percentage
                progress = clamp(completion / 100.0, 0.0, 1.0)
            
            time_left = progress_data.get("printTimeLeft")
            eta_seconds = int(time_left) if time_left is not None else None
        
        # Parse job data
        job_name = None
        job_data = data.get("job")
        if job_data and isinstance(job_data, dict):
            file_info = job_data.get("file", {})
            if isinstance(file_info, dict):
                job_name = file_info.get("name")
        
        # Parse temperature data (if present from /api/printer)
        nozzle_temp = None
        bed_temp = None
        temp_data = data.get("temperature")
        if temp_data and isinstance(temp_data, dict):
            tool_data = temp_data.get("tool0", {})
            bed_data = temp_data.get("bed", {})
            
            if isinstance(tool_data, dict):
                nozzle_temp = tool_data.get("actual")
            if isinstance(bed_data, dict):
                bed_temp = bed_data.get("actual")
        
        return PrinterState(
            status=status,
            progress=progress,
            eta_seconds=eta_seconds,
            job_name=job_name,
            nozzle_temp=nozzle_temp,
            bed_temp=bed_temp,
            last_ok_timestamp=datetime.now()
        )
    
    except Exception as e:
        logger.error(f"Error parsing OctoPrint state: {e}", exc_info=True)
        return PrinterState(
            status=PrinterStatus.OFFLINE,
            error_message=f"Parse error: {str(e)}",
            message="Failed to parse OctoPrint response",
            last_ok_timestamp=datetime.now()
        )


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
        Does NOT block. Uses 5-second timeout for responsiveness.
        """
        url = QUrl(f"{self.base_url}{self.endpoint}")
        request = QNetworkRequest(url)
        request.setTransferTimeout(5000)  # 5s timeout - fail fast for better UX
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
        """
        Handle network reply with comprehensive error handling.
        
        Never throws - always emits either state_fetched or state_error.
        Handles malformed JSON gracefully.
        """
        try:
            error = reply.error()
            http_status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            self._last_http_status = http_status
            
            if error == QNetworkReply.NetworkError.NoError:
                # Success - parse response
                data = reply.readAll().data()
                
                # Parse JSON with error handling
                try:
                    import json
                    parsed = json.loads(data.decode('utf-8'))
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON from {self.base_url}: {e}")
                    error_state = PrinterState(
                        status=PrinterStatus.ERROR,
                        error_message="Invalid JSON response",
                        message=f"Server returned malformed JSON: {str(e)[:100]}"
                    )
                    self.state_fetched.emit(error_state)
                    return
                except UnicodeDecodeError as e:
                    logger.error(f"Invalid encoding from {self.base_url}: {e}")
                    error_state = PrinterState(
                        status=PrinterStatus.ERROR,
                        error_message="Invalid response encoding",
                        message=f"Server returned non-UTF8 data"
                    )
                    self.state_fetched.emit(error_state)
                    return
                
                # Parse to PrinterState
                try:
                    state = self.parse_response(parsed)
                    state.last_ok_timestamp = datetime.now()
                    self.state_fetched.emit(state)
                except Exception as e:
                    logger.error(f"Failed to parse response from {self.base_url}: {e}", exc_info=True)
                    error_state = PrinterState(
                        status=PrinterStatus.ERROR,
                        error_message="Parse error",
                        message=f"Could not parse printer state: {str(e)[:100]}"
                    )
                    self.state_fetched.emit(error_state)
                    
            elif http_status == 401 or http_status == 403:
                # Authentication failure
                error_msg = f"Authentication failed (HTTP {http_status})"
                logger.error(f"{self.base_url}: {error_msg}")
                error_state = PrinterState(
                    status=PrinterStatus.ERROR,
                    error_message="Authentication failed",
                    message="Check credentials in configuration"
                )
                self.state_fetched.emit(error_state)
                
            elif http_status == 404:
                # Not found - might be wrong endpoint
                error_msg = f"Endpoint not found (HTTP 404): {self.endpoint}"
                logger.error(f"{self.base_url}: {error_msg}")
                error_state = PrinterState(
                    status=PrinterStatus.ERROR,
                    error_message="Endpoint not found",
                    message=f"API endpoint {self.endpoint} does not exist"
                )
                self.state_fetched.emit(error_state)
                
            elif http_status and 500 <= http_status < 600:
                # Server error
                error_msg = f"Server error (HTTP {http_status})"
                logger.warning(f"{self.base_url}: {error_msg}")
                error_state = PrinterState(
                    status=PrinterStatus.ERROR,
                    error_message="Server error",
                    message=f"Printer returned HTTP {http_status}"
                )
                self.state_fetched.emit(error_state)
                
            elif error == QNetworkReply.NetworkError.TimeoutError:
                # Timeout
                logger.warning(f"{self.base_url}: Request timeout (5s)")
                error_state = PrinterState(
                    status=PrinterStatus.ERROR,
                    error_message="Timeout",
                    message="Printer did not respond within 5 seconds"
                )
                self.state_fetched.emit(error_state)
                
            elif error == QNetworkReply.NetworkError.HostNotFoundError:
                # Host not found
                logger.warning(f"{self.base_url}: Host not found")
                error_state = PrinterState(
                    status=PrinterStatus.ERROR,
                    error_message="Host not found",
                    message="Could not resolve printer hostname/IP"
                )
                self.state_fetched.emit(error_state)
                
            elif error == QNetworkReply.NetworkError.ConnectionRefusedError:
                # Connection refused
                logger.warning(f"{self.base_url}: Connection refused")
                error_state = PrinterState(
                    status=PrinterStatus.ERROR,
                    error_message="Connection refused",
                    message="Printer refused connection - is it powered on?"
                )
                self.state_fetched.emit(error_state)
                
            else:
                # Generic network error
                error_string = reply.errorString()
                logger.warning(f"{self.base_url}: Network error: {error_string}")
                error_state = PrinterState(
                    status=PrinterStatus.ERROR,
                    error_message="Network error",
                    message=error_string[:100]
                )
                self.state_fetched.emit(error_state)
                
        except Exception as e:
            # Catch-all for unexpected errors
            logger.error(f"Unexpected error handling reply from {self.base_url}: {e}", exc_info=True)
            try:
                error_state = PrinterState(
                    status=PrinterStatus.ERROR,
                    error_message="Internal error",
                    message=str(e)[:100]
                )
                self.state_fetched.emit(error_state)
            except:
                # Last resort - log but don't crash
                logger.critical(f"Failed to emit error state: {e}")
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
    
    Authenticates using a bearer token (user must provide via config).
    
    Configuration requirements:
    - bearer_token: Authentication token from Prusa Connect account
    - printer_id: Unique printer identifier
    - status_path: Optional custom endpoint path (defaults to /api/v1/status)
    
    No automatic login is performed - user must generate and provide token manually.
    """
    
    def __init__(self, base_url: str, config: Optional[AppConfig] = None, parent: Optional[QObject] = None):
        """Initialize PrusaConnect adapter with bearer token auth."""
        super().__init__(base_url, config, parent)
        
        # Validate required config
        if not config:
            raise ValueError("PrusaConnect requires configuration with bearer_token and printer_id")
        if not config.bearer_token:
            raise ValueError("PrusaConnect requires bearer_token in configuration")
        if not config.printer_id:
            raise ValueError("PrusaConnect requires printer_id in configuration")
    
    @property
    def endpoint(self) -> str:
        """Return configurable status endpoint."""
        if self.config and self.config.status_path:
            return self.config.status_path
        return "/api/v1/status"
    
    def _prepare_request(self, request: QNetworkRequest) -> None:
        """Add bearer token authentication header."""
        if self.config and self.config.bearer_token:
            auth_header = f"Bearer {self.config.bearer_token}"
            request.setRawHeader(b"Authorization", auth_header.encode())
        
        # Add JSON accept header
        request.setRawHeader(b"Accept", b"application/json")
    
    def parse_response(self, data: Dict[str, Any]) -> PrinterState:
        return parse_prusa_connect_state(data)


class PrusaLinkAdapter(HttpJsonAdapter):
    """
    PrusaLink local API adapter with dual-endpoint support.
    
    Supports both:
    - PrusaLink API v1: /api/v1/status (primary)
    - Legacy format: /api/job (fallback)
    
    Auto-detects which endpoint is available and uses it.
    """
    
    def __init__(self, base_url: str, config: Optional[AppConfig] = None, parent: Optional[QObject] = None):
        """Initialize PrusaLink adapter."""
        super().__init__(base_url, config, parent)
        self._use_legacy = False  # Track which endpoint works
        self._tried_v1 = False
    
    @property
    def endpoint(self) -> str:
        """Return current endpoint (v1 or legacy)."""
        return "/api/job" if self._use_legacy else "/api/v1/status"
    
    def parse_response(self, data: Dict[str, Any]) -> PrinterState:
        """Parse PrusaLink response (auto-detects format)."""
        return parse_prusalink_state(data)
    
    def fetch_state_async(self) -> None:
        """
        Fetch state with automatic endpoint fallback.
        
        Tries /api/v1/status first, falls back to /api/job if needed.
        Uses 5-second timeout for responsiveness.
        """
        # If we already know which endpoint works, use it
        if self._use_legacy or self._tried_v1:
            super().fetch_state_async()
            return
        
        # First time: try v1 endpoint
        url = QUrl(f"{self.base_url}/api/v1/status")
        request = QNetworkRequest(url)
        request.setTransferTimeout(5000)  # 5s timeout - fail fast
        request.setRawHeader(b"Accept", b"application/json")
        
        # Add authentication headers
        if self.config:
            auth_headers = build_auth_headers(self.config)
            for header_name, header_value in auth_headers.items():
                request.setRawHeader(header_name, header_value)
        
        logger.debug(f"Trying v1 endpoint: {url.toString()}")
        
        reply = self._network_manager.get(request)
        reply.finished.connect(lambda: self._handle_v1_reply(reply))
    
    def _handle_v1_reply(self, reply: QNetworkReply) -> None:
        """Handle v1 endpoint reply with fallback logic."""
        try:
            error = reply.error()
            http_status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
            self._last_http_status = http_status
            
            if error == QNetworkReply.NetworkError.NoError:
                # V1 endpoint works!
                data = reply.readAll().data()
                import json
                parsed = json.loads(data.decode('utf-8'))
                state = self.parse_response(parsed)
                state.last_ok_timestamp = datetime.now()
                self._tried_v1 = True
                self.state_fetched.emit(state)
            elif http_status == 404:
                # V1 not available, try legacy
                logger.info("V1 endpoint not found, trying legacy /api/job")
                self._use_legacy = True
                self._tried_v1 = True
                super().fetch_state_async()
            elif http_status == 401 or http_status == 403:
                # Authentication failure
                error_msg = f"Authentication failed (HTTP {http_status})"
                logger.error(error_msg)
                error_state = PrinterState(
                    status=PrinterStatus.ERROR,
                    error_message="Auth failed - check credentials",
                    message=error_msg
                )
                self._tried_v1 = True
                self.state_fetched.emit(error_state)
            else:
                # Other error, try legacy as fallback
                error_string = reply.errorString()
                logger.warning(f"V1 endpoint error: {error_string}, trying legacy")
                self._use_legacy = True
                self._tried_v1 = True
                super().fetch_state_async()
        except Exception as e:
            logger.error(f"Error handling v1 reply: {e}", exc_info=True)
            # Try legacy on parse errors too
            self._use_legacy = True
            self._tried_v1 = True
            super().fetch_state_async()
        finally:
            reply.deleteLater()


class OctoPrintAdapter(HttpJsonAdapter):
    """
    OctoPrint API adapter.
    
    Uses /api/job endpoint which provides:
    - Current state (Printing/Paused/Operational/Offline/Error)
    - Job progress and time estimates
    - File name
    
    Requires X-Api-Key authentication.
    """
    
    @property
    def endpoint(self) -> str:
        """OctoPrint job endpoint."""
        return "/api/job"
    
    def parse_response(self, data: Dict[str, Any]) -> PrinterState:
        """Parse OctoPrint /api/job response."""
        return parse_octoprint_state(data)
