"""NUT (Network UPS Tools) protocol client and telemetry parsing."""

import logging
import re
import socket
from dataclasses import dataclass
from typing import Dict, Optional

logger = logging.getLogger("ups-dashboard.nut")

# Ordered list preserving canonical status priority (matches original app.py)
_STATUS_PRIORITY = [
    ("OL", "Rete elettrica"),
    ("OB", "Su batteria (Blackout)"),
    ("LB", "Batteria critica (LB)"),
    ("CHRG", "In carica"),
    ("DISCHRG", "In scarica"),
    ("BYPASS", "Bypass"),
    ("CAL", "Calibrazione"),
    ("OVER", "Sovraccarico"),
    ("OFF", "Spento"),
    ("RB", "Sostituire batteria"),
]


def format_ups_status(raw_status: str) -> str:
    """Format raw NUT ups.status flags (e.g. OL, OB, CHRG) into human-readable Italian labels."""
    if not raw_status:
        return "Rete elettrica"
    flags = set(raw_status.strip().upper().split())
    labels = [label for flag, label in _STATUS_PRIORITY if flag in flags]
    return " • ".join(labels) if labels else raw_status


_VAR_PATTERN = re.compile(r'^VAR\s+[^\s]+\s+[^\s]+\s+"?([^"\r\n]*)"?')
_VAR_NAME_PATTERN = re.compile(r'^VAR\s+[^\s]+\s+([^\s]+)\s+"?([^"\r\n]*)"?')


def parse_nut_var(line: str) -> Optional[str]:
    """
    Parses a NUT protocol response line:
    VAR <upsname> <varname> "<value>"
    """
    match = _VAR_PATTERN.match(line.strip())
    if match:
        return match.group(1)
    return None


def _clean_numeric(val: Optional[str]) -> Optional[float]:
    if not val:
        return None
    cleaned = "".join(c for c in val if c.isdigit() or c == ".")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


@dataclass
class NutMetrics:
    """Container for parsed UPS telemetry data."""
    status: str
    watts: Optional[int]
    nominal_watts: Optional[int]
    load: int
    battery: int
    voltage: Optional[float]
    ups_status: str
    ups_status_raw: str
    ups_model: str
    raw_vars: Dict[str, str]
    error_message: str = ""


class NutClient:
    """Low-level TCP client communicating with Network UPS Tools daemon."""

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
        self.ups_name = (ups_name or "").replace("\r", "").replace("\n", "")
        self.user = (user or "").replace("\r", "").replace("\n", "")
        self.password = (password or "").replace("\r", "").replace("\n", "")
        self.timeout = timeout

    def fetch_metrics(self) -> NutMetrics:
        """Connects to NUT daemon, queries telemetry variables, and returns parsed NutMetrics."""
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as sock:
            sock_file = sock.makefile("r", encoding="utf-8", errors="replace")
            try:
                # Optional NUT authentication
                if self.user and self.password:
                    sock.sendall(f"USERNAME {self.user}\n".encode("utf-8"))
                    sock_file.readline()
                    sock.sendall(f"PASSWORD {self.password}\n".encode("utf-8"))
                    sock_file.readline()

                def query_var(var_name: str) -> Optional[str]:
                    cmd = f"GET VAR {self.ups_name} {var_name}\n"
                    sock.sendall(cmd.encode("utf-8"))
                    res = sock_file.readline()
                    return parse_nut_var(res)

                def query_all_vars() -> Dict[str, str]:
                    cmd = f"LIST VAR {self.ups_name}\n"
                    sock.sendall(cmd.encode("utf-8"))
                    vars_map: Dict[str, str] = {}
                    while True:
                        line = sock_file.readline()
                        if not line:
                            break
                        line = line.strip()
                        if line.startswith("END LIST VAR"):
                            break
                        if line.startswith("ERR"):
                            return {}
                        match = _VAR_NAME_PATTERN.match(line)
                        if match:
                            vars_map[match.group(1)] = match.group(2)
                    return vars_map

                # Query key metrics
                status_raw = query_var("ups.status")
                model_raw = query_var("device.model") or query_var("ups.model")
                mfr_raw = query_var("device.mfr") or query_var("ups.mfr")
                load_raw = query_var("ups.load")
                battery_raw = query_var("battery.charge")
                realpower_raw = query_var("ups.realpower") or query_var("output.realpower")
                nominal_raw = query_var("ups.realpower.nominal") or query_var("output.realpower.nominal")
                voltage_raw = query_var("input.voltage") or query_var("output.voltage")
                raw_vars = query_all_vars()

                # Send LOGOUT
                try:
                    sock.sendall(b"LOGOUT\n")
                except Exception:
                    pass

                # Parse load percentage
                load_num = _clean_numeric(load_raw)
                load_val = float(load_num) if load_num is not None else 0.0

                # Parse battery percentage
                batt_num = _clean_numeric(battery_raw)
                battery_val = float(batt_num) if batt_num is not None else 100.0

                # Parse voltage (AC mains / input voltage)
                v_num = _clean_numeric(voltage_raw)
                voltage_val = round(v_num, 1) if v_num is not None else None

                # Determine active power in Watts
                watts_num = _clean_numeric(realpower_raw)
                watts_val = round(watts_num) if watts_num is not None else None

                nom_num = _clean_numeric(nominal_raw)
                nom_watts = round(nom_num) if nom_num is not None else None

                # Calculate watts from load and nominal watts if active power not reported
                if watts_val is None and nom_watts is not None:
                    watts_val = round((load_val * nom_watts) / 100.0)

                model_full = f"{mfr_raw or ''} {model_raw or ''}".strip()

                return NutMetrics(
                    status="online",
                    watts=watts_val,
                    nominal_watts=nom_watts,
                    load=round(load_val),
                    battery=round(battery_val),
                    voltage=voltage_val,
                    ups_status=format_ups_status(status_raw or ""),
                    ups_status_raw=status_raw or "",
                    ups_model=model_full,
                    raw_vars=raw_vars,
                    error_message="",
                )
            finally:
                sock_file.close()
