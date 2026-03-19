import pytest

from mealmetric.services import security


class _FakeBcrypt:
    def __init__(self, *, checkpw_result: bool = True, raise_value_error: bool = False) -> None:
        self.checkpw_result = checkpw_result
        self.raise_value_error = raise_value_error

    def hashpw(self, password: bytes, salt: bytes) -> bytes:
        return b"bcrypt-hash"

    def gensalt(self) -> bytes:
        return b"salt"

    def checkpw(self, password: bytes, hashed_password: bytes) -> bool:
        if self.raise_value_error:
            raise ValueError("invalid hash")
        return self.checkpw_result


def test_hash_and_verify_password_with_pbkdf2_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "bcrypt_module", None)
    hashed = security.hash_password("securepass1")

    assert hashed.startswith("pbkdf2_sha256$")
    assert security.verify_password("securepass1", hashed) is True
    assert security.verify_password("wrongpass", hashed) is False


def test_verify_password_pbkdf2_invalid_payload_returns_false() -> None:
    assert security.verify_password("x", "pbkdf2_sha256$not-an-int$bad$bad") is False
    assert security.verify_password("x", "not_pbkdf2$100$abc$def") is False


def test_hash_password_uses_bcrypt_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "bcrypt_module", _FakeBcrypt())

    hashed = security.hash_password("securepass1")

    assert hashed == "bcrypt-hash"


def test_verify_password_uses_bcrypt_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(security, "bcrypt_module", _FakeBcrypt(checkpw_result=True))
    assert security.verify_password("securepass1", "bcrypt-hash") is True

    monkeypatch.setattr(security, "bcrypt_module", _FakeBcrypt(checkpw_result=False))
    assert security.verify_password("securepass1", "bcrypt-hash") is False


def test_verify_password_bcrypt_value_error_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(security, "bcrypt_module", _FakeBcrypt(raise_value_error=True))
    assert security.verify_password("securepass1", "bcrypt-hash") is False


def test_verify_password_without_bcrypt_and_non_pbkdf2_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(security, "bcrypt_module", None)
    assert security.verify_password("securepass1", "bcrypt-hash") is False
