import os
from typing import Protocol

from cryptography.fernet import Fernet


class SecretCipher(Protocol):
    def encrypt(self, value: str) -> str:
        ...

    def decrypt(self, value: str) -> str:
        ...


class PlaintextCipher:
    """Dev-only cipher; replace with a proper KMS-backed implementation."""

    def encrypt(self, value: str) -> str:
        return value

    def decrypt(self, value: str) -> str:
        return value


class FernetCipher:
    """Symmetric encryption using a pre-shared Fernet key."""

    def __init__(self, key: str) -> None:
        self._fernet = Fernet(key.encode("utf-8"))

    def encrypt(self, value: str) -> str:
        token = self._fernet.encrypt(value.encode("utf-8"))
        return token.decode("utf-8")

    def decrypt(self, value: str) -> str:
        token = self._fernet.decrypt(value.encode("utf-8"))
        return token.decode("utf-8")


def get_credentials_cipher() -> SecretCipher:
    key = os.environ.get("BACKEND_CREDENTIALS_KEY")
    if not key:
        raise RuntimeError("BACKEND_CREDENTIALS_KEY is required for credential encryption")
    return FernetCipher(key)
