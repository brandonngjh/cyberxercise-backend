from __future__ import annotations

import hashlib
import hmac
import secrets


def generate_participant_token() -> str:
    # Opaque token intended for client storage.
    return secrets.token_urlsafe(32)


def hash_participant_token(*, token: str, pepper: str) -> bytes:
    return hmac.new(pepper.encode("utf-8"), token.encode("utf-8"), hashlib.sha256).digest()
