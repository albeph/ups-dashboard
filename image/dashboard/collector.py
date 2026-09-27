"""Background telemetry collection, cache, and client activity tracking for standby mode."""

import logging
import threading
import time
from typing import Any, Dict, Optional

from .config import ConfigManager
from .nut import NutClient, NutMetrics

logger = logging.getLogger("ups-dashboard.collector")


class NUTDataCache:
    """Thread-safe cache holding real-time telemetry from NUT daemon."""

    def __init__(self):
        self.lock = threading.Lock()
        self.status = "connecting"
        self.watts: Optional[int] = None
        self.nominal_watts: Optional[int] = None
        self.load: int = 0
        self.battery: int = 100
        self.voltage: Optional[float] = None
        self.ups_status = "In connessione..."
        self.ups_status_raw = ""
        self.ups_model = ""
        self.last_update: float = 0.0
        self.error_message = ""

    def update_metrics(self, metrics: NutMetrics) -> None:
        """Update cache from a NutMetrics object."""
        with self.lock:
            self.status = metrics.status
            self.watts = metrics.watts
            self.nominal_watts = metrics.nominal_watts
            self.load = metrics.load
            self.battery = metrics.battery
            self.voltage = metrics.voltage
            self.ups_status = metrics.ups_status
            self.ups_status_raw = metrics.ups_status_raw
            self.ups_model = metrics.ups_model
            self.error_message = metrics.error_message
            self.last_update = time.time()

    def update_offline(self, error_message: str) -> None:
        """Mark cache as offline with error message."""
        with self.lock:
            self.status = "offline"
            self.watts = None
            self.nominal_watts = None
            self.load = 0
            self.battery = 0
            self.voltage = None
            self.ups_status = "Disconnesso"
            self.ups_status_raw = ""
            self.ups_model = ""
            self.error_message = error_message
            self.last_update = time.time()

    def update(
        self,
        status: str,
        watts: Optional[int],
        load: int,
        battery: int,
        voltage: Optional[float] = None,
        ups_status: str = "",
        ups_status_raw: str = "",
        ups_model: str = "",
        error_message: str = "",
        nominal_watts: Optional[int] = None,
    ) -> None:
        """Backward-compatible update method."""
        with self.lock:
            self.status = status
            self.watts = watts
            self.nominal_watts = nominal_watts
            self.load = load
            self.battery = battery
            self.voltage = voltage
            self.ups_status = ups_status
            self.ups_status_raw = ups_status_raw
            self.ups_model = ups_model
            self.error_message = error_message
            self.last_update = time.time()

    def get_data(self) -> Dict[str, Any]:
        """Returns snapshot of current telemetry data."""
        with self.lock:
            return {
                "status": self.status,
                "watts": self.watts,
                "nominal_watts": self.nominal_watts,
                "load": self.load,
                "battery": self.battery,
                "voltage": self.voltage,
                "ups_status": self.ups_status,
                "ups_status_raw": self.ups_status_raw,
                "ups_model": self.ups_model,
                "last_update": self.last_update,
                "error_message": self.error_message,
            }


class ActivityTracker:
    """Tracks client activity and coordinates background poller suspension and wake-up."""

    def __init__(self):
        self._lock = threading.Lock()
        self._last_activity = time.time()
        self._wake_event = threading.Event()
        self._fresh_poll_event = threading.Event()
        self._is_suspended = False

    def get_idle_timeout(self, poll_interval: float) -> float:
        """Seconds of client inactivity before suspending NUT polling."""
        return max(10.0, poll_interval * 2.5)

    def record_activity(self) -> bool:
        """Record that an active client made a request. Returns True if poller was suspended."""
        with self._lock:
            was_suspended = self._is_suspended
            self._last_activity = time.time()
            self._wake_event.set()
            return was_suspended

    def is_idle(self, poll_interval: float) -> bool:
        """Check if the idle timeout has expired since last client request."""
        with self._lock:
            return (time.time() - self._last_activity) > self.get_idle_timeout(poll_interval)

    def wait_for_fresh_poll(self, timeout: float = 2.0) -> None:
        """Wait for background worker to complete a fresh query to NUT daemon."""
        self._wake_event.set()
        self._fresh_poll_event.wait(timeout=timeout)

    def mark_suspended(self) -> None:
        with self._lock:
            self._fresh_poll_event.clear()
            self._wake_event.clear()
            self._is_suspended = True

    def mark_resumed(self) -> None:
        with self._lock:
            self._is_suspended = False

    def wait_for_wake(self) -> None:
        self._wake_event.wait()

    def notify_poll_complete(self) -> None:
        self._fresh_poll_event.set()


class NutPoller:
    """Background worker that queries NUT via raw TCP socket only when clients are active."""

    def __init__(
        self,
        config: ConfigManager,
        cache: NUTDataCache,
        tracker: Optional[ActivityTracker] = None,
    ):
        self.config = config
        self.cache = cache
        self.tracker = tracker or ActivityTracker()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Starts the background polling worker thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="nut-poller")
        self._thread.start()

    def stop(self) -> None:
        """Signals the poller thread to stop."""
        self._stop_event.set()
        self.tracker.record_activity()  # Wake up if sleeping
        self.config.reload_event.set()

    def _run(self) -> None:
        first_run = True

        while not self._stop_event.is_set():
            poll_int = self.config.get("poll_interval", 2.0)

            # Suspend polling if no active clients requested data recently
            if not first_run and self.tracker.is_idle(poll_int):
                idle_timeout = round(self.tracker.get_idle_timeout(poll_int))
                self.tracker.mark_suspended()
                print(
                    f"[POLLER] Nessun client attivo negli ultimi {idle_timeout}s: polling NUT sospeso (standby).",
                    flush=True,
                )
                self.tracker.wait_for_wake()
                if self._stop_event.is_set():
                    break
                self.tracker.mark_resumed()
                print("[POLLER] Client attivo rilevato: polling NUT ripreso.", flush=True)

            first_run = False
            self.config.reload_event.clear()

            nut_host = self.config.get("nut_host")
            nut_port = self.config.get("nut_port")
            ups_name = self.config.get("ups_name")
            nut_user = self.config.get("nut_user")
            nut_pwd = self.config.get_nut_password()

            try:
                client = NutClient(
                    host=nut_host,
                    port=nut_port,
                    ups_name=ups_name,
                    user=nut_user,
                    password=nut_pwd,
                )
                metrics = client.fetch_metrics()
                self.cache.update_metrics(metrics)
            except Exception as e:
                self.cache.update_offline(str(e))
            finally:
                self.tracker.notify_poll_complete()

            # Wait for either interval expiration or reload trigger or stop
            self.config.reload_event.wait(timeout=poll_int)
