"""AI key vault: encrypted storage for user-supplied model credentials.

BYOK model: users paste base_url + api_key + model. Keys are encrypted at
rest with Fernet (AES-128-CBC + HMAC) derived from TRUSS_AI_VAULT_SECRET.
Keys are never logged, never returned in full by the API (masked only).
"""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from truss_kernel.config import settings


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.ai_vault_secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_secret(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken as e:
        raise ValueError("cannot decrypt key (vault secret changed?)") from e


def mask(plaintext: str) -> str:
    """Show only a safe hint: 'sk-…abcd'."""
    if len(plaintext) <= 8:
        return "…" + plaintext[-2:]
    return plaintext[:3] + "…" + plaintext[-4:]
