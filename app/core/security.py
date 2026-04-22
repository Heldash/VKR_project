"""Security helpers for DB-backed RBAC."""

from hashlib import pbkdf2_hmac
from hmac import compare_digest


def hash_password(password: str) -> str:
    """Returns a stable PBKDF2 hash for the MVP bootstrap users."""
    digest = pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        b"netauto-mvp-rbac",
        120_000,
    )
    return digest.hex()


def verify_password(password: str, password_hash: str) -> bool:
    """Verifies a plaintext password against the stored PBKDF2 hash."""
    return compare_digest(hash_password(password), password_hash)
