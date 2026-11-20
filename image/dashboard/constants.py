"""Global constants, filesystem path resolution, and application version loading."""

import os

# ---------------------------------------------------------------------------
# Server & Network Defaults
# ---------------------------------------------------------------------------
DEFAULT_PORT = 8080
DEFAULT_POLL_INTERVAL = 2.0
DEFAULT_NUT_HOST = "127.0.0.1"
DEFAULT_NUT_PORT = 3493
DEFAULT_UPS_NAME = "ups"

# ---------------------------------------------------------------------------
# Authentication & Cryptography Defaults
# ---------------------------------------------------------------------------
COOKIE_NAME = "ups_dashboard_session"
SESSION_MAX_AGE_SECONDS = 2_592_000  # 30 days
PBKDF2_ITERATIONS = 100_000
KEY_SIZE_BYTES = 32
SALT_SIZE_BYTES = 16
NONCE_SIZE_BYTES = 16

# ---------------------------------------------------------------------------
# Directory & File Paths
# ---------------------------------------------------------------------------
# IMAGE_DIR points to the application root (where app.py, VERSION, and static/ reside).
IMAGE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE_DIR = IMAGE_DIR
VERSION_FILE = os.path.join(IMAGE_DIR, "VERSION")
STATIC_DIR = os.path.join(IMAGE_DIR, "static")
LOCALES_DIR = os.path.join(STATIC_DIR, "locales")


def resolve_data_dir(base_dir: str = BASE_DIR) -> str:
    """Resolve the persistent data directory.

    Priority order:
    1. Explicit ``DATA_DIR`` environment variable.
    2. ``<base_dir>/data`` when running inside the container image.
    3. ``<parent_of_base_dir>/data`` when running directly from a repository checkout.
    """
    env_data_dir = os.getenv("DATA_DIR")
    if env_data_dir:
        return env_data_dir

    local_data = os.path.join(base_dir, "data")
    parent_data = os.path.join(os.path.dirname(base_dir), "data")
    if not os.path.isdir(local_data) and os.path.isdir(parent_data):
        return parent_data
    return local_data


DATA_DIR = resolve_data_dir()
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
KEY_FILE = os.path.join(DATA_DIR, ".secret_key")


def get_app_version(version_file: str = VERSION_FILE) -> str:
    """Read the canonical SemVer string from the ``VERSION`` file.

    Falls back to ``"dev"`` if the file cannot be read or is empty.
    """
    try:
        with open(version_file, "r", encoding="utf-8") as vf:
            version = vf.read().strip()
            if version:
                return version
    except OSError:
        pass
    return "dev"


APP_VERSION = get_app_version()
