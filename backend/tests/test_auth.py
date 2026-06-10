"""Unit tests for auth service — password hashing, JWT, refresh rotation."""

import time

import pytest
from argon2.exceptions import VerificationError

from app.services.auth_service import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
    _hash_token,
)


class TestPasswordHashing:
    """AC-15: Password stored as argon2id hash."""

    def test_hash_produces_argon2id(self):
        pw = "TestPass123"
        hashed = hash_password(pw)
        assert hashed.startswith("$argon2id$")
        assert "$m=65536,t=3,p=2" in hashed

    def test_verify_correct_password(self):
        pw = "CorrectHorse1"
        hashed = hash_password(pw)
        assert verify_password(pw, hashed) is True

    def test_verify_wrong_password(self):
        pw = "CorrectHorse1"
        hashed = hash_password(pw)
        assert verify_password("WrongPassword1", hashed) is False

    def test_different_passwords_different_hashes(self):
        h1 = hash_password("PassOne1")
        h2 = hash_password("PassTwo2")
        assert h1 != h2

    def test_same_password_different_salts(self):
        h1 = hash_password("SamePass1")
        h2 = hash_password("SamePass1")
        assert h1 != h2  # Different salts


# ── Mock objects for JWT tests ──

class _MockRole:
    name = "user"


class _MockUser:
    id = 42
    name = "testuser"
    role = _MockRole()


class TestJWT:
    """AC-3, AC-6, AC-11: JWT creation and verification."""

    @pytest.fixture
    def user(self):
        return _MockUser()

    def test_access_token_contains_claims(self, user):
        token = create_access_token(user)
        payload = decode_token(token)
        assert payload["sub"] == "42"
        assert payload["name"] == "testuser"
        assert payload["role"] == "user"
        assert payload["type"] == "access"
        assert "jti" in payload
        assert "iat" in payload
        assert "exp" in payload

    def test_refresh_token_has_correct_type(self, user):
        token = create_refresh_token(user)
        payload = decode_token(token)
        assert payload["type"] == "refresh"

    def test_access_token_expires_in_15min(self, user):
        token = create_access_token(user)
        payload = decode_token(token)
        lifetime = payload["exp"] - payload["iat"]
        assert lifetime == 900  # 15 minutes

    def test_refresh_token_expires_in_7days(self, user):
        token = create_refresh_token(user)
        payload = decode_token(token)
        lifetime = payload["exp"] - payload["iat"]
        assert lifetime == 604800  # 7 days

    def test_invalid_token_raises_error(self):
        with pytest.raises(Exception):
            decode_token("not.a.valid.token")

    def test_tokens_with_same_user_are_unique(self, user):
        """JTI ensures uniqueness even within the same second."""
        t1 = create_access_token(user)
        t2 = create_access_token(user)
        assert t1 != t2
        # Hashes should be different
        assert _hash_token(t1) != _hash_token(t2)


class TestTokenHashing:
    """Refresh token hash for DB storage."""

    def test_hash_is_64_chars(self):
        h = _hash_token("some-refresh-token")
        assert len(h) == 64  # SHA-256 hex

    def test_same_input_same_hash(self):
        assert _hash_token("abc") == _hash_token("abc")

    def test_different_input_different_hash(self):
        assert _hash_token("abc") != _hash_token("def")
