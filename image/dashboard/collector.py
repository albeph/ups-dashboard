"""Background telemetry collection, thread-safe cache, and standby/wake activity tracking."""

import logging
import threading
import time
from typing import Any, Callable, Dict, Optional

from .config import ConfigManager
from .nut import NutClient, NutMetrics

logger = logging.getLogger("ups-dashboard.collector")


class NUTDataCache:
    """Thread-safe in-memory cache storing the latest UPS telemetry snapshot."""

    def __init__(self):
        self.lock = threading.Lock()
        self.status = "connecting"
        self.watts: Optional[int] = None
        self.nominal_watts: Optional[int] = None
        self.load: int = 0
        self.battery: int = 100
        self.battery_charge_low: Optional[int] = None
        self.battery_runtime: Optional[int] = None
        self.battery_runtime_low: Optional[int] = None
        self.voltage: Optional[float] = None
        self.ups_status = "Connecting..."
        self.ups_status_raw = ""
        self.ups_model = ""
        self.last_update: float = 0.0
        self.error_message = ""

    def update_metrics(self, metrics: NutMetrics) -> None:
        """Store a fresh ``NutMetrics`` snapshot in the cache."""
        with self.lock:
            self.status = metrics.status
            self.watts = metrics.watts
            self.nominal_watts = metrics.nominal_watts
            self.load = metrics.load
            self.battery = metrics.battery
            self.battery_charge_low = metrics.battery_charge_low
            self.battery_runtime = metrics.battery_runtime
            self.battery_runtime_low = metrics.battery_runtime_low
            self.voltage = metrics.voltage
            self.ups_status = metrics.ups_status
            self.ups_status_raw = metrics.ups_status_raw
            self.ups_model = metrics.ups_model
            self.error_message = metrics.error_message
            self.last_update = time.time()

    def update_offline(self, error_message: str) -> None:
        """Reset live telemetry fields and mark the NUT connection as offline."""
        with self.lock:
            self.status = "offline"
            self.watts = None
            self.nominal_watts = None
            self.load = 0
            self.battery = 0
            self.battery_charge_low = None
            self.battery_runtime = None
            self.battery_runtime_low = None
            self.voltage = None
            self.ups_status = "Disconnected"
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
        battery_charge_low: Optional[int] = None,
        battery_runtime: Optional[int] = None,
        battery_runtime_low: Optional[int] = None,
    ) -> None:
        """Directly update cache fields from individual keyword arguments."""
        self.update_metrics(
            NutMetrics(
                status=status,
                watts=watts,
                nominal_watts=nominal_watts,
                load=load,
                battery=battery,
                voltage=voltage,
                ups_status=ups_status,
                ups_status_raw=ups_status_raw,
                ups_model=ups_model,
                error_message=error_message,
                battery_charge_low=battery_charge_low,
                battery_runtime=battery_runtime,
                battery_runtime_low=battery_runtime_low,
            )
        )

    def get_data(self) -> Dict[str, Any]:
        """Return a thread-safe dictionary copy of the current telemetry state."""
        with self.lock:
            return {
                "status": self.status,
                "watts": self.watts,
                "nominal_watts": self.nominal_watts,
                "load": self.load,
                "battery": self.battery,
                "battery_charge_low": self.battery_charge_low,
                "battery_runtime": self.battery_runtime,
                "battery_runtime_low": self.battery_runtime_low,
                "voltage": self.voltage,
                "ups_status": self.ups_status,
                "ups_status_raw": self.ups_status_raw,
                "ups_model": self.ups_model,
                "last_update": self.last_update,
                "error_message": self.error_message,
            }


class ActivityTracker:
    """Coordinates demand-driven NUT polling suspension (standby) and instant wake-up."""

    MIN_IDLE_TIMEOUT_SECONDS = 10.0
    IDLE_POLL_MULTIPLIER = 2.5

    def __init__(self):
        self._lock = threading.Lock()
        self._last_activity = time.time()
        self._wake_event = threading.Event()
        self._fresh_poll_event = threading.Event()
        self._is_suspended = False

    def get_idle_timeout(self, poll_interval: float) -> float:
        """Compute inactivity duration (in seconds) before entering standby."""
        return max(self.MIN_IDLE_TIMEOUT_SECONDS, poll_interval * self.IDLE_POLL_MULTIPLIER)

    def record_activity(self) -> bool:
        """Record an incoming client request and wake the poller if suspended.

        Returns True if the poller was suspended prior to this call.
        """
        with self._lock:
            was_suspended = self._is_suspended
            self._last_activity = time.time()
            self._wake_event.set()
            return was_suspended

    def is_idle(self, poll_interval: float) -> bool:
        """Return True if no client has polled within the computed idle timeout."""
        with self._lock:
            return (time.time() - self._last_activity) > self.get_idle_timeout(poll_interval)

    def wait_for_fresh_poll(self, timeout: float = 2.0) -> None:
        """Block briefly until the woken poller finishes a fresh NUT query."""
        self._wake_event.set()
        self._fresh_poll_event.wait(timeout=timeout)

    def mark_suspended(self) -> None:
        """Transition tracker state to suspended and reset wake/fresh-poll signals."""
        with self._lock:
            self._fresh_poll_event.clear()
            self._wake_event.clear()
            self._is_suspended = True

    def mark_resumed(self) -> None:
        """Transition tracker state back to active."""
        with self._lock:
            self._is_suspended = False

    def wait_for_wake(self) -> None:
        """Block the poller thread until a client wakes it or shutdown is requested."""
        self._wake_event.wait()

    def notify_poll_complete(self) -> None:
        """Signal any waiting HTTP request that fresh telemetry is now available."""
        self._fresh_poll_event.set()


class NutPoller:
    """Background daemon thread that polls the NUT server only while web clients are active."""

    def __init__(
        self,
        config: ConfigManager,
        cache: NUTDataCache,
        tracker: Optional[ActivityTracker] = None,
        client_factory: Callable[..., NutClient] = NutClient,
    ):
        self.config = config
        self.cache = cache
        self.tracker = tracker or ActivityTracker()
        self._client_factory = client_factory
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Launch the background polling thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="nut-poller")
        self._thread.start()

    def stop(self) -> None:
        """Request graceful termination of the background polling thread."""
        self._stop_event.set()
        self.tracker.record_activity()  # Unblock if currently sleeping in standby
        self.config.reload_event.set()

    def _run(self) -> None:
        """Main polling loop: suspend when idle, fetch metrics when active, sleep until next cycle."""
        first_run = True

        while not self._stop_event.is_set():
            poll_interval = float(self.config.get("poll_interval", 2.0))

            if not first_run and not self._wait_if_idle(poll_interval):
                break

            first_run = False
            self.config.reload_event.clear()
            self._poll_once()

            # Wait for the polling interval or wake immediately if settings are updated.
            self.config.reload_event.wait(timeout=poll_interval)

    def _wait_if_idle(self, poll_interval: float) -> bool:
        """Suspend polling if no clients are active. Returns False if stop was requested."""
        if not self.tracker.is_idle(poll_interval):
            return True

        idle_timeout = round(self.tracker.get_idle_timeout(poll_interval))
        self.tracker.mark_suspended()
        logger.info(
            "No active clients in the last %ss: NUT polling suspended (standby).",
            idle_timeout,
        )
        self.tracker.wait_for_wake()
        if self._stop_event.is_set():
            return False

        self.tracker.mark_resumed()
        logger.info("Active client detected: NUT polling resumed.")
        return True

    def _poll_once(self) -> None:
        """Execute a single NUT telemetry fetch and update the shared cache."""
        try:
            client = self._client_factory(
                host=self.config.get("nut_host"),
                port=self.config.get("nut_port"),
                ups_name=self.config.get("ups_name"),
                user=self.config.get("nut_user"),
                password=self.config.get_nut_password(),
            )
            metrics = client.fetch_metrics()
            self.cache.update_metrics(metrics)
        except Exception as exc:
            self.cache.update_offline(str(exc))
        finally:
            self.tracker.notify_poll_complete()
