from __future__ import annotations

import re
import uuid

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.db.models.exercise_session import ExerciseSession, SessionStatus
from app.db.models.instructor import Instructor


TEAM_ID_RE = re.compile(r"^[A-HJ-NP-Z2-9]{6}$")


async def _login_and_get_headers(client, db_session, *, username: str = "instructor") -> dict[str, str]:
    instructor = Instructor(username=username, password_hash=hash_password("password-1234"))
    db_session.add(instructor)
    await db_session.commit()

    res = await client.post("/auth/login", json={"username": username, "password": "password-1234"})
    assert res.status_code == 200
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_create_session_requires_auth(client):
    res = await client.post("/sessions", json={})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_create_session_201_and_returns_team_id(client, db_session):
    headers = await _login_and_get_headers(client, db_session)

    res = await client.post("/sessions", headers=headers)
    assert res.status_code == 201

    body = res.json()
    assert TEAM_ID_RE.match(body["team_id"])
    assert body["status"] == "lobby"
    assert body["max_participants"] == 10
    assert body["duration_seconds"] is None


@pytest.mark.asyncio
async def test_create_session_validates_max_participants_422(client, db_session):
    headers = await _login_and_get_headers(client, db_session)

    res = await client.post("/sessions", headers=headers, json={"max_participants": 11})
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_join_success_returns_participant_token(client, db_session):
    headers = await _login_and_get_headers(client, db_session)
    create_res = await client.post("/sessions", headers=headers, json={})
    assert create_res.status_code == 201
    created = create_res.json()

    join_res = await client.post(
        "/join",
        json={"team_id": created["team_id"], "display_name": "Alice"},
    )
    assert join_res.status_code == 200
    body = join_res.json()

    assert body["session_id"] == created["session_id"]
    assert isinstance(body["participant_token"], str) and body["participant_token"]
    assert isinstance(body["participant_id"], str) and body["participant_id"]


@pytest.mark.asyncio
async def test_join_unknown_team_id_404(client):
    res = await client.post("/join", json={"team_id": "AAAAAA", "display_name": "Alice"})
    # Team ID format is validated; A is allowed, so this should be a real 404.
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_join_duplicate_display_name_409(client, db_session):
    headers = await _login_and_get_headers(client, db_session)
    create_res = await client.post("/sessions", headers=headers, json={})
    created = create_res.json()

    first = await client.post("/join", json={"team_id": created["team_id"], "display_name": "Same"})
    assert first.status_code == 200

    second = await client.post("/join", json={"team_id": created["team_id"], "display_name": "Same"})
    assert second.status_code == 409
    assert second.json()["detail"] == "Display name already taken"


@pytest.mark.asyncio
async def test_join_full_session_409(client, db_session):
    headers = await _login_and_get_headers(client, db_session)
    create_res = await client.post("/sessions", headers=headers, json={"max_participants": 1})
    created = create_res.json()

    first = await client.post("/join", json={"team_id": created["team_id"], "display_name": "One"})
    assert first.status_code == 200

    second = await client.post("/join", json={"team_id": created["team_id"], "display_name": "Two"})
    assert second.status_code == 409
    assert second.json()["detail"] == "Session is full"


@pytest.mark.asyncio
async def test_join_not_lobby_409(client, db_session):
    headers = await _login_and_get_headers(client, db_session)
    create_res = await client.post("/sessions", headers=headers, json={})
    created = create_res.json()

    # Flip the session to running.
    result = await db_session.execute(
        select(ExerciseSession).where(ExerciseSession.id == created["session_id"])
    )
    session = result.scalar_one()
    session.status = SessionStatus.running
    await db_session.commit()

    res = await client.post("/join", json={"team_id": created["team_id"], "display_name": "Late"})
    assert res.status_code == 409
    assert res.json()["detail"] == "Session is not joinable"


@pytest.mark.asyncio
async def test_get_session_requires_auth(client):
    res = await client.get(f"/sessions/{uuid.uuid4()}")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_get_session_details_200(client, db_session):
    headers = await _login_and_get_headers(client, db_session)
    create_res = await client.post("/sessions", headers=headers)
    assert create_res.status_code == 201
    created = create_res.json()

    res = await client.get(f"/sessions/{created['session_id']}", headers=headers)
    assert res.status_code == 200
    body = res.json()

    assert body["id"] == created["session_id"]
    assert body["team_id"] == created["team_id"]
    assert body["status"] == "lobby"
    assert body["max_participants"] == 10
    assert body["duration_seconds"] is None
    assert body["started_at"] is None
    assert body["ended_at"] is None
    assert body["ended_by"] is None
    assert isinstance(body["created_at"], str) and body["created_at"]


@pytest.mark.asyncio
async def test_get_session_details_not_found_404(client, db_session):
    headers = await _login_and_get_headers(client, db_session)
    res = await client.get(f"/sessions/{uuid.uuid4()}", headers=headers)
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_get_session_details_other_instructor_404(client, db_session):
    headers_a = await _login_and_get_headers(client, db_session, username="a")
    create_res = await client.post("/sessions", headers=headers_a)
    created = create_res.json()

    headers_b = await _login_and_get_headers(client, db_session, username="b")
    res = await client.get(f"/sessions/{created['session_id']}", headers=headers_b)
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_get_participants_requires_auth(client):
    res = await client.get(f"/sessions/{uuid.uuid4()}/participants")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_get_participants_lists_joined_participants(client, db_session):
    headers = await _login_and_get_headers(client, db_session)
    create_res = await client.post("/sessions", headers=headers)
    assert create_res.status_code == 201
    created = create_res.json()

    join_res = await client.post(
        "/join",
        json={"team_id": created["team_id"], "display_name": "Alice"},
    )
    assert join_res.status_code == 200
    joined = join_res.json()

    res = await client.get(f"/sessions/{created['session_id']}/participants", headers=headers)
    assert res.status_code == 200
    body = res.json()

    assert body["session_id"] == created["session_id"]
    assert isinstance(body["participants"], list)
    assert len(body["participants"]) == 1

    p = body["participants"][0]
    assert p["id"] == joined["participant_id"]
    assert p["display_name"] == "Alice"
    assert p["is_ready"] is False
    assert isinstance(p["joined_at"], str) and p["joined_at"]
    assert p["left_at"] is None
