from __future__ import annotations

import pytest

from app.core.security import hash_password
from app.db.models.instructor import Instructor
from app.ws.deps import get_ws_manager


class FakeWsManager:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def broadcast(self, *, session_id, event_type: str, data: dict) -> None:
        self.calls.append({"session_id": str(session_id), "type": event_type, "data": data})


async def _login_and_get_headers(client, db_session, *, username: str = "instructor") -> dict[str, str]:
    instructor = Instructor(username=username, password_hash=hash_password("password-1234"))
    db_session.add(instructor)
    await db_session.commit()

    res = await client.post("/auth/login", json={"username": username, "password": "password-1234"})
    assert res.status_code == 200
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_start_requires_auth(client):
    res = await client.post("/sessions/00000000-0000-0000-0000-000000000000/start")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_start_rejects_when_no_participants(client, db_session, app):
    fake_ws = FakeWsManager()
    app.dependency_overrides[get_ws_manager] = lambda: fake_ws

    headers = await _login_and_get_headers(client, db_session)
    create_res = await client.post("/sessions", headers=headers)
    assert create_res.status_code == 201
    created = create_res.json()

    start_res = await client.post(f"/sessions/{created['session_id']}/start", headers=headers)
    assert start_res.status_code == 400
    assert start_res.json()["detail"] == "No participants have joined"


@pytest.mark.asyncio
async def test_start_rejects_when_not_all_ready(client, db_session, app):
    fake_ws = FakeWsManager()
    app.dependency_overrides[get_ws_manager] = lambda: fake_ws

    headers = await _login_and_get_headers(client, db_session)
    create_res = await client.post("/sessions", headers=headers)
    created = create_res.json()

    join_res = await client.post("/join", json={"team_id": created["team_id"], "display_name": "Alice"})
    assert join_res.status_code == 200

    start_res = await client.post(f"/sessions/{created['session_id']}/start", headers=headers)
    assert start_res.status_code == 400
    assert start_res.json()["detail"] == "Not all participants are ready"


@pytest.mark.asyncio
async def test_start_success_sets_running_and_broadcasts(client, db_session, app):
    fake_ws = FakeWsManager()
    app.dependency_overrides[get_ws_manager] = lambda: fake_ws

    headers = await _login_and_get_headers(client, db_session)
    create_res = await client.post("/sessions", headers=headers)
    created = create_res.json()

    join_res = await client.post("/join", json={"team_id": created["team_id"], "display_name": "Alice"})
    joined = join_res.json()

    ready_res = await client.post(
        "/participant/ready",
        headers={"X-Participant-Token": joined["participant_token"]},
        json={"is_ready": True},
    )
    assert ready_res.status_code == 200

    start_res = await client.post(f"/sessions/{created['session_id']}/start", headers=headers)
    assert start_res.status_code == 200
    body = start_res.json()

    assert body["status"] == "running"
    assert body["started_at"] is not None

    assert any(c["type"] == "session_started" for c in fake_ws.calls)


@pytest.mark.asyncio
async def test_start_rejects_when_already_running(client, db_session, app):
    fake_ws = FakeWsManager()
    app.dependency_overrides[get_ws_manager] = lambda: fake_ws

    headers = await _login_and_get_headers(client, db_session)
    create_res = await client.post("/sessions", headers=headers)
    created = create_res.json()

    join_res = await client.post("/join", json={"team_id": created["team_id"], "display_name": "Alice"})
    joined = join_res.json()

    ready_res = await client.post(
        "/participant/ready",
        headers={"X-Participant-Token": joined["participant_token"]},
        json={"is_ready": True},
    )
    assert ready_res.status_code == 200

    first_start = await client.post(f"/sessions/{created['session_id']}/start", headers=headers)
    assert first_start.status_code == 200

    second_start = await client.post(f"/sessions/{created['session_id']}/start", headers=headers)
    assert second_start.status_code == 400
    assert second_start.json()["detail"] == "Session is not in lobby"


@pytest.mark.asyncio
async def test_end_rejects_when_not_running(client, db_session, app):
    fake_ws = FakeWsManager()
    app.dependency_overrides[get_ws_manager] = lambda: fake_ws

    headers = await _login_and_get_headers(client, db_session)
    create_res = await client.post("/sessions", headers=headers)
    created = create_res.json()

    end_res = await client.post(f"/sessions/{created['session_id']}/end", headers=headers)
    assert end_res.status_code == 400
    assert end_res.json()["detail"] == "Session is not running"


@pytest.mark.asyncio
async def test_end_success_sets_ended_and_broadcasts(client, db_session, app):
    fake_ws = FakeWsManager()
    app.dependency_overrides[get_ws_manager] = lambda: fake_ws

    headers = await _login_and_get_headers(client, db_session)
    create_res = await client.post("/sessions", headers=headers)
    created = create_res.json()

    join_res = await client.post("/join", json={"team_id": created["team_id"], "display_name": "Alice"})
    joined = join_res.json()

    ready_res = await client.post(
        "/participant/ready",
        headers={"X-Participant-Token": joined["participant_token"]},
        json={"is_ready": True},
    )
    assert ready_res.status_code == 200

    start_res = await client.post(f"/sessions/{created['session_id']}/start", headers=headers)
    assert start_res.status_code == 200

    end_res = await client.post(f"/sessions/{created['session_id']}/end", headers=headers)
    assert end_res.status_code == 200
    body = end_res.json()

    assert body["status"] == "ended"
    assert body["ended_at"] is not None
    assert body["ended_by"] == "instructor"

    assert any(c["type"] == "session_ended" for c in fake_ws.calls)
