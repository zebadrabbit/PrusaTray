"""Adapter layer for different printer backends.

This module provides a clean abstraction over various printer APIs,
allowing backend swapping via config without touching UI code.
"""

import logging
import time
from datetime import datetime
from typing import Protocol, Dict, Any, Optional

from PySide6.QtCore import QObject, QTimer, QUrl, Signal
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply

from .models import PrinterState, PrinterStatus, AppConfig
from . import keyring_util

logger = logging.getLogger(__name__)


# ============================================================================
# PURE PARSING FUNCTIONS (unit-testable, no I/O)
# ============================================================================


def normalize_status(status_str: Optional[str]) -> PrinterStatus:
    """
    Normalize a backend status string to PrinterStatus.

    Covers the PrusaLink API v1 printer states (IDLE, BUSY, PRINTING, PAUSED,
    FINISHED, STOPPED, ERROR, ATTENTION, READY), the extra Prusa Connect states
    (MANIPULATING, OFFLINE, UNKNOWN) and the legacy OctoPrint-style strings.

    Args:
        status_str: Raw status string from API.

    Returns:
        Normalized PrinterStatus.
    """
    if not status_str:
        return PrinterStatus.UNKNOWN

    # FINISHED/STOPPED mean "the job ended, printer is sitting there" - not an
    # error, and mapping them to IDLE is what makes the print-complete
    # notification fire on the PRINTING -> FINISHED transition.
    # BUSY/MANIPULATING mean the printer is doing something that is not a print.
    return {
        "IDLE": PrinterStatus.IDLE,
        "READY": PrinterStatus.IDLE,
        "OPERATIONAL": PrinterStatus.IDLE,
        "FINISHED": PrinterStatus.IDLE,
        "STOPPED": PrinterStatus.IDLE,
        "CANCELLED": PrinterStatus.IDLE,
        "BUSY": PrinterStatus.IDLE,
        "MANIPULATING": PrinterStatus.IDLE,
        "PRINTING": PrinterStatus.PRINTING,
        "WORKING": PrinterStatus.PRINTING,
        "PAUSED": PrinterStatus.PAUSED,
        "PAUSING": PrinterStatus.PAUSED,
        "ATTENTION": PrinterStatus.ATTENTION,
        "ERROR": PrinterStatus.ERROR,
        "FAILED": PrinterStatus.ERROR,
        "OFFLINE": PrinterStatus.OFFLINE,
    }.get(status_str.upper(), PrinterStatus.UNKNOWN)


def clamp(
    value: Optional[float], min_val: float = 0.0, max_val: float = 1.0
) -> Optional[float]:
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


def normalize_progress(value: Optional[float]) -> Optional[float]:
    """
    Normalize a progress value to 0.0-1.0.

    Prusa APIs report percent (0-100); a few legacy payloads report a fraction.
    Values <= 1.0 are treated as a fraction, everything else as percent.

    Args:
        value: Raw progress value, or None.

    Returns:
        Progress as 0.0-1.0, or None.
    """
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return clamp(value if value <= 1.0 else value / 100.0, 0.0, 1.0)


def positive_seconds(value: Optional[Any]) -> Optional[int]:
    """
    Coerce a remaining-time field to a non-negative int.

    PrusaLink reports -1 (and Connect reports null) while the estimate is not
    ready yet; both must not be shown as an ETA.

    Args:
        value: Raw seconds value.

    Returns:
        Seconds as int, or None if missing/negative/unparseable.
    """
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return None
    return seconds if seconds >= 0 else None


def get_credential(config: AppConfig) -> Optional[str]:
    """
    Look up the configured password / API key.

    Two lookup methods, in order:
    1. password_key reference (e.g. "prusalink:mk4-office")
    2. Legacy: username + printer_base_url (stored as "url:username")

    Args:
        config: Application configuration.

    Returns:
        The secret, or None if not configured/found.
    """
    if config.password_key:
        secret = keyring_util.get_secret(config.password_key)
        if secret:
            return secret
        logger.warning(f"No credential stored for '{config.password_key}'")

    # Fall through to the legacy lookup: credentials saved from the settings
    # dialog live under url:username, with no password_key in the config file.
    if config.username and config.printer_base_url:
        secret = keyring_util.get_password(config.printer_base_url, config.username)
        if secret:
            return secret
        logger.warning("No credential in keyring (legacy url:username lookup)")

    return None


def build_auth_headers(config: AppConfig) -> Dict[bytes, bytes]:
    """
    Build authentication headers for a PrusaLink/OctoPrint request.

    PrusaLink on Buddy firmware (MK4/XL/MINI) guards the whole /api tree and
    accepts the PrusaLink password as X-Api-Key, so the header is sent in both
    "apikey" and "digest" mode. Real Digest challenge/response is handled by Qt
    via QNetworkAccessManager.authenticationRequired (see HttpJsonAdapter), which
    is what standalone PrusaLink (MK3) and the PrusaLink web UI use.

    Args:
        config: Application configuration.

    Returns:
        Dictionary of header name -> header value (as bytes).
    """
    if config.auth_mode not in ("apikey", "digest"):
        return {}

    secret = get_credential(config)
    if not secret:
        return {}

    logger.debug("Added X-Api-Key header")
    return {b"X-Api-Key": secret.encode("utf-8")}


# ============================================================================
# DEMO ADAPTER PARSING
# ============================================================================


def parse_demo_state(
    status: PrinterStatus,
    progress: float = 0.0,
    eta_seconds: Optional[int] = None,
    job_name: Optional[str] = None,
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
        last_ok_timestamp=datetime.now(),
    )


# ============================================================================
# PRUSA CONNECT PARSING
# ============================================================================


# Job states that mean "there is a print running right now". Everything else
# in the Job.state enum (FIN_OK, FIN_ERROR, FIN_STOPPED, FIN_HARVESTED, UNKNOWN)
# is a finished job that Connect still lists as the printer's most recent one.
CONNECT_ACTIVE_JOB_STATES = ("PRINTING", "PAUSED")


def parse_prusa_connect_state(
    printer: Dict[str, Any], job: Optional[Dict[str, Any]] = None
) -> PrinterState:
    """
    Parse a Prusa Connect response into a PrinterState.

    Shapes come from the published Connect mobile API OpenAPI spec
    (https://connect-mobile-api.prusa3d.com/api/docs).

    printer - GET /api/v1/printers/{uuid}:
    {
      "uuid": "...", "name": "MK4 Office", "state": "PRINTING",
      "telemetry": {"temperatureNozzleCurrent": 214.9, "temperatureNozzleTarget": 215.0,
                    "temperatureHeatbedCurrent": 59.5, "temperatureHeatbedTarget": 60.0,
                    "axisZ": 0.5, "speed": 100, "lastOnline": "..."}
    }

    job - first element of GET /api/v1/jobs?printer={uuid}:
    {
      "id": "...", "state": "PRINTING", "progress": 42.0, "fileName": "benchy.gcode",
      "endAt": 1706749200, "estimatedPrintTime": 7200
    }

    Args:
        printer: Printer resource from Connect.
        job: Most recent job for that printer, if any.

    Returns:
        PrinterState.
    """
    try:
        printer = printer or {}
        telemetry = printer.get("telemetry") or {}

        status = normalize_status(printer.get("state"))

        # Only report progress/ETA/file for a job that is actually running -
        # Connect keeps returning the last finished job forever otherwise.
        progress = eta_seconds = job_name = None
        if job and job.get("state") in CONNECT_ACTIVE_JOB_STATES:
            progress = normalize_progress(job.get("progress"))
            job_name = job.get("fileName")
            eta_seconds = _connect_eta(job)

        return PrinterState(
            status=status,
            progress=progress,
            eta_seconds=eta_seconds,
            job_name=job_name,
            nozzle_temp=telemetry.get("temperatureNozzleCurrent"),
            bed_temp=telemetry.get("temperatureHeatbedCurrent"),
            last_ok_timestamp=datetime.now(),
        )

    except Exception as e:
        logger.error(f"Error parsing PrusaConnect state: {e}", exc_info=True)
        return PrinterState(
            status=PrinterStatus.ERROR,
            error_message=f"Parse error: {str(e)}",
            last_ok_timestamp=datetime.now(),
        )


def _connect_eta(job: Dict[str, Any]) -> Optional[int]:
    """
    Derive remaining seconds from a Connect job.

    Connect reports an absolute finish time (endAt, unix seconds) rather than a
    countdown, so subtract now. Falls back to estimatedPrintTime scaled by the
    remaining fraction when endAt is missing.

    Args:
        job: Job resource from Connect.

    Returns:
        Seconds remaining, or None.
    """
    end_at = positive_seconds(job.get("endAt"))
    if end_at:
        return positive_seconds(end_at - time.time())

    estimated = positive_seconds(job.get("estimatedPrintTime"))
    fraction = normalize_progress(job.get("progress"))
    if estimated is not None and fraction is not None:
        return int(estimated * (1.0 - fraction))
    return None


# ============================================================================
# PRUSALINK PARSING
# ============================================================================


def parse_prusalink_state(
    data: Dict[str, Any], job_name: Optional[str] = None
) -> PrinterState:
    """
    Parse a PrusaLink API response (v1 or legacy format).

    1. PrusaLink API v1 (GET /api/v1/status), per the published OpenAPI spec:
    {
      "printer": {"state": "PRINTING", "temp_nozzle": 214.9, "target_nozzle": 215.0,
                  "temp_bed": 59.5, "target_bed": 60.0, "axis_z": 0.5,
                  "flow": 95, "speed": 100, "fan_hotend": 0, "fan_print": 0,
                  "status_printer": {"ok": true, "message": "..."},
                  "status_connect": {"ok": true, "message": "..."}},
      "job": {"id": 420, "progress": 42.0, "time_remaining": 520, "time_printing": 526}
    }
    Note that /api/v1/status carries NO file name - the printing file is only
    available from GET /api/v1/job, which PrusaLinkAdapter fetches separately and
    passes in as job_name.

    2. Legacy format (GET /api/job, PrusaLink 0.7 / OctoPrint-compatible):
    {
      "state": "Printing",
      "job": {"file": {"name": "model.gcode"}},
      "progress": {"completion": 0.88, "printTimeLeft": 960},
      "temperature": {"tool0": {"actual": 215}, "bed": {"actual": 60}}
    }

    Args:
        data: Parsed JSON from the PrusaLink API.
        job_name: File name from /api/v1/job, if already known (v1 only).

    Returns:
        PrinterState.
    """
    try:
        if "printer" in data:
            # --- API v1 -----------------------------------------------------
            printer = data.get("printer") or {}
            job = data.get("job") or {}

            status = normalize_status(printer.get("state"))

            # status_printer/status_connect explain ATTENTION and ERROR states.
            message = None
            for key in ("status_printer", "status_connect"):
                info = printer.get(key)
                if isinstance(info, dict) and not info.get("ok", True):
                    message = info.get("message") or message

            return PrinterState(
                status=status,
                progress=normalize_progress(job.get("progress")),
                eta_seconds=positive_seconds(job.get("time_remaining")),
                job_name=job_name,
                nozzle_temp=printer.get("temp_nozzle"),
                bed_temp=printer.get("temp_bed"),
                message=message,
                last_ok_timestamp=datetime.now(),
            )

        # --- Legacy /api/job ------------------------------------------------
        status = normalize_status(data.get("state"))

        temp_data = data.get("temperature") or {}
        tool_temp = temp_data.get("tool0") or {}
        bed_temp_data = temp_data.get("bed") or {}

        job = data.get("job")
        progress_data = data.get("progress")

        progress = None
        eta_seconds = None
        if progress_data:
            progress = normalize_progress(progress_data.get("completion"))
            eta_seconds = positive_seconds(progress_data.get("printTimeLeft"))

        legacy_name = None
        if isinstance(job, dict):
            file_info = job.get("file")
            if isinstance(file_info, dict):
                legacy_name = file_info.get("display_name") or file_info.get("name")

        return PrinterState(
            status=status,
            progress=progress,
            eta_seconds=eta_seconds,
            job_name=legacy_name,
            nozzle_temp=(
                tool_temp.get("actual") if isinstance(tool_temp, dict) else None
            ),
            bed_temp=(
                bed_temp_data.get("actual") if isinstance(bed_temp_data, dict) else None
            ),
            last_ok_timestamp=datetime.now(),
        )

    except Exception as e:
        logger.error(f"Error parsing PrusaLink state: {e}", exc_info=True)
        return PrinterState(
            status=PrinterStatus.ERROR,
            error_message=f"Parse error: {str(e)}",
            last_ok_timestamp=datetime.now(),
        )


def parse_prusalink_job_name(data: Dict[str, Any]) -> Optional[str]:
    """
    Extract the printing file name from a GET /api/v1/job response.

    Args:
        data: Parsed JSON from /api/v1/job.

    Returns:
        Long file name (falling back to the 8.3 short name), or None for a
        serial print / no job.
    """
    file_info = (data or {}).get("file")
    if not isinstance(file_info, dict):
        return None
    return file_info.get("display_name") or file_info.get("name")


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
            last_ok_timestamp=datetime.now(),
        )

    except Exception as e:
        logger.error(f"Error parsing OctoPrint state: {e}", exc_info=True)
        return PrinterState(
            status=PrinterStatus.OFFLINE,
            error_message=f"Parse error: {str(e)}",
            message="Failed to parse OctoPrint response",
            last_ok_timestamp=datetime.now(),
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
                job_name="demo_model.gcode",
            )
        elif cycle_time < self._duration + 10:
            # Paused phase
            return parse_demo_state(
                status=PrinterStatus.PAUSED,
                progress=0.75,
                eta_seconds=30,
                job_name="demo_model.gcode",
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

    def __init__(
        self,
        base_url: str,
        config: Optional[AppConfig] = None,
        parent: Optional[QObject] = None,
    ):
        """
        Initialize HTTP adapter.

        Args:
            base_url: Base URL of the printer (e.g., "http://192.168.1.100")
            config: Application configuration (for auth).
            parent: Parent QObject.
        """
        super().__init__(parent)
        self.base_url = base_url.rstrip("/")
        self.config = config
        self._network_manager = QNetworkAccessManager(self)
        self._network_manager.authenticationRequired.connect(self._authenticate)
        self._last_http_status: Optional[int] = None
        self._auth_attempted = False

    def _authenticate(self, reply: QNetworkReply, authenticator) -> None:
        """
        Answer an HTTP Digest (or Basic) challenge.

        Qt does the challenge/response itself; we only supply the credentials.
        This is how PrusaLink's documented digestAuth scheme is satisfied.
        Answering the same challenge twice means the credentials are wrong, so
        we refuse the second time instead of letting Qt loop.
        """
        if self._auth_attempted or not self.config:
            logger.error("Authentication rejected - check username/password")
            return

        password = get_credential(self.config)
        if not password:
            return

        self._auth_attempted = True
        authenticator.setUser(self.config.username or "maker")
        authenticator.setPassword(password)
        logger.debug("Answered auth challenge for user %s", self.config.username)

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

    def _read_json(self, reply: QNetworkReply, required: bool = True) -> Optional[Any]:
        """
        Decode a reply body, emitting state_error on failure.

        Args:
            reply: Finished reply.
            required: When False, a failed reply yields None without an error
                signal (the caller can still emit a useful partial state).

        Returns:
            Parsed JSON, or None if the request failed.
        """
        import json

        http_status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        self._last_http_status = http_status

        if reply.error() != QNetworkReply.NetworkError.NoError:
            message = (
                "Auth failed - check credentials"
                if http_status in (401, 403)
                else reply.errorString()
            )
            logger.warning(f"{self.base_url} request failed: {message}")
            if required:
                self.state_error.emit(message)
            return None

        try:
            return json.loads(bytes(reply.readAll()).decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as e:
            logger.error(f"Invalid JSON from {self.base_url}: {e}")
            if required:
                self.state_error.emit(f"Invalid JSON: {e}")
            return None

    def build_request(self, path: str) -> QNetworkRequest:
        """
        Build an authenticated JSON GET request for a path on this backend.

        Args:
            path: Path (and query) to append to the base URL.

        Returns:
            Configured QNetworkRequest with a 5s transfer timeout.
        """
        url = QUrl(f"{self.base_url}{path}")
        request = QNetworkRequest(url)
        request.setTransferTimeout(5000)  # 5s timeout - fail fast for better UX
        request.setRawHeader(b"Accept", b"application/json")

        if self.config:
            for name, value in build_auth_headers(self.config).items():
                request.setRawHeader(name, value)

        # One digest challenge answer per request; a repeat means bad credentials.
        self._auth_attempted = False
        logger.debug(f"Fetching {url.toString()}")
        return request

    def fetch_state_async(self) -> None:
        """
        Fetch state asynchronously.

        Emits state_fetched on success or state_error on failure.
        Does NOT block. Uses 5-second timeout for responsiveness.
        """
        reply = self._network_manager.get(self.build_request(self.endpoint))
        reply.finished.connect(lambda: self._handle_reply(reply))

    def _handle_reply(self, reply: QNetworkReply) -> None:
        """
        Handle network reply with comprehensive error handling.

        Never throws - always emits either state_fetched or state_error.
        Handles malformed JSON gracefully.
        """
        try:
            error = reply.error()
            http_status = reply.attribute(
                QNetworkRequest.Attribute.HttpStatusCodeAttribute
            )
            self._last_http_status = http_status

            if error == QNetworkReply.NetworkError.NoError:
                # Success - parse response
                data = reply.readAll().data()

                # Parse JSON with error handling
                try:
                    import json

                    parsed = json.loads(data.decode("utf-8"))
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON from {self.base_url}: {e}")
                    error_state = PrinterState(
                        status=PrinterStatus.ERROR,
                        error_message="Invalid JSON response",
                        message=f"Server returned malformed JSON: {str(e)[:100]}",
                    )
                    self.state_fetched.emit(error_state)
                    return
                except UnicodeDecodeError as e:
                    logger.error(f"Invalid encoding from {self.base_url}: {e}")
                    error_state = PrinterState(
                        status=PrinterStatus.ERROR,
                        error_message="Invalid response encoding",
                        message="Server returned non-UTF8 data",
                    )
                    self.state_fetched.emit(error_state)
                    return

                # Parse to PrinterState
                try:
                    state = self.parse_response(parsed)
                    state.last_ok_timestamp = datetime.now()
                    self.state_fetched.emit(state)
                except Exception as e:
                    logger.error(
                        f"Failed to parse response from {self.base_url}: {e}",
                        exc_info=True,
                    )
                    error_state = PrinterState(
                        status=PrinterStatus.ERROR,
                        error_message="Parse error",
                        message=f"Could not parse printer state: {str(e)[:100]}",
                    )
                    self.state_fetched.emit(error_state)

            elif http_status == 401 or http_status == 403:
                # Authentication failure
                error_msg = f"Authentication failed (HTTP {http_status})"
                logger.error(f"{self.base_url}: {error_msg}")
                error_state = PrinterState(
                    status=PrinterStatus.ERROR,
                    error_message="Authentication failed",
                    message="Check credentials in configuration",
                )
                self.state_fetched.emit(error_state)

            elif http_status == 404:
                # Not found - might be wrong endpoint
                error_msg = f"Endpoint not found (HTTP 404): {self.endpoint}"
                logger.error(f"{self.base_url}: {error_msg}")
                error_state = PrinterState(
                    status=PrinterStatus.ERROR,
                    error_message="Endpoint not found",
                    message=f"API endpoint {self.endpoint} does not exist",
                )
                self.state_fetched.emit(error_state)

            elif http_status and 500 <= http_status < 600:
                # Server error
                error_msg = f"Server error (HTTP {http_status})"
                logger.warning(f"{self.base_url}: {error_msg}")
                error_state = PrinterState(
                    status=PrinterStatus.ERROR,
                    error_message="Server error",
                    message=f"Printer returned HTTP {http_status}",
                )
                self.state_fetched.emit(error_state)

            elif error == QNetworkReply.NetworkError.TimeoutError:
                # Timeout
                logger.warning(f"{self.base_url}: Request timeout (5s)")
                error_state = PrinterState(
                    status=PrinterStatus.ERROR,
                    error_message="Timeout",
                    message="Printer did not respond within 5 seconds",
                )
                self.state_fetched.emit(error_state)

            elif error == QNetworkReply.NetworkError.HostNotFoundError:
                # Host not found
                logger.warning(f"{self.base_url}: Host not found")
                error_state = PrinterState(
                    status=PrinterStatus.ERROR,
                    error_message="Host not found",
                    message="Could not resolve printer hostname/IP",
                )
                self.state_fetched.emit(error_state)

            elif error == QNetworkReply.NetworkError.ConnectionRefusedError:
                # Connection refused
                logger.warning(f"{self.base_url}: Connection refused")
                error_state = PrinterState(
                    status=PrinterStatus.ERROR,
                    error_message="Connection refused",
                    message="Printer refused connection - is it powered on?",
                )
                self.state_fetched.emit(error_state)

            else:
                # Generic network error
                error_string = reply.errorString()
                logger.warning(f"{self.base_url}: Network error: {error_string}")
                error_state = PrinterState(
                    status=PrinterStatus.ERROR,
                    error_message="Network error",
                    message=error_string[:100],
                )
                self.state_fetched.emit(error_state)

        except Exception as e:
            # Catch-all for unexpected errors
            logger.error(
                f"Unexpected error handling reply from {self.base_url}: {e}",
                exc_info=True,
            )
            try:
                error_state = PrinterState(
                    status=PrinterStatus.ERROR,
                    error_message="Internal error",
                    message=str(e)[:100],
                )
                self.state_fetched.emit(error_state)
            except Exception as emit_error:
                # Last resort - log but don't crash
                logger.critical(f"Failed to emit error state: {emit_error}")
        finally:
            reply.deleteLater()

    def get_last_http_status(self) -> Optional[int]:
        """Get the last HTTP status code received."""
        return self._last_http_status


# ============================================================================
# CONCRETE HTTP ADAPTERS (Stubbed)
# ============================================================================


class PrusaLinkAdapter(HttpJsonAdapter):
    """
    PrusaLink local API adapter.

    Primary: PrusaLink API v1 (GET /api/v1/status), the documented API on Buddy
    firmware (MK4/MK3.9/XL/MINI) and PrusaLink 0.8+. /api/v1/status carries no
    file name, so the current job's name is fetched once per job from
    GET /api/v1/job and reused until the job id changes.

    Fallback: the legacy OctoPrint-shaped GET /api/job, for PrusaLink 0.7.x,
    used automatically if /api/v1/status returns 404.
    """

    def __init__(
        self,
        base_url: str,
        config: Optional[AppConfig] = None,
        parent: Optional[QObject] = None,
    ):
        """Initialize PrusaLink adapter."""
        super().__init__(base_url, config, parent)
        self._use_legacy = False
        self._job_id: Optional[Any] = None
        self._job_name: Optional[str] = None

    @property
    def endpoint(self) -> str:
        """Status endpoint for the detected API generation."""
        return "/api/job" if self._use_legacy else "/api/v1/status"

    def parse_response(self, data: Dict[str, Any]) -> PrinterState:
        """Parse a status response, refreshing the cached job name if needed."""
        if not self._use_legacy:
            job_id = (data.get("job") or {}).get("id")
            if job_id != self._job_id:
                # New job (or job ended): drop the stale name and look it up.
                self._job_id, self._job_name = job_id, None
                if job_id is not None:
                    self._fetch_job_name()
        return parse_prusalink_state(data, self._job_name)

    def _handle_reply(self, reply: QNetworkReply) -> None:
        """Handle a status reply, falling back to the legacy endpoint on 404."""
        http_status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if http_status == 404 and not self._use_legacy:
            logger.info("No /api/v1/status on this printer, using legacy /api/job")
            self._use_legacy = True
            reply.deleteLater()
            # Start the retry from the event loop; issuing a request from inside
            # a finished handler re-enters QNetworkAccessManager and can crash.
            QTimer.singleShot(0, self.fetch_state_async)
            return
        super()._handle_reply(reply)

    def _fetch_job_name(self) -> None:
        """Fetch the current job's file name from /api/v1/job (fire and forget)."""

        def request():
            reply = self._network_manager.get(self.build_request("/api/v1/job"))
            reply.finished.connect(lambda: self._store_job_name(reply))

        # parse_response runs inside a finished handler; defer the extra request.
        QTimer.singleShot(0, request)

    def _store_job_name(self, reply: QNetworkReply) -> None:
        """
        Cache the job name from a /api/v1/job reply.

        The name shows up on the next poll; a failure here (204 No Content when
        the job just ended, or an offline printer) only means no name is shown.
        """
        data = self._read_json(reply, required=False)
        reply.deleteLater()
        if isinstance(data, dict):
            self._job_name = parse_prusalink_job_name(data)
            logger.debug(f"Job {self._job_id} name: {self._job_name}")


class PrusaConnectAdapter(HttpJsonAdapter):
    """
    Prusa Connect cloud adapter, using the documented Connect mobile API gateway
    at https://connect-mobile-api.prusa3d.com (see /api/docs for the OpenAPI spec).

    Two requests per poll, because Connect splits the data:
      GET /api/v1/printers/{uuid}      -> state + telemetry (temperatures)
      GET /api/v1/jobs?printer={uuid}  -> progress, file name, finish time

    Configuration requirements:
    - bearer_token: JWT for the Authorization header (from a signed-in Connect
      session; Prusa publishes no token-issuing endpoint, so it is supplied by hand)
    - printer_uuid: printer UUID, as listed by GET /api/v1/printers
    """

    DEFAULT_BASE_URL = "https://connect-mobile-api.prusa3d.com"

    def __init__(
        self,
        base_url: str,
        config: Optional[AppConfig] = None,
        parent: Optional[QObject] = None,
    ):
        """Initialize the Connect adapter."""
        super().__init__(base_url or self.DEFAULT_BASE_URL, config, parent)

        if not config:
            raise ValueError(
                "PrusaConnect requires configuration with bearer_token and printer_uuid"
            )
        if not config.bearer_token:
            raise ValueError("PrusaConnect requires bearer_token in configuration")
        if not config.printer_uuid:
            raise ValueError("PrusaConnect requires printer_uuid in configuration")

        self._printer_data: Optional[Dict[str, Any]] = None

    @property
    def endpoint(self) -> str:
        """Printer detail endpoint (state + telemetry)."""
        return f"/api/v1/printers/{self.config.printer_uuid}"

    def build_request(self, path: str) -> QNetworkRequest:
        """Build a Connect request carrying the JWT."""
        request = super().build_request(path)
        token = self.config.bearer_token
        # Accept a bare JWT or one the user pasted with its scheme already on it.
        if " " not in token:
            token = f"Bearer {token}"
        request.setRawHeader(b"Authorization", token.encode("utf-8"))
        return request

    def parse_response(self, data: Dict[str, Any]) -> PrinterState:
        """Parse a printer resource on its own (no job info)."""
        return parse_prusa_connect_state(data)

    def fetch_state_async(self) -> None:
        """Fetch the printer resource, then its current job."""
        reply = self._network_manager.get(self.build_request(self.endpoint))
        reply.finished.connect(lambda: self._handle_printer_reply(reply))

    def _handle_printer_reply(self, reply: QNetworkReply) -> None:
        """Store the printer resource, then chain the jobs request."""
        data = self._read_json(reply)
        reply.deleteLater()
        if data is None:
            return

        self._printer_data = data
        # Chain from the event loop, not from inside this finished handler.
        QTimer.singleShot(0, self._fetch_jobs)

    def _fetch_jobs(self) -> None:
        """Fetch the printer's most recent job."""
        path = f"/api/v1/jobs?printer={self.config.printer_uuid}&itemsPerPage=1"
        reply = self._network_manager.get(self.build_request(path))
        reply.finished.connect(lambda: self._handle_jobs_reply(reply))

    def _handle_jobs_reply(self, reply: QNetworkReply) -> None:
        """Combine the job list with the stored printer resource and emit."""
        data = self._read_json(reply, required=False)
        reply.deleteLater()

        # Plain JSON gives a list; the JSON-LD variant wraps it in hydra:member.
        if isinstance(data, dict):
            data = data.get("hydra:member")
        job = data[0] if isinstance(data, list) and data else None

        self.state_fetched.emit(
            parse_prusa_connect_state(self._printer_data or {}, job)
        )


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
