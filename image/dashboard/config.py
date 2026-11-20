"""Thread-safe configuration manager with JSON persistence and credential protection."""

import json
import logging
import os
import threading
from typing import Any, Dict, Optional

from .constants import (
    CONFIG_FILE,
    DEFAULT_NUT_HOST,
    DEFAULT_NUT_PORT,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_UPS_NAME,
    KEY_FILE,
)
from .security import KeyManager, PasswordHasher, SecretCipher

logger = logging.getLogger("ups-dashboard.config")


class ConfigManager:
    """Manages runtime configuration, environment defaults, JSON persistence, and encrypted secrets.

    - Dashboard access passwords are stored exclusively as irreversible PBKDF2-HMAC-SHA256 hashes.
    - NUT daemon passwords are encrypted at rest with ``SecretCipher`` using a 32-byte key in
      ``.secret_key`` (enforced with ``0600`` filesystem permissions).
    - Legacy plaintext credential keys found in older ``config.json`` files are migrated
      automatically on startup.
    """

    def __init__(
        self,
        filepath: str = CONFIG_FILE,
        key_file: str = KEY_FILE,
        secret_key: Optional[bytes] = None,
    ):
        self.filepath = filepath
        self.lock = threading.Lock()
        self.reload_event = threading.Event()
        self.secret_key = secret_key or KeyManager.get_or_create_key(key_file)
        self._cipher = SecretCipher(self.secret_key)
        self.config: Dict[str, Any] = self._load_initial()

    def _load_initial(self) -> Dict[str, Any]:
        """Build initial configuration from environment defaults and persisted JSON overrides."""
        config = self._load_env_defaults()
        needs_save = False

        if os.path.isfile(self.filepath):
            needs_save = self._merge_persisted_file(config)

        if needs_save:
            try:
                self._save_to_disk(config)
                logger.info("Migrated legacy plaintext credentials and saved secured config.json.")
            except OSError as exc:
                logger.error("Failed to persist migrated configuration: %s", exc)
        elif os.path.isfile(self.filepath):
            self._enforce_file_permissions()

        return config

    def _load_env_defaults(self) -> Dict[str, Any]:
        """Compute baseline settings from environment variables."""
        nut_pwd_plain = self._read_nut_password_from_env()
        dash_pwd_env = os.getenv("DASHBOARD_PASSWORD", "").strip()

        if PasswordHasher.is_hashed(dash_pwd_env):
            dash_hash = dash_pwd_env
        elif dash_pwd_env:
            dash_hash = PasswordHasher.hash(dash_pwd_env)
        else:
            dash_hash = ""

        nut_encrypted = self._cipher.encrypt(nut_pwd_plain) if nut_pwd_plain else ""

        return {
            "nut_host": os.getenv("NUT_HOST", DEFAULT_NUT_HOST).strip(),
            "nut_port": int(os.getenv("NUT_PORT", str(DEFAULT_NUT_PORT))),
            "ups_name": os.getenv("UPS_NAME", DEFAULT_UPS_NAME).strip(),
            "nut_user": os.getenv("NUT_USER", "").strip(),
            "nut_password_encrypted": nut_encrypted,
            "dashboard_password_hash": dash_hash,
            "poll_interval": float(os.getenv("POLL_INTERVAL", str(DEFAULT_POLL_INTERVAL))),
            "port": int(os.getenv("PORT", str(DEFAULT_PORT))),
        }

    @staticmethod
    def _read_nut_password_from_env() -> str:
        """Read NUT password from ``NUT_PASSWORD`` or a Docker secrets file (``NUT_PASSWORD_FILE``)."""
        nut_pwd = os.getenv("NUT_PASSWORD", "").strip()
        nut_pwd_file = os.getenv("NUT_PASSWORD_FILE", "").strip()
        if nut_pwd_file and os.path.isfile(nut_pwd_file):
            try:
                with open(nut_pwd_file, "r", encoding="utf-8") as f:
                    nut_pwd = f.read().strip()
            except OSError as exc:
                logger.warning("Failed to read NUT_PASSWORD_FILE (%s): %s", nut_pwd_file, exc)
        return nut_pwd

    def _merge_persisted_file(self, config: Dict[str, Any]) -> bool:
        """Load overrides from ``config.json`` and migrate legacy plaintext credentials if present.

        Returns True when the file must be re-saved to remove legacy plaintext fields.
        """
        needs_save = False
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                saved = json.load(f)

            if not isinstance(saved, dict):
                return False

            needs_save = self._migrate_legacy_credentials(saved, config)

            for key, value in saved.items():
                if key in config and value is not None:
                    config[key] = value

            logger.info("Loaded persistent configuration from %s", self.filepath)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Failed to read %s: %s", self.filepath, exc)
        return needs_save

    def _migrate_legacy_credentials(self, saved: Dict[str, Any], target: Dict[str, Any]) -> bool:
        """Convert legacy plaintext password fields in ``saved`` to hashed/encrypted equivalents."""
        migrated = False

        if "dashboard_password" in saved:
            raw_dash = saved.pop("dashboard_password", None)
            plain_dash = str(raw_dash).strip() if raw_dash is not None else ""
            if plain_dash:
                target["dashboard_password_hash"] = PasswordHasher.hash(plain_dash)
                logger.info("Migrated plaintext dashboard_password to PBKDF2 hash.")
            else:
                target["dashboard_password_hash"] = ""
                logger.info("Removed empty legacy dashboard_password field.")
            migrated = True

        if "nut_password" in saved:
            raw_nut = saved.pop("nut_password", None)
            plain_nut = str(raw_nut) if raw_nut is not None else ""
            if plain_nut:
                target["nut_password_encrypted"] = self._cipher.encrypt(plain_nut)
                logger.info("Migrated plaintext nut_password to encrypted secret.")
            else:
                target["nut_password_encrypted"] = ""
                logger.info("Removed empty legacy nut_password field.")
            migrated = True

        return migrated

    def _enforce_file_permissions(self) -> None:
        """Ensure ``config.json`` is readable and writable only by the owner (``0600``)."""
        try:
            os.chmod(self.filepath, 0o600)
        except OSError:
            pass

    def _save_to_disk(self, config_dict: Dict[str, Any]) -> None:
        """Write configuration dictionary to disk with restrictive ``0600`` permissions."""
        os.makedirs(os.path.dirname(os.path.abspath(self.filepath)), exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        fd = os.open(self.filepath, flags, 0o600)
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(config_dict, f, indent=2)
        self._enforce_file_permissions()

    def get(self, key: str, default: Any = None) -> Any:
        """Retrieve a single configuration value in a thread-safe manner."""
        with self.lock:
            return self.config.get(key, default)

    def get_all(self) -> Dict[str, Any]:
        """Return a shallow copy of the current configuration dictionary."""
        with self.lock:
            return dict(self.config)

    def get_nut_password(self) -> str:
        """Decrypt and return the configured NUT daemon password (or empty string)."""
        with self.lock:
            encrypted = self.config.get("nut_password_encrypted", "")
        return self._cipher.decrypt(encrypted) if encrypted else ""

    def encrypt_nut_password(self, plain: str) -> str:
        """Encrypt a plaintext NUT password using this manager's master key."""
        return self._cipher.encrypt(plain)

    def is_auth_required(self) -> bool:
        """Return True when dashboard password authentication is enabled."""
        with self.lock:
            return bool(self.config.get("dashboard_password_hash"))

    def verify_dashboard_password(self, candidate: str) -> bool:
        """Verify ``candidate`` against the stored PBKDF2 password hash."""
        with self.lock:
            dash_hash = self.config.get("dashboard_password_hash", "")
        if not dash_hash:
            return True
        return PasswordHasher.verify(candidate, dash_hash)

    def update(self, new_values: Dict[str, Any]) -> None:
        """Apply partial updates, persist to disk, and notify listeners via ``reload_event``."""
        with self.lock:
            for key, value in new_values.items():
                if key in self.config and value is not None:
                    self.config[key] = value

            try:
                self._save_to_disk(self.config)
                logger.info("Configuration updated and persisted with 0600 permissions.")
            except OSError as exc:
                logger.error("Failed to save configuration: %s", exc)

        self.reload_event.set()
