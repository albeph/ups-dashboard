#!/usr/bin/env python3
"""UPS Web Dashboard - Application Entrypoint.

A lightweight, zero-dependency web dashboard and PWA for monitoring UPS devices
managed by Network UPS Tools (NUT).
"""

import logging
import os
import sys

# Ensure the image directory is on sys.path when executed directly (e.g. `python3 image/app.py`).
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# Configure structured console logging before importing application modules.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Re-export core symbols for convenience and backward compatibility.
from dashboard import (  # noqa: E402
    APP_VERSION,
    ActivityTracker,
    ConfigManager,
    DashboardApplication,
    DashboardHandler,
    DashboardHTTPServer,
    KeyManager,
    LocaleRegistry,
    NUTDataCache,
    NutClient,
    NutMetrics,
    NutPoller,
    NutProtocolError,
    NutProtocolParser,
    PasswordHasher,
    Response,
    Router,
    SecretCipher,
    SessionManager,
    SettingsValidator,
    StaticFileServer,
    build_app,
    decrypt_secret,
    encrypt_secret,
    format_ups_status,
    hash_password,
    parse_nut_error,
    parse_nut_var,
    run_server,
    verify_password,
)

if __name__ == "__main__":
    run_server()
