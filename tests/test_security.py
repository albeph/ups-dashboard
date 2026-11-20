"""Unit tests for the dashboard.security module."""

import os
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "image")))

from dashboard.security import (
    KeyManager,
    PasswordHasher,
    SecretCipher,
    SessionManager,
    decrypt_secret,
    encrypt_secret,
    hash_password,
    verify_password,
)


class TestSecurity(unittest.TestCase):
    """Tests for master key storage, PBKDF2 hashing, authenticated encryption, and sessions."""

    def test_key_manager_creation_and_reuse(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            key_file = os.path.join(tmpdir, "test.key")
            key1 = KeyManager.get_or_create_key(key_file)
            self.assertEqual(len(key1), 32)
            self.assertTrue(os.path.isfile(key_file))

            file_mode = stat.S_IMODE(os.stat(key_file).st_mode)
            self.assertEqual(file_mode, 0o600)

            key2 = KeyManager.get_or_create_key(key_file)
            self.assertEqual(key1, key2)

    def test_password_hashing_and_verification(self):
        plain = "SuperSecret123!"
        hashed = PasswordHasher.hash(plain)
        self.assertTrue(hashed.startswith("pbkdf2:sha256:100000$"))
        self.assertTrue(PasswordHasher.is_hashed(hashed))

        self.assertTrue(PasswordHasher.verify(plain, hashed))
        self.assertTrue(verify_password(plain, hashed))
        self.assertFalse(verify_password("WrongPassword", hashed))

        # Empty and malformed inputs must safely fail.
        self.assertEqual(hash_password(""), "")
        self.assertFalse(verify_password("", hashed))
        self.assertFalse(verify_password(plain, ""))
        self.assertFalse(verify_password("test", "invalid_format"))

    def test_secret_encryption_and_decryption(self):
        key = os.urandom(32)
        cipher = SecretCipher(key)
        secret = "nut_password_secret_!@#$%"

        enc = cipher.encrypt(secret)
        self.assertTrue(enc.startswith("enc:v1:"))
        self.assertEqual(cipher.decrypt(enc), secret)
        self.assertEqual(decrypt_secret(enc, key), secret)

        # Wrong key must fail authentication tag validation.
        wrong_key = os.urandom(32)
        self.assertEqual(decrypt_secret(enc, wrong_key), "")

        # Tampered ciphertext must fail authentication tag validation.
        parts = enc.split(":")
        tampered = f"{parts[0]}:{parts[1]}:{parts[2]}:00{parts[3][2:]}:{parts[4]}"
        self.assertEqual(cipher.decrypt(tampered), "")

        # Empty inputs must return empty strings.
        self.assertEqual(encrypt_secret("", key), "")
        self.assertEqual(decrypt_secret("", key), "")

    def test_session_manager(self):
        sm = SessionManager()

        token = sm.create_session()
        self.assertTrue(sm.is_valid(token))
        self.assertFalse(sm.is_valid("nonexistent"))
        self.assertFalse(sm.is_valid(None))

        cookie_header = f"foo=bar; {sm.cookie_name}={token}; other=123"
        self.assertEqual(sm.extract_token_from_cookie(cookie_header), token)

        bearer_header = f"Bearer {token}"
        self.assertEqual(sm.extract_token_from_auth(bearer_header), token)

        sm.invalidate(token)
        self.assertFalse(sm.is_valid(token))

        set_cookie = sm.build_cookie_header("abc")
        self.assertIn("ups_dashboard_session=abc", set_cookie)
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("SameSite=Lax", set_cookie)

        clear_cookie = sm.build_clear_cookie_header()
        self.assertIn("Max-Age=0", clear_cookie)


if __name__ == "__main__":
    unittest.main()
