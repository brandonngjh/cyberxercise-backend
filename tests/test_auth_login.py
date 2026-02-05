from __future__ import annotations

import pytest

from app.core.security import decode_access_token, hash_password
from app.core.settings import Settings
from app.db.models.instructor import Instructor


@pytest.mark.asyncio
async def test_login_success_returns_valid_jwt(client, db_session):
    instructor = Instructor(username="alice", password_hash=hash_password("correct-horse-battery-staple"))
    db_session.add(instructor)
    await db_session.commit()

    res = await client.post(
        "/auth/login",
        json={"username": "alice", "password": "correct-horse-battery-staple"},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["token_type"] == "bearer"
    assert isinstance(body["access_token"], str)
    assert body["access_token"]

    settings = Settings(database_url="postgresql+asyncpg://ignored/ignored", jwt_secret="test-jwt-secret")
    token_data = decode_access_token(settings, body["access_token"])
    assert token_data.instructor_id == str(instructor.id)


@pytest.mark.asyncio
async def test_login_invalid_password_401(client, db_session):
    instructor = Instructor(username="bob", password_hash=hash_password("right-password"))
    db_session.add(instructor)
    await db_session.commit()

    res = await client.post(
        "/auth/login",
        json={"username": "bob", "password": "wrong-password"},
    )

    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_login_unknown_user_401(client):
    res = await client.post(
        "/auth/login",
        json={"username": "nobody", "password": "does-not-matter"},
    )

    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid credentials"


@pytest.mark.asyncio
async def test_login_validation_error_missing_password_422(client):
    res = await client.post(
        "/auth/login",
        json={"username": "alice"},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_login_validation_error_password_too_long_422(client):
    res = await client.post(
        "/auth/login",
        json={"username": "alice", "password": "x" * 73},
    )
    assert res.status_code == 422
