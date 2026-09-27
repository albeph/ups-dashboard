"""Security, cryptography, and session management."""

import hashlib
import hmac
import http.cookies
import logging
import os
import secrets
import threading
from typing import Optional, Set

from .constants import (
    COOKIE_NAME,
    KEY_FILE,
    KEY_SIZE_BYTES,
    PBKDF2_ITERATIONS,
    SALT_SIZE_BYTES,
    SESSION_MAX_AGE_SECONDS,
)

logger = logging.getLogger("ups-dashboard.security")


class KeyManager:
    """Manages application symmetric encryption key stored with 0600 permissions."""

    @staticmethod
    def get_or_create_key(key_file: str = KEY_FILE) -> bytes:
        """Retrieve existing 32-byte symmetric master key or generate and persist one with 0600 permissions."""
        if os.path.isfile(key_file):
            try:
                with open(key_file, "rb") as f:
                    key = f.read()
                if len(key) == KEY_SIZE_BYTES:
                    return key
            except Exception as e:
                logger.warning(f"Failed to read secret key from {key_file}: {e}")

        key = secrets.token_bytes(KEY_SIZE_BYTES)
        try:
            os.makedirs(os.path.dirname(os.path.abspath(key_file)), exist_ok=True)
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
            mode = 0o600
            fd = os.open(key_file, flags, mode)
            with open(fd, "wb") as f:
                f.write(key)
            try:
                os.chmod(key_file, 0o600)
            except Exception:
                pass
            logger.info(f"Generated and saved new application secret key to {key_file} (chmod 0600).")
        except Exception as e:
            logger.error(f"Failed to persist application secret key: {e}")
        return key


def hash_password(plain: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with a unique random 16-byte salt."""
    if not plain:
        return ""
    salt = secrets.token_bytes(SALT_SIZE_BYTES)
    iterations = PBKDF2_ITERATIONS
    dk = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, iterations)
    return f"pbkdf2:sha256:{iterations}${salt.hex()}${dk.hex()}"


def verify_password(plain: str, hashed: str) -> bool:
    """Verify plain password against a stored PBKDF2 hash using constant-time comparison."""
    if not hashed or not plain:
        return False
    try:
        parts = hashed.split("$")
        if len(parts) != 3:
            return False
        method_part, salt_hex, hash_hex = parts
        method, alg, iters_str = method_part.split(":")
        if method != "pbkdf2" or alg != "sha256":
            return False
        iterations = int(iters_str)
        salt = bytes.fromhex(salt_hex)
        expected_dk = bytes.fromhex(hash_hex)
        actual_dk = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, iterations)
        return secrets.compare_digest(actual_dk, expected_dk)
    except Exception:
        return False


def encrypt_secret(plain: str, key: bytes) -> str:
    """Encrypt reversible secret using HMAC-SHA256 authenticated CTR stream cipher."""
    if not plain:
        return ""
    data = plain.encode("utf-8")
    nonce = secrets.token_bytes(16)
    keystream = bytearray()
    counter = 0
    while len(keystream) < len(data):
        block = hmac.new(key, b"keystream:" + nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
        keystream.extend(block)
        counter += 1
    ciphertext = bytes(b ^ k for b, k in zip(data, keystream[:len(data)]))
    tag = hmac.new(key, b"auth:" + nonce + ciphertext, hashlib.sha256).digest()
    return f"enc:v1:{nonce.hex()}:{ciphertext.hex()}:{tag.hex()}"


def decrypt_secret(enc_str: str, key: bytes) -> str:
    """Decrypt reversible secret with HMAC-SHA256 verification."""
    if not enc_str:
        return ""
    try:
        parts = enc_str.split(":")
        if len(parts) != 5 or parts[0] != "enc" or parts[1] != "v1":
            return ""
        nonce = bytes.fromhex(parts[2])
        ciphertext = bytes.fromhex(parts[3])
        expected_tag = bytes.fromhex(parts[4])
        tag = hmac.new(key, b"auth:" + nonce + ciphertext, hashlib.sha256).digest()
        if not secrets.compare_digest(tag, expected_tag):
            logger.warning("Decryption failed: auth tag mismatch")
            return ""
        keystream = bytearray()
        counter = 0
        while len(keystream) < len(ciphertext):
            block = hmac.new(key, b"keystream:" + nonce + counter.to_bytes(4, "big"), hashlib.sha256).digest()
            keystream.extend(block)
            counter += 1
        plain = bytes(b ^ k for b, k in zip(ciphertext, keystream[:len(ciphertext)]))
        return plain.decode("utf-8", errors="replace")
    except Exception as e:
        logger.warning(f"Error during secret decryption: {e}")
        return ""


class SessionManager:
    """Thread-safe in-memory session manager for authenticated web clients."""

    def __init__(self, cookie_name: str = COOKIE_NAME):
        self.cookie_name = cookie_name
        self._lock = threading.Lock()
        self._active_sessions: Set[str] = set()

    def create_session(self) -> str:
        """Generates a secure random session token and registers it."""
        token = secrets.token_hex(24)
        with self._lock:
            self._active_sessions.add(token)
        return token

    def is_valid(self, token: Optional[str]) -> bool:
        """Checks if a session token is active."""
        if not token:
            return False
        with self._lock:
            return token in self._active_sessions

    def invalidate(self, token: Optional[str]) -> None:
        """Removes a session token."""
        if not token:
            return
        with self._lock:
            self._active_sessions.discard(token)

    def extract_token_from_cookie(self, cookie_header: Optional[str]) -> Optional[str]:
        """Extracts session token from Cookie header string."""
        if not cookie_header:
            return None
        try:
            cookie = http.cookies.SimpleCookie(cookie_header)
            if self.cookie_name in cookie:
                return cookie[self.cookie_name].value
        except Exception:
            pass
        return None

    def extract_token_from_auth(self, auth_header: Optional[str]) -> Optional[str]:
        """Extracts bearer token from Authorization header string."""
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:].strip()
        return None

    def build_cookie_header(self, token: str, max_age: int = SESSION_MAX_AGE_SECONDS) -> str:
        """Returns Set-Cookie header value for login."""
        return f"{self.cookie_name}={token}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Lax"

    def build_clear_cookie_header(self) -> str:
        """Returns Set-Cookie header value to clear session."""
        return f"{self.cookie_name}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
