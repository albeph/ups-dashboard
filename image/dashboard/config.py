"""Configuration management with JSON persistence, password hashing, and encrypted secrets."""

import json
import logging
import os
import tempfile
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
from .security import (
    KeyManager,
    decrypt_secret,
    encrypt_secret,
    hash_password,
    verify_password,
)

logger = logging.getLogger("ups-dashboard.config")


class ConfigManager:
    """Manages application settings with persistent JSON storage, password hashing, and encrypted secrets."""

    def __init__(
        self,
        filepath: str = CONFIG_FILE,
        key_file: str = KEY_FILE,
        secret_key: Optional[bytes] = None,
    ):
        self.filepath = filepath
        self.backup_filepath = f"{filepath}.bak"
        self.lock = threading.Lock()
        self.reload_event = threading.Event()
        self.secret_key = secret_key or KeyManager.get_or_create_key(key_file)
        self.config: Dict[str, Any] = self._load_initial()

    def _load_initial(self) -> Dict[str, Any]:
        # Defaults derived from environment variables
        nut_pwd_env = os.getenv("NUT_PASSWORD", "").strip()
        nut_pwd_file = os.getenv("NUT_PASSWORD_FILE", "").strip()
        if nut_pwd_file and os.path.isfile(nut_pwd_file):
            try:
                with open(nut_pwd_file, "r", encoding="utf-8") as f:
                    nut_pwd_env = f.read().strip()
            except Exception as e:
                logger.warning(f"Failed to read NUT_PASSWORD_FILE ({nut_pwd_file}): {e}")

        dash_pwd_env = os.getenv("DASHBOARD_PASSWORD", "").strip()
        dash_hash = ""
        if dash_pwd_env:
            if dash_pwd_env.startswith("pbkdf2:sha256:"):
                dash_hash = dash_pwd_env
            else:
                dash_hash = hash_password(dash_pwd_env)

        nut_enc = ""
        if nut_pwd_env:
            nut_enc = encrypt_secret(nut_pwd_env, self.secret_key)

        defaults: Dict[str, Any] = {
            "nut_host": os.getenv("NUT_HOST", DEFAULT_NUT_HOST).strip(),
            "nut_port": int(os.getenv("NUT_PORT", str(DEFAULT_NUT_PORT))),
            "ups_name": os.getenv("UPS_NAME", DEFAULT_UPS_NAME).strip(),
            "nut_user": os.getenv("NUT_USER", "").strip(),
            "nut_password_encrypted": nut_enc,
            "dashboard_password_hash": dash_hash,
            "poll_interval": float(os.getenv("POLL_INTERVAL", str(DEFAULT_POLL_INTERVAL))),
            "port": int(os.getenv("PORT", str(DEFAULT_PORT))),
        }

        needs_save = False

        # Override with persisted config.json if present
        saved = self._load_json_file(self.filepath)
        if saved is None and os.path.isfile(self.filepath):
            backup_saved = self._load_json_file(self.backup_filepath)
            if backup_saved is not None:
                saved = backup_saved
                needs_save = True
                logger.warning("Recovered configuration from backup after primary config read failure.")

        if saved is not None:
            # Check for legacy plaintext passwords to migrate
            if "dashboard_password" in saved:
                raw_dash = saved.pop("dashboard_password", None)
                plain_dash = str(raw_dash).strip() if raw_dash is not None else ""
                if plain_dash:
                    defaults["dashboard_password_hash"] = hash_password(plain_dash)
                    logger.info("Migrated plaintext dashboard_password to PBKDF2 hash.")
                else:
                    defaults["dashboard_password_hash"] = ""
                    logger.info("Cleaned empty legacy dashboard_password.")
                needs_save = True

            if "nut_password" in saved:
                raw_nut = saved.pop("nut_password", None)
                plain_nut = str(raw_nut) if raw_nut is not None else ""
                if plain_nut:
                    defaults["nut_password_encrypted"] = encrypt_secret(plain_nut, self.secret_key)
                    logger.info("Migrated plaintext nut_password to encrypted secret.")
                else:
                    defaults["nut_password_encrypted"] = ""
                    logger.info("Cleaned empty legacy nut_password.")
                needs_save = True

            for k, v in saved.items():
                if k in defaults and v is not None:
                    defaults[k] = v
            logger.info(f"Loaded persistent configuration from {self.filepath}")

        # Set strict permissions and save migrated config if needed
        if needs_save:
            try:
                self._save_to_disk(defaults)
                logger.info("Cleaned plaintext credentials and persisted secured config.json.")
            except Exception as e:
                logger.error(f"Failed to persist migrated configuration: {e}")
        elif os.path.isfile(self.filepath):
            try:
                os.chmod(self.filepath, 0o600)
            except Exception:
                pass

        return defaults

    def _save_to_disk(self, config_dict: Dict[str, Any]) -> None:
        self._atomic_write_json(self.filepath, config_dict)
        try:
            self._atomic_write_json(self.backup_filepath, config_dict)
        except Exception as e:
            logger.warning(f"Failed to save config backup {self.backup_filepath}: {e}")

    def _load_json_file(self, filepath: str) -> Optional[Dict[str, Any]]:
        if not os.path.isfile(filepath):
            return None
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            if not isinstance(loaded, dict):
                raise ValueError("Configuration payload must be a JSON object")
            return loaded
        except Exception as e:
            logger.warning(f"Failed to read {filepath}: {e}")
            return None

    def _atomic_write_json(self, filepath: str, config_dict: Dict[str, Any]) -> None:
        directory = os.path.dirname(os.path.abspath(filepath))
        os.makedirs(directory, exist_ok=True)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
        mode = 0o600
        fd, temp_path = tempfile.mkstemp(prefix=".cfg.", suffix=".tmp", dir=directory)
        try:
            os.close(fd)
            write_fd = os.open(temp_path, flags, mode)
            with open(write_fd, "w", encoding="utf-8") as f:
                json.dump(config_dict, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temp_path, filepath)
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
        try:
            os.chmod(filepath, 0o600)
        except Exception:
            pass

    def get(self, key: str, default: Any = None) -> Any:
        with self.lock:
            return self.config.get(key, default)

    def get_nut_password(self) -> str:
        """Returns the decrypted NUT password for socket communication."""
        with self.lock:
            enc = self.config.get("nut_password_encrypted", "")
            if enc:
                return decrypt_secret(enc, self.secret_key)
            return ""

    def is_auth_required(self) -> bool:
        """Returns True if dashboard password protection is active."""
        with self.lock:
            return bool(self.config.get("dashboard_password_hash"))

    def verify_dashboard_password(self, candidate: str) -> bool:
        """Verifies candidate password against stored PBKDF2 hash."""
        with self.lock:
            dash_hash = self.config.get("dashboard_password_hash", "")
        if not dash_hash:
            return True
        return verify_password(candidate, dash_hash)

    def get_all(self) -> Dict[str, Any]:
        with self.lock:
            return dict(self.config)

    def update(self, new_values: Dict[str, Any]) -> None:
        with self.lock:
            for k, v in new_values.items():
                if k in self.config and v is not None:
                    self.config[k] = v

            try:
                self._save_to_disk(self.config)
                logger.info("Configuration updated and saved to disk with 0600 permissions.")
            except Exception as e:
                logger.error(f"Failed to save configuration: {e}")

        self.reload_event.set()
