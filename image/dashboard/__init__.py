"""UPS Web Dashboard backend package."""

from .collector import ActivityTracker, NUTDataCache, NutPoller
from .config import ConfigManager
from .constants import APP_VERSION
from .nut import (
    NutClient,
    NutMetrics,
    NutProtocolError,
    NutProtocolParser,
    format_ups_status,
    parse_nut_error,
    parse_nut_var,
)
from .router import LocaleRegistry, Response, Router, SettingsValidator, StaticFileServer
from .security import (
    KeyManager,
    PasswordHasher,
    SecretCipher,
    SessionManager,
    decrypt_secret,
    encrypt_secret,
    hash_password,
    verify_password,
)
from .server import DashboardApplication, DashboardHandler, DashboardHTTPServer, build_app, run_server

__all__ = [
    "APP_VERSION",
    "ActivityTracker",
    "ConfigManager",
    "DashboardApplication",
    "DashboardHTTPServer",
    "DashboardHandler",
    "KeyManager",
    "LocaleRegistry",
    "NUTDataCache",
    "NutClient",
    "NutMetrics",
    "NutPoller",
    "NutProtocolError",
    "NutProtocolParser",
    "PasswordHasher",
    "Response",
    "Router",
    "SecretCipher",
    "SessionManager",
    "SettingsValidator",
    "StaticFileServer",
    "build_app",
    "decrypt_secret",
    "encrypt_secret",
    "format_ups_status",
    "hash_password",
    "parse_nut_error",
    "parse_nut_var",
    "run_server",
    "verify_password",
]
