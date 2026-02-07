from __future__ import annotations

import uuid

import pytest

from app.core.security import hash_password
from app.db.models.exercise_session import SessionStatus
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
async def test_ready_requires_participant_token(client):
    res = await client.post("/participant/ready", json={"is_ready": True})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_ready_toggles_and_broadcasts(client, db_session, app):
    fake_ws = FakeWsManager()
    app.dependency_overrides[get_ws_manager] = lambda: fake_ws

    headers = await _login_and_get_headers(client, db_session)
    create_res = await client.post("/sessions", headers=headers)
    assert create_res.status_code == 201
    created = create_res.json()

    join_res = await client.post("/join", json={"team_id": created["team_id"], "display_name": "Alice"})
    assert join_res.status_code == 200
    joined = join_res.json()

    # join should broadcast participant_joined
    assert any(c["type"] == "participant_joined" for c in fake_ws.calls)

    ready_res = await client.post(
        "/participant/ready",
        headers={"X-Participant-Token": joined["participant_token"]},
        json={"is_ready": True},
    )
    assert ready_res.status_code == 200
    body = ready_res.json()
    assert body["participant_id"] == joined["participant_id"]
    assert body["is_ready"] is True

    assert any(c["type"] == "participant_ready_changed" for c in fake_ws.calls)


@pytest.mark.asyncio
async def test_ready_rejects_when_not_lobby(client, db_session, app):
    fake_ws = FakeWsManager()
    app.dependency_overrides[get_ws_manager] = lambda: fake_ws

    headers = await _login_and_get_headers(client, db_session)
    create_res = await client.post("/sessions", headers=headers)
    created = create_res.json()

    join_res = await client.post("/join", json={"team_id": created["team_id"], "display_name": "Alice"})
    joined = join_res.json()

    # Force session to running
    from sqlalchemy import select
    from app.db.models.exercise_session import ExerciseSession

    sess = (
        await db_session.execute(
            select(ExerciseSession).where(ExerciseSession.id == created["session_id"])
        )
    ).scalar_one()
    sess.status = SessionStatus.running
    await db_session.commit()

    res = await client.post(
        "/participant/ready",
        headers={"X-Participant-Token": joined["participant_token"]},
        json={"is_ready": True},
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Session is not in lobby"


@pytest.mark.asyncio
async def test_ws_manager_broadcast_delivers_to_connected_sockets():
    from app.ws.manager import WsManager

    class FakeSocket:
        def __init__(self) -> None:
            self.accepted = False
            self.sent: list[dict] = []

        async def accept(self) -> None:
            self.accepted = True

        async def send_json(self, payload: dict) -> None:
            self.sent.append(payload)

    manager = WsManager()
    session_id = uuid.uuid4()

    ws1 = FakeSocket()
    ws2 = FakeSocket()

    await manager.connect_instructor(session_id, ws1)  # type: ignore[arg-type]
    await manager.connect_participant(session_id, ws2)  # type: ignore[arg-type]

    await manager.broadcast(session_id=session_id, event_type="participant_ready_changed", data={"x": 1})

    assert ws1.sent == [{"type": "participant_ready_changed", "data": {"x": 1}}]
    assert ws2.sent == [{"type": "participant_ready_changed", "data": {"x": 1}}]
