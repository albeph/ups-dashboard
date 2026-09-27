"""Global constants, paths, and version resolution for UPS Dashboard."""

import os

# Server & Network Defaults
DEFAULT_PORT = 8080
DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_NUT_HOST = "127.0.0.1"
DEFAULT_NUT_PORT = 3493
DEFAULT_UPS_NAME = "ups"

# Authentication & Session
COOKIE_NAME = "ups_dashboard_session"
SESSION_MAX_AGE_SECONDS = 2592000  # 30 days
PBKDF2_ITERATIONS = 100_000
KEY_SIZE_BYTES = 32
SALT_SIZE_BYTES = 16

# Directory & File Paths
# IMAGE_DIR is the root of the image directory (where app.py, VERSION, and static/ reside)
IMAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = IMAGE_DIR
VERSION_FILE = os.path.join(IMAGE_DIR, "VERSION")
STATIC_DIR = os.path.join(IMAGE_DIR, "static")
LOCALES_DIR = os.path.join(STATIC_DIR, "locales")

_base_data = os.path.join(BASE_DIR, "data")
_parent_data = os.path.join(os.path.dirname(BASE_DIR), "data")
_default_data = (
    _parent_data
    if (not os.path.isdir(_base_data) and os.path.isdir(_parent_data))
    else _base_data
)
DATA_DIR = os.getenv("DATA_DIR") or _default_data
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
KEY_FILE = os.path.join(DATA_DIR, ".secret_key")


def get_app_version() -> str:
    """Reads the application version string from VERSION file."""
    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as vf:
            ver = vf.read().strip()
            if ver:
                return ver
    except Exception:
        pass
    return "1.1.0"


APP_VERSION = get_app_version()
