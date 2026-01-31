"""Polling service for fetching printer state using adapters."""

import logging
import random
from datetime import datetime
from typing import Optional

from PySide6.QtCore import QObject, QTimer, Signal

from .models import PrinterState, PrinterStatus
from .adapters import BaseAdapter, DemoAdapter, HttpJsonAdapter

logger = logging.getLogger(__name__)


class PrinterPoller(QObject):
    """
    Polls printer for status updates using pluggable adapters.
    
    Design:
    - Adapter pattern allows swapping backends without changing poller logic
    - Synchronous adapters (DemoAdapter) called directly
    - Async adapters (HttpJsonAdapter subclasses) use signals
    - Backoff applied on failures regardless of adapter type
    
    Features:
    - Non-blocking: never freezes UI
    - Timeouts: handled by adapters
    - Backoff: exponential with jitter on failures (3s → 30s)
    - Recovery: returns to normal interval on success
    - State tracking: last_ok_timestamp, last_error
    """
    
    # Signal emitted when state is updated
    state_updated = Signal(PrinterState)
    
    def __init__(
        self,
        adapter: BaseAdapter,
        interval_seconds: float = 3.0,
        parent: Optional[QObject] = None
    ):
        """
        Initialize the poller.
        
        Args:
            adapter: Adapter instance for fetching state.
            interval_seconds: Normal polling interval in seconds.
            parent: Parent QObject.
        """
        super().__init__(parent)
        
        self.adapter = adapter
        self.interval_seconds = interval_seconds
        
        # Timer for scheduling polls
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._poll)
        self._timer.setSingleShot(True)  # Manual reschedule for backoff
        
        # Backoff state
        self._consecutive_failures = 0
        self._min_backoff = 3.0  # seconds
        self._max_backoff = 30.0  # seconds
        
        # Track last state
        self._last_ok_timestamp: Optional[datetime] = None
        self._last_error: Optional[str] = None
        
        # Connect to async adapter signals if applicable
        if isinstance(adapter, HttpJsonAdapter):
            adapter.state_fetched.connect(self._handle_success)
            adapter.state_error.connect(self._handle_error)
    
    def start(self) -> None:
        """Start polling."""
        adapter_name = type(self.adapter).__name__
        logger.info(f"Starting poller (interval: {self.interval_seconds}s, adapter: {adapter_name})")
        self._consecutive_failures = 0
        self._poll()  # Immediate first poll
    
    def stop(self) -> None:
        """Stop polling."""
        logger.info("Stopping poller")
        self._timer.stop()
    
    def set_interval(self, interval_seconds: float) -> None:
        """
        Update polling interval.
        
        Args:
            interval_seconds: New interval in seconds.
        """
        self.interval_seconds = interval_seconds
        logger.info(f"Updated polling interval to {interval_seconds}s")
    
    def set_adapter(self, adapter: BaseAdapter) -> None:
        """
        Update adapter (backend swap).
        
        Args:
            adapter: New adapter instance.
        """
        # Disconnect old adapter signals
        if isinstance(self.adapter, HttpJsonAdapter):
            try:
                self.adapter.state_fetched.disconnect(self._handle_success)
                self.adapter.state_error.disconnect(self._handle_error)
            except:
                pass  # Ignore if not connected
        
        self.adapter = adapter
        
        # Connect new adapter signals
        if isinstance(adapter, HttpJsonAdapter):
            adapter.state_fetched.connect(self._handle_success)
            adapter.state_error.connect(self._handle_error)
        
        # Reset state
        self._consecutive_failures = 0
        adapter_name = type(adapter).__name__
        logger.info(f"Switched to adapter: {adapter_name}")
    
    def _schedule_next_poll(self, delay: Optional[float] = None) -> None:
        """
        Schedule the next poll.
        
        Args:
            delay: Delay in seconds. If None, uses current interval/backoff.
        """
        if delay is None:
            if self._consecutive_failures > 0:
                # Exponential backoff with jitter
                base_delay = min(
                    self._min_backoff * (2 ** (self._consecutive_failures - 1)),
                    self._max_backoff
                )
                # Add 0-20% jitter to prevent thundering herd
                jitter = random.uniform(0, 0.2 * base_delay)
                delay = base_delay + jitter
                logger.debug(f"Backoff: {delay:.1f}s (failures: {self._consecutive_failures})")
            else:
                delay = self.interval_seconds
        
        self._timer.start(int(delay * 1000))
    
    def _poll(self) -> None:
        """Perform a single poll operation."""
        try:
            if isinstance(self.adapter, DemoAdapter):
                # Synchronous adapter: call directly
                state = self.adapter.fetch_state()
                self._handle_success(state)
            elif isinstance(self.adapter, HttpJsonAdapter):
                # Async adapter: triggers signals
                self.adapter.fetch_state_async()
            else:
                # Generic synchronous adapter
                state = self.adapter.fetch_state()
                self._handle_success(state)
        except Exception as e:
            logger.error(f"Poll error: {e}", exc_info=True)
            self._handle_error(str(e))
    
    def _handle_success(self, state: PrinterState) -> None:
        """
        Handle successful state fetch.
        
        Args:
            state: Fetched PrinterState.
        """
        # Success: reset backoff
        self._consecutive_failures = 0
        self._last_ok_timestamp = datetime.now()
        self._last_error = None
        
        # Ensure timestamps are set
        if state.last_ok_timestamp is None:
            state.last_ok_timestamp = self._last_ok_timestamp
        
        self.state_updated.emit(state)
        logger.debug(f"Poll success: {state.status.value}")
        
        # Schedule next poll
        self._schedule_next_poll()
    
    def _handle_error(self, error_msg: str) -> None:
        """
        Handle polling error.
        
        Args:
            error_msg: Error message.
        """
        self._consecutive_failures += 1
        self._last_error = error_msg
        
        logger.warning(f"Poll failed ({self._consecutive_failures}): {error_msg}")
        
        # Emit offline state
        offline_state = PrinterState(
            status=PrinterStatus.OFFLINE,
            last_ok_timestamp=self._last_ok_timestamp,
            last_error=error_msg
        )
        self.state_updated.emit(offline_state)
        
        # Schedule with backoff
        self._schedule_next_poll()
