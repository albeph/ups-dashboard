"""Security primitives: master key storage, password hashing, authenticated encryption, and sessions."""

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
    NONCE_SIZE_BYTES,
    PBKDF2_ITERATIONS,
    SALT_SIZE_BYTES,
    SESSION_MAX_AGE_SECONDS,
)

logger = logging.getLogger("ups-dashboard.security")


class KeyManager:
    """Manages the symmetric master encryption key on disk with ``0600`` permissions."""

    @staticmethod
    def get_or_create_key(key_file: str = KEY_FILE) -> bytes:
        """Load the existing 32-byte master key or generate and persist a new one."""
        if os.path.isfile(key_file):
            try:
                with open(key_file, "rb") as f:
                    key = f.read()
                if len(key) == KEY_SIZE_BYTES:
                    return key
            except OSError as exc:
                logger.warning("Failed to read secret key from %s: %s", key_file, exc)

        key = secrets.token_bytes(KEY_SIZE_BYTES)
        KeyManager._persist_key(key_file, key)
        return key

    @staticmethod
    def _persist_key(key_file: str, key: bytes) -> None:
        """Write the master key to disk enforcing restrictive ``0600`` permissions."""
        try:
            os.makedirs(os.path.dirname(os.path.abspath(key_file)), exist_ok=True)
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
            fd = os.open(key_file, flags, 0o600)
            with open(fd, "wb") as f:
                f.write(key)
            try:
                os.chmod(key_file, 0o600)
            except OSError:
                pass
            logger.info("Generated and saved new master secret key to %s (chmod 0600).", key_file)
        except OSError as exc:
            logger.error("Failed to persist application secret key: %s", exc)


class PasswordHasher:
    """One-way password hashing and constant-time verification using PBKDF2-HMAC-SHA256."""

    SCHEME = "pbkdf2"
    ALGORITHM = "sha256"

    @classmethod
    def hash(cls, plain: str, iterations: int = PBKDF2_ITERATIONS) -> str:
        """Derive a salted PBKDF2-HMAC-SHA256 hash string from a plaintext password."""
        if not plain:
            return ""
        salt = secrets.token_bytes(SALT_SIZE_BYTES)
        derived_key = hashlib.pbkdf2_hmac(
            cls.ALGORITHM,
            plain.encode("utf-8"),
            salt,
            iterations,
        )
        return f"{cls.SCHEME}:{cls.ALGORITHM}:{iterations}${salt.hex()}${derived_key.hex()}"

    @classmethod
    def verify(cls, plain: str, hashed: str) -> bool:
        """Verify a candidate plaintext password against a stored PBKDF2 hash in constant time."""
        if not hashed or not plain:
            return False
        try:
            parts = hashed.split("$")
            if len(parts) != 3:
                return False

            method_part, salt_hex, hash_hex = parts
            method, algorithm, iterations_str = method_part.split(":")
            if method != cls.SCHEME or algorithm != cls.ALGORITHM:
                return False

            iterations = int(iterations_str)
            salt = bytes.fromhex(salt_hex)
            expected_dk = bytes.fromhex(hash_hex)
            actual_dk = hashlib.pbkdf2_hmac(
                cls.ALGORITHM,
                plain.encode("utf-8"),
                salt,
                iterations,
            )
            return secrets.compare_digest(actual_dk, expected_dk)
        except (ValueError, TypeError):
            return False

    @classmethod
    def is_hashed(cls, value: str) -> bool:
        """Return True if ``value`` already uses this hasher's serialized format."""
        return bool(value) and value.startswith(f"{cls.SCHEME}:{cls.ALGORITHM}:")


class SecretCipher:
    """Reversible authenticated symmetric cipher (HMAC-SHA256 CTR + Encrypt-then-MAC).

    Implemented exclusively with Python's standard library so the application
    retains zero external dependencies while still providing confidentiality
    and integrity protection for stored NUT credentials.
    """

    PREFIX = "enc"
    VERSION = "v1"

    def __init__(self, key: bytes):
        self._key = key

    def encrypt(self, plain: str) -> str:
        """Encrypt a plaintext string and return a versioned authenticated token."""
        if not plain:
            return ""
        data = plain.encode("utf-8")
        nonce = secrets.token_bytes(NONCE_SIZE_BYTES)
        keystream = self._generate_keystream(nonce, len(data))
        ciphertext = bytes(b ^ k for b, k in zip(data, keystream))
        tag = self._compute_mac(nonce, ciphertext)
        return f"{self.PREFIX}:{self.VERSION}:{nonce.hex()}:{ciphertext.hex()}:{tag.hex()}"

    def decrypt(self, token: str) -> str:
        """Verify integrity and decrypt a previously encrypted token, or return ``""`` on failure."""
        if not token:
            return ""
        try:
            parts = token.split(":")
            if len(parts) != 5 or parts[0] != self.PREFIX or parts[1] != self.VERSION:
                return ""

            nonce = bytes.fromhex(parts[2])
            ciphertext = bytes.fromhex(parts[3])
            expected_tag = bytes.fromhex(parts[4])

            computed_tag = self._compute_mac(nonce, ciphertext)
            if not secrets.compare_digest(computed_tag, expected_tag):
                logger.warning("Secret decryption failed: authentication tag mismatch.")
                return ""

            keystream = self._generate_keystream(nonce, len(ciphertext))
            plaintext = bytes(b ^ k for b, k in zip(ciphertext, keystream))
            return plaintext.decode("utf-8", errors="replace")
        except (ValueError, TypeError) as exc:
            logger.warning("Error during secret decryption: %s", exc)
            return ""

    def _generate_keystream(self, nonce: bytes, length: int) -> bytes:
        """Generate a deterministic HMAC-SHA256 counter-mode keystream of ``length`` bytes."""
        stream = bytearray()
        counter = 0
        while len(stream) < length:
            block = hmac.new(
                self._key,
                b"keystream:" + nonce + counter.to_bytes(4, "big"),
                hashlib.sha256,
            ).digest()
            stream.extend(block)
            counter += 1
        return bytes(stream[:length])

    def _compute_mac(self, nonce: bytes, ciphertext: bytes) -> bytes:
        """Compute the Encrypt-then-MAC authentication tag over nonce and ciphertext."""
        return hmac.new(
            self._key,
            b"auth:" + nonce + ciphertext,
            hashlib.sha256,
        ).digest()


# Backward-compatible module-level convenience functions delegating to OOP primitives.
def hash_password(plain: str) -> str:
    """Hash a plaintext password using PBKDF2-HMAC-SHA256."""
    return PasswordHasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a stored PBKDF2-HMAC-SHA256 hash."""
    return PasswordHasher.verify(plain, hashed)


def encrypt_secret(plain: str, key: bytes) -> str:
    """Encrypt a reversible secret using the provided 32-byte master key."""
    return SecretCipher(key).encrypt(plain)


def decrypt_secret(enc_str: str, key: bytes) -> str:
    """Decrypt and authenticate a reversible secret using the provided 32-byte master key."""
    return SecretCipher(key).decrypt(enc_str)


class SessionManager:
    """Thread-safe in-memory session registry for authenticated web clients."""

    def __init__(self, cookie_name: str = COOKIE_NAME):
        self.cookie_name = cookie_name
        self._lock = threading.Lock()
        self._active_sessions: Set[str] = set()

    def create_session(self) -> str:
        """Generate a cryptographically secure session token and register it."""
        token = secrets.token_hex(24)
        with self._lock:
            self._active_sessions.add(token)
        return token

    def is_valid(self, token: Optional[str]) -> bool:
        """Return True if the provided session token is currently active."""
        if not token:
            return False
        with self._lock:
            return token in self._active_sessions

    def invalidate(self, token: Optional[str]) -> None:
        """Revoke a session token if present."""
        if not token:
            return
        with self._lock:
            self._active_sessions.discard(token)

    def extract_token_from_cookie(self, cookie_header: Optional[str]) -> Optional[str]:
        """Parse and return the session token from an HTTP ``Cookie`` header."""
        if not cookie_header:
            return None
        try:
            cookie = http.cookies.SimpleCookie(cookie_header)
            if self.cookie_name in cookie:
                return cookie[self.cookie_name].value
        except http.cookies.CookieError:
            pass
        return None

    def extract_token_from_auth(self, auth_header: Optional[str]) -> Optional[str]:
        """Extract a Bearer token from an HTTP ``Authorization`` header."""
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:].strip()
        return None

    def build_cookie_header(self, token: str, max_age: int = SESSION_MAX_AGE_SECONDS) -> str:
        """Build the ``Set-Cookie`` header value used after a successful login."""
        return f"{self.cookie_name}={token}; Path=/; Max-Age={max_age}; HttpOnly; SameSite=Lax"

    def build_clear_cookie_header(self) -> str:
        """Build the ``Set-Cookie`` header value used to expire the session cookie on logout."""
        return f"{self.cookie_name}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax"
