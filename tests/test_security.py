"""Tests for dashboard.security module."""

import os
import stat
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "image")))

from dashboard.security import (
    KeyManager,
    SessionManager,
    decrypt_secret,
    encrypt_secret,
    hash_password,
    verify_password,
)


class TestSecurity(unittest.TestCase):

    def test_key_manager_creation_and_reuse(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            key_file = os.path.join(tmpdir, "test.key")
            key1 = KeyManager.get_or_create_key(key_file)
            self.assertEqual(len(key1), 32)
            self.assertTrue(os.path.isfile(key_file))

            # Check permissions (0600)
            file_mode = stat.S_IMODE(os.stat(key_file).st_mode)
            self.assertEqual(file_mode, 0o600)

            # Check reuse
            key2 = KeyManager.get_or_create_key(key_file)
            self.assertEqual(key1, key2)

    def test_password_hashing_and_verification(self):
        plain = "SuperSecret123!"
        hashed = hash_password(plain)
        self.assertTrue(hashed.startswith("pbkdf2:sha256:100000$"))

        # Verify correct password
        self.assertTrue(verify_password(plain, hashed))

        # Verify incorrect password
        self.assertFalse(verify_password("WrongPassword", hashed))

        # Empty inputs
        self.assertEqual(hash_password(""), "")
        self.assertFalse(verify_password("", hashed))
        self.assertFalse(verify_password(plain, ""))
        self.assertFalse(verify_password("test", "invalid_format"))

    def test_secret_encryption_and_decryption(self):
        key = os.urandom(32)
        secret = "nut_password_secret_!@#$%"

        enc = encrypt_secret(secret, key)
        self.assertTrue(enc.startswith("enc:v1:"))

        decrypted = decrypt_secret(enc, key)
        self.assertEqual(decrypted, secret)

        # Decrypt with wrong key should fail (tag mismatch)
        wrong_key = os.urandom(32)
        self.assertEqual(decrypt_secret(enc, wrong_key), "")

        # Tampered ciphertext should fail
        parts = enc.split(":")
        tampered = f"{parts[0]}:{parts[1]}:{parts[2]}:00{parts[3][2:]}:{parts[4]}"
        self.assertEqual(decrypt_secret(tampered, key), "")

        # Empty inputs
        self.assertEqual(encrypt_secret("", key), "")
        self.assertEqual(decrypt_secret("", key), "")

    def test_session_manager(self):
        sm = SessionManager()

        # Generate session
        token = sm.create_session()
        self.assertTrue(sm.is_valid(token))
        self.assertFalse(sm.is_valid("nonexistent"))
        self.assertFalse(sm.is_valid(None))

        # Cookie extraction
        cookie_header = f"foo=bar; {sm.cookie_name}={token}; other=123"
        extracted = sm.extract_token_from_cookie(cookie_header)
        self.assertEqual(extracted, token)

        # Auth header extraction
        bearer_header = f"Bearer {token}"
        extracted_bearer = sm.extract_token_from_auth(bearer_header)
        self.assertEqual(extracted_bearer, token)

        # Invalidate session
        sm.invalidate(token)
        self.assertFalse(sm.is_valid(token))

        # Cookie header builders
        set_cookie = sm.build_cookie_header("abc")
        self.assertIn("ups_dashboard_session=abc", set_cookie)
        self.assertIn("HttpOnly", set_cookie)
        self.assertIn("SameSite=Lax", set_cookie)

        clear_cookie = sm.build_clear_cookie_header()
        self.assertIn("Max-Age=0", clear_cookie)


if __name__ == "__main__":
    unittest.main()
