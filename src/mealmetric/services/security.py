import base64
import hashlib
import hmac
import importlib
import os
from typing import Final, Protocol, cast


class _BcryptLike(Protocol):
    def hashpw(self, password: bytes, salt: bytes) -> bytes: ...

    def gensalt(self) -> bytes: ...

    def checkpw(self, password: bytes, hashed_password: bytes) -> bool: ...


bcrypt_module: _BcryptLike | None
try:
    bcrypt_module = cast(_BcryptLike, importlib.import_module("bcrypt"))
except ImportError:  # pragma: no cover - exercised when bcrypt is unavailable
    bcrypt_module = None

_PBKDF2_PREFIX: Final[str] = "pbkdf2_sha256"
_PBKDF2_ROUNDS: Final[int] = 100_000
_PBKDF2_BYTES: Final[int] = 32


def _pbkdf2_hash(plain: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, _PBKDF2_ROUNDS)
    return (
        f"{_PBKDF2_PREFIX}${_PBKDF2_ROUNDS}$"
        f"{base64.urlsafe_b64encode(salt).decode('ascii')}$"
        f"{base64.urlsafe_b64encode(digest).decode('ascii')}"
    )


def _pbkdf2_verify(plain: str, hashed: str) -> bool:
    try:
        algo, rounds, salt_b64, digest_b64 = hashed.split("$", maxsplit=3)
        if algo != _PBKDF2_PREFIX:
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
        actual = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, int(rounds))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


def hash_password(plain: str) -> str:
    if bcrypt_module is not None:
        return bcrypt_module.hashpw(plain.encode("utf-8"), bcrypt_module.gensalt()).decode("utf-8")
    return _pbkdf2_hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    if hashed.startswith(_PBKDF2_PREFIX):
        return _pbkdf2_verify(plain, hashed)
    if bcrypt_module is None:
        return False
    try:
        return bool(bcrypt_module.checkpw(plain.encode("utf-8"), hashed.encode("utf-8")))
    except ValueError:
        return False
