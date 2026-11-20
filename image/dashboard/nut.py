"""Network UPS Tools (NUT) raw TCP protocol client and telemetry parser."""

import logging
import re
import socket
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, TextIO, Tuple

logger = logging.getLogger("ups-dashboard.nut")


class NutProtocolError(RuntimeError):
    """Raised when the NUT daemon returns a fatal protocol error or drops the connection."""

    def __init__(self, message: str, error_code: Optional[str] = None):
        super().__init__(message)
        self.error_code = error_code


class NutProtocolParser:
    """Stateless parser and formatter for Network UPS Tools (NUT) protocol messages."""

    # Ordered mapping preserving canonical display priority when multiple flags are active.
    STATUS_PRIORITY: List[Tuple[str, str]] = [
        ("OL", "Utility Power"),
        ("OB", "On Battery"),
        ("LB", "Low Battery (LB)"),
        ("CHRG", "Charging"),
        ("DISCHRG", "Discharging"),
        ("BYPASS", "Bypass"),
        ("CAL", "Calibration"),
        ("OVER", "Overload"),
        ("OFF", "Powered Off"),
        ("RB", "Replace Battery"),
    ]

    # Protocol errors that indicate the UPS cannot be queried and polling should fail immediately.
    FATAL_ERRORS = frozenset({
        "UNKNOWN-UPS",
        "DATA-STALE",
        "DRIVER-NOT-CONNECTED",
        "ACCESS-DENIED",
        "INVALID-USERNAME",
        "INVALID-PASSWORD",
        "USERNAME-REQUIRED",
        "PASSWORD-REQUIRED",
    })

    AUTH_ERRORS = frozenset({
        "ACCESS-DENIED",
        "INVALID-USERNAME",
        "INVALID-PASSWORD",
        "USERNAME-REQUIRED",
        "PASSWORD-REQUIRED",
    })

    _VAR_PATTERN = re.compile(r'^VAR\s+[^\s]+\s+[^\s]+\s+"?([^"\r\n]*)"?')

    @classmethod
    def format_status(cls, raw_status: str) -> str:
        """Translate whitespace-separated NUT ``ups.status`` flags into readable English labels."""
        if not raw_status:
            return "Utility Power"
        flags = set(raw_status.strip().upper().split())
        labels = [label for flag, label in cls.STATUS_PRIORITY if flag in flags]
        return " • ".join(labels) if labels else raw_status

    @classmethod
    def format_error(cls, err_code: str, ups_name: str) -> str:
        """Produce a clear, user-facing English message for a NUT protocol error code."""
        if err_code == "UNKNOWN-UPS":
            return f"UPS '{ups_name}' not found on NUT server (ERR {err_code})"
        if err_code == "DATA-STALE":
            return f"Stale UPS data / driver not responding (ERR {err_code})"
        if err_code == "DRIVER-NOT-CONNECTED":
            return f"UPS driver is not connected (ERR {err_code})"
        if err_code in cls.AUTH_ERRORS:
            return f"NUT authentication failed (ERR {err_code})"
        return f"NUT server error (ERR {err_code})"

    @staticmethod
    def parse_error(line: str) -> Optional[str]:
        """Extract the error token from a NUT ``ERR <CODE>`` response, or return None."""
        stripped = line.strip()
        if stripped.startswith("ERR "):
            parts = stripped[4:].strip().split()
            return parts[0] if parts else "UNKNOWN"
        return None

    @classmethod
    def parse_var(cls, line: str) -> Optional[str]:
        """Parse a NUT ``VAR <ups> <name> "<value>"`` response line and return its value."""
        match = cls._VAR_PATTERN.match(line.strip())
        return match.group(1) if match else None

    @staticmethod
    def clean_numeric(value: Optional[str]) -> Optional[float]:
        """Extract a floating-point number from a NUT string value, or return None."""
        if not value:
            return None
        cleaned = "".join(ch for ch in value if ch.isdigit() or ch == ".")
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None


# Backward-compatible module-level aliases delegating to NutProtocolParser.
def format_ups_status(raw_status: str) -> str:
    """Format raw NUT ``ups.status`` flags into human-readable English labels."""
    return NutProtocolParser.format_status(raw_status)


def parse_nut_error(line: str) -> Optional[str]:
    """Parse a NUT protocol ``ERR`` response line and return the error code."""
    return NutProtocolParser.parse_error(line)


def parse_nut_var(line: str) -> Optional[str]:
    """Parse a NUT protocol ``VAR`` response line and return the extracted value."""
    return NutProtocolParser.parse_var(line)


@dataclass
class NutMetrics:
    """Immutable-style snapshot of parsed UPS telemetry returned by ``NutClient``."""

    status: str
    watts: Optional[int]
    nominal_watts: Optional[int]
    load: int
    battery: int
    voltage: Optional[float]
    ups_status: str
    ups_status_raw: str
    ups_model: str
    error_message: str = ""
    battery_charge_low: Optional[int] = None
    battery_runtime: Optional[int] = None
    battery_runtime_low: Optional[int] = None


class NutClient:
    """Low-level TCP socket client implementing the Network UPS Tools (NUT) text protocol.

    All required variables are queried over a single TCP session followed by a
    clean ``LOGOUT`` command to keep network overhead minimal.
    """

    def __init__(
        self,
        host: str,
        port: int,
        ups_name: str,
        user: str = "",
        password: str = "",
        timeout: float = 3.0,
    ):
        self.host = host
        self.port = port
        # Strip CR/LF to prevent protocol command injection over the raw TCP stream.
        self.ups_name = self._sanitize(ups_name)
        self.user = self._sanitize(user)
        self.password = self._sanitize(password)
        self.timeout = timeout

    @staticmethod
    def _sanitize(value: Optional[str]) -> str:
        """Remove carriage returns and newlines from NUT protocol parameters."""
        return (value or "").replace("\r", "").replace("\n", "")

    def fetch_metrics(self) -> NutMetrics:
        """Connect to the NUT daemon, query telemetry variables, and return parsed ``NutMetrics``."""
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
            sock_file = sock.makefile("r", encoding="utf-8", errors="replace")
            try:
                self._authenticate(sock, sock_file)
                raw = self._collect_raw_variables(sock, sock_file)
                self._logout(sock)
                return self._build_metrics(raw)
            finally:
                sock_file.close()

    def _authenticate(self, sock: socket.socket, sock_file: TextIO) -> None:
        """Send optional ``USERNAME`` and ``PASSWORD`` commands when credentials are configured."""
        if not (self.user and self.password):
            return

        for command in (f"USERNAME {self.user}\n", f"PASSWORD {self.password}\n"):
            sock.sendall(command.encode("utf-8"))
            response = sock_file.readline()
            err_code = NutProtocolParser.parse_error(response)
            if err_code:
                raise NutProtocolError(
                    NutProtocolParser.format_error(err_code, self.ups_name),
                    error_code=err_code,
                )

    def _query_var(self, sock: socket.socket, sock_file: TextIO, var_name: str) -> Optional[str]:
        """Request a single NUT variable and return its string value, or None if unsupported."""
        cmd = f"GET VAR {self.ups_name} {var_name}\n"
        sock.sendall(cmd.encode("utf-8"))
        response = sock_file.readline()
        if not response:
            raise NutProtocolError("Connection closed unexpectedly by NUT server")

        err_code = NutProtocolParser.parse_error(response)
        if err_code in NutProtocolParser.FATAL_ERRORS:
            raise NutProtocolError(
                NutProtocolParser.format_error(err_code, self.ups_name),
                error_code=err_code,
            )
        return NutProtocolParser.parse_var(response)

    def _query_first(
        self,
        sock: socket.socket,
        sock_file: TextIO,
        var_names: Sequence[str],
    ) -> Optional[str]:
        """Query candidate NUT variable names in order and return the first supported value."""
        for var_name in var_names:
            value = self._query_var(sock, sock_file, var_name)
            if value is not None:
                return value
        return None

    def _collect_raw_variables(
        self,
        sock: socket.socket,
        sock_file: TextIO,
    ) -> Dict[str, Optional[str]]:
        """Query all telemetry variables needed by the dashboard over the active socket."""
        return {
            "ups.status": self._query_var(sock, sock_file, "ups.status"),
            "model": self._query_first(sock, sock_file, ("device.model", "ups.model")),
            "mfr": self._query_first(sock, sock_file, ("device.mfr", "ups.mfr")),
            "ups.load": self._query_var(sock, sock_file, "ups.load"),
            "battery.charge": self._query_var(sock, sock_file, "battery.charge"),
            "battery.charge.low": self._query_var(sock, sock_file, "battery.charge.low"),
            "battery.runtime": self._query_var(sock, sock_file, "battery.runtime"),
            "battery.runtime.low": self._query_var(sock, sock_file, "battery.runtime.low"),
            "realpower": self._query_first(sock, sock_file, ("ups.realpower", "output.realpower")),
            "realpower.nominal": self._query_first(
                sock, sock_file, ("ups.realpower.nominal", "output.realpower.nominal")
            ),
            "voltage": self._query_first(sock, sock_file, ("input.voltage", "output.voltage")),
        }

    @staticmethod
    def _logout(sock: socket.socket) -> None:
        """Politely close the NUT protocol session."""
        try:
            sock.sendall(b"LOGOUT\n")
        except OSError:
            pass

    @staticmethod
    def _build_metrics(raw: Dict[str, Optional[str]]) -> NutMetrics:
        """Convert raw NUT string values into a strongly typed ``NutMetrics`` snapshot."""
        load_num = NutProtocolParser.clean_numeric(raw["ups.load"])
        load_val = float(load_num) if load_num is not None else 0.0

        batt_num = NutProtocolParser.clean_numeric(raw["battery.charge"])
        battery_val = float(batt_num) if batt_num is not None else 100.0

        batt_low_num = NutProtocolParser.clean_numeric(raw["battery.charge.low"])
        battery_charge_low = round(batt_low_num) if batt_low_num is not None else None

        batt_rt_num = NutProtocolParser.clean_numeric(raw["battery.runtime"])
        battery_runtime = round(batt_rt_num) if batt_rt_num is not None else None

        batt_rt_low_num = NutProtocolParser.clean_numeric(raw["battery.runtime.low"])
        battery_runtime_low = round(batt_rt_low_num) if batt_rt_low_num is not None else None

        voltage_num = NutProtocolParser.clean_numeric(raw["voltage"])
        voltage_val = round(voltage_num, 1) if voltage_num is not None else None

        watts_num = NutProtocolParser.clean_numeric(raw["realpower"])
        watts_val = round(watts_num) if watts_num is not None else None

        nominal_num = NutProtocolParser.clean_numeric(raw["realpower.nominal"])
        nominal_watts = round(nominal_num) if nominal_num is not None else None

        # Derive active wattage from load % and nominal power when the UPS does not report realpower directly.
        if watts_val is None and nominal_watts is not None:
            watts_val = round((load_val * nominal_watts) / 100.0)

        status_raw = raw["ups.status"] or ""
        model_full = f"{raw['mfr'] or ''} {raw['model'] or ''}".strip()

        return NutMetrics(
            status="online",
            watts=watts_val,
            nominal_watts=nominal_watts,
            load=round(load_val),
            battery=round(battery_val),
            voltage=voltage_val,
            ups_status=NutProtocolParser.format_status(status_raw),
            ups_status_raw=status_raw,
            ups_model=model_full,
            error_message="",
            battery_charge_low=battery_charge_low,
            battery_runtime=battery_runtime,
            battery_runtime_low=battery_runtime_low,
        )
