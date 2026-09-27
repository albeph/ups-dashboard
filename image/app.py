#!/usr/bin/env python3
"""
UPS Web Dashboard - Lightweight NUT Web Monitor
================================================
A self-contained, zero-dependency web interface for Network UPS Tools (NUT).
Runs efficiently on any Docker host (from low-power SBCs to full servers).
"""

import logging
import os
import sys

# Ensure current directory is in sys.path for direct script execution
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Re-export key components for backward compatibility
from dashboard import (  # noqa: E402
    APP_VERSION,
    ActivityTracker,
    ConfigManager,
    DashboardHandler,
    KeyManager,
    NUTDataCache,
    NutClient,
    NutMetrics,
    NutPoller,
    Response,
    Router,
    SessionManager,
    build_app,
    decrypt_secret,
    encrypt_secret,
    format_ups_status,
    hash_password,
    parse_nut_var,
    run_server,
    verify_password,
)

if __name__ == "__main__":
    run_server()
