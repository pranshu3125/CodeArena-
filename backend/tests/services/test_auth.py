import hashlib

import pytest

from app.api.routes.auth import hash_password, verify_password


class TestPasswordHashing:
    def test_new_format_prefix(self):
        hashed = hash_password("hello")
        assert hashed.startswith("$pbkdf2-sha256$100000$")

    def test_verify_new_format(self):
        pwd = "correct-horse-battery-staple"
        h = hash_password(pwd)
        assert verify_password(pwd, h) is True

    def test_verify_new_format_wrong(self):
        h = hash_password("real-password")
        assert verify_password("wrong-password", h) is False

    def test_verify_legacy_format(self):
        pwd = "legacy-password"
        old_hash = hashlib.sha256(pwd.encode("utf-8")).hexdigest()
        assert verify_password(pwd, old_hash) is True

    def test_verify_legacy_format_wrong(self):
        pwd = "legacy-password"
        old_hash = hashlib.sha256(pwd.encode("utf-8")).hexdigest()
        assert verify_password("wrong-password", old_hash) is False

    def test_different_salts(self):
        h1 = hash_password("same-password")
        h2 = hash_password("same-password")
        assert h1 != h2
