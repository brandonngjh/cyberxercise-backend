from __future__ import annotations

import time
from dataclasses import dataclass

import bcrypt
from jose import JWTError, jwt

from app.core.settings import Settings


def _check_bcrypt_password_length(password: str) -> None:
    # bcrypt only uses the first 72 bytes of the password.
    # We reject longer passwords to avoid surprising truncation.
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password too long (bcrypt max is 72 bytes)")


def hash_password(password: str) -> str:
    _check_bcrypt_password_length(password)
    password_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password_bytes, salt)
    # bcrypt hashes are ASCII bytes like b"$2b$12$..."; store as str.
    return hashed.decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        _check_bcrypt_password_length(password)
    except ValueError:
        return False

    try:
        password_bytes = password.encode("utf-8")
        hash_bytes = password_hash.encode("utf-8")
        return bcrypt.checkpw(password_bytes, hash_bytes)
    except Exception:
        return False


@dataclass(frozen=True)
class TokenData:
    instructor_id: str


def create_access_token(settings: Settings, *, instructor_id: str) -> str:
    now = int(time.time())
    payload = {
        "sub": instructor_id,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": now,
        "exp": now + int(settings.jwt_access_ttl_seconds),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_access_token(settings: Settings, token: str) -> TokenData:
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
        )
    except JWTError as exc:
        raise ValueError("Invalid token") from exc

    sub = payload.get("sub")
    if not isinstance(sub, str) or not sub:
        raise ValueError("Invalid token")

    return TokenData(instructor_id=sub)
