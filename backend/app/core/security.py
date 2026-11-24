"""Password hashing, random tokens and QR token encryption (spec section 3 and 7)."""

import base64
import hashlib
import hmac
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import get_settings

_password_hasher = PasswordHasher()  # argon2-cffi defaults to Argon2id


# ---------- passwords ----------

def hash_password(plain: str) -> str:
    return _password_hasher.hash(plain)


def verify_password(plain: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, plain)
    except (VerificationError, InvalidHashError):
        return False


# Used when the email does not exist, so login takes the same time either way
# and does not reveal whether the account exists (spec section 4).
DUMMY_PASSWORD_HASH = _password_hasher.hash("not-a-real-password")


# ---------- tokens ----------

def new_token() -> str:
    """256-bit cryptographically random token, URL-safe."""
    return secrets.token_urlsafe(32)


def sha256_hex(value: str) -> str:
    """64-character hex digest, the format stored in CHAR(64) columns."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def csrf_token_for(session_token: str) -> str:
    """CSRF token bound to the session (spec section 7).

    Derived from the secret session token, so it needs no extra table column and changes
    whenever the session changes. The session token itself is in an HttpOnly cookie that
    JavaScript (and an attacking site) cannot read, so the CSRF token cannot be guessed,
    and the one-way hash means the CSRF token never reveals the session token.
    """
    return hashlib.sha256(f"csrf:{session_token}".encode("utf-8")).hexdigest()


# ---------- QR token encryption (AES-256-GCM, key outside the database) ----------

def _qr_key() -> bytes:
    key = base64.b64decode(get_settings().qr_encryption_key)
    if len(key) != 32:
        raise RuntimeError("QR_ENCRYPTION_KEY must be a base64-encoded 32-byte key")
    return key


def encrypt_qr_token(token: str) -> str:
    """Return base64(nonce || ciphertext+tag). GCM authenticates, so tampering is detected."""
    nonce = secrets.token_bytes(12)
    ciphertext = AESGCM(_qr_key()).encrypt(nonce, token.encode("utf-8"), None)
    return base64.b64encode(nonce + ciphertext).decode("ascii")


def decrypt_qr_token(stored: str) -> str:
    raw = base64.b64decode(stored)
    nonce, ciphertext = raw[:12], raw[12:]
    return AESGCM(_qr_key()).decrypt(nonce, ciphertext, None).decode("utf-8")


def generate_qr_token() -> tuple[str, str, str]:
    """New QR token for a reservation: (plain token, sha256 digest, ciphertext)."""
    token = new_token()
    return token, sha256_hex(token), encrypt_qr_token(token)
