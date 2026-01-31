"""Data models for printer state and application data."""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional


class PrinterStatus(Enum):
    """Printer status enumeration."""
    IDLE = "idle"
    PRINTING = "printing"
    PAUSED = "paused"
    ERROR = "error"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


@dataclass
class PrinterState:
    """Complete printer state snapshot."""
    status: PrinterStatus
    progress: Optional[float] = None  # 0.0-1.0 (normalized)
    eta_seconds: Optional[int] = None  # Remaining time in seconds
    job_name: Optional[str] = None
    nozzle_temp: Optional[float] = None  # Current nozzle temperature (°C)
    bed_temp: Optional[float] = None  # Current bed temperature (°C)
    message: Optional[str] = None  # Status message from printer
    error_message: Optional[str] = None  # Error message if status is ERROR
    last_ok_timestamp: Optional[datetime] = None  # Last successful poll
    last_error: Optional[str] = None  # Last network/parse error
    
    @property
    def progress_percent(self) -> Optional[float]:
        """Get progress as percentage (0-100) for backward compatibility."""
        return self.progress * 100 if self.progress is not None else None
    
    def get_tooltip_text(self) -> str:
        """Generate tooltip text for the tray icon."""
        lines = [f"Status: {self.status.value}"]
        
        if self.progress is not None:
            lines.append(f"Progress: {self.progress * 100:.1f}%")
        
        if self.eta_seconds is not None:
            hours, remainder = divmod(self.eta_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            if hours > 0:
                eta_str = f"{hours}h {minutes}m"
            else:
                eta_str = f"{minutes}m {seconds}s"
            lines.append(f"ETA: {eta_str}")
        
        if self.job_name:
            lines.append(f"Job: {self.job_name}")
        
        # Temperature info
        if self.nozzle_temp is not None:
            lines.append(f"Nozzle: {self.nozzle_temp:.1f}°C")
        if self.bed_temp is not None:
            lines.append(f"Bed: {self.bed_temp:.1f}°C")
        
        # Messages
        if self.message:
            lines.append(f"Info: {self.message}")
        
        if self.error_message:
            lines.append(f"Error: {self.error_message}")
        
        # Show offline status with last error
        if self.status == PrinterStatus.OFFLINE and self.last_error:
            # Truncate error to first line, max 60 chars
            short_error = self.last_error.split('\n')[0][:60]
            lines.append(f"Last error: {short_error}")
        
        # Show last successful poll time if available
        if self.last_ok_timestamp:
            elapsed = (datetime.now() - self.last_ok_timestamp).total_seconds()
            if elapsed < 60:
                lines.append(f"Last OK: {int(elapsed)}s ago")
            elif elapsed < 3600:
                lines.append(f"Last OK: {int(elapsed/60)}m ago")
        
        return "\n".join(lines)


@dataclass
class AppConfig:
    """Application configuration."""
    printer_base_url: Optional[str] = None
    poll_interval_s: float = 3.0
    backend: str = "demo"  # "demo", "prusaconnect", "prusalink", "octoprint"
    open_ui_path: str = "/"  # Path to append to base URL for "Open printer UI"
    icon_style: str = "ring"  # "ring" or "bar" (legacy)
    
    # Authentication settings
    username: Optional[str] = None  # Username for digest auth or API key name
    auth_mode: str = "none"  # "none", "digest", "apikey"
    password_key: Optional[str] = None  # Reference key for password in keyring (e.g., "prusalink:mk4-office")
    # Note: password/API key stored securely in keyring or env var, NOT in config
    
    # PrusaConnect specific settings
    bearer_token: Optional[str] = None  # Bearer token for PrusaConnect authentication
    printer_id: Optional[str] = None  # Printer ID for PrusaConnect
    status_path: Optional[str] = None  # Custom endpoint path (defaults to /api/v1/status)
    
    @property
    def polling_interval_seconds(self) -> float:
        """Backward compatibility property."""
        return self.poll_interval_s
