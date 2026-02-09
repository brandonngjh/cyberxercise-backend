from __future__ import annotations

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.db.models.instructor import Instructor
from app.db.models.message import Message
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
async def test_submit_message_requires_participant_token(client):
    res = await client.post("/participant/message", json={"content": "hi"})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_submit_message_rejects_when_not_running(client, db_session, app):
    fake_ws = FakeWsManager()
    app.dependency_overrides[get_ws_manager] = lambda: fake_ws

    headers = await _login_and_get_headers(client, db_session)
    create_res = await client.post("/sessions", headers=headers)
    created = create_res.json()

    join_res = await client.post("/join", json={"team_id": created["team_id"], "display_name": "Alice"})
    joined = join_res.json()

    res = await client.post(
        "/participant/message",
        headers={"X-Participant-Token": joined["participant_token"]},
        json={"content": "hello"},
    )
    assert res.status_code == 400
    assert res.json()["detail"] == "Session is not running"


@pytest.mark.asyncio
async def test_submit_message_persists_broadcasts_and_lists(client, db_session, app):
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

    submit_res = await client.post(
        "/participant/message",
        headers={"X-Participant-Token": joined["participant_token"]},
        json={"content": "hello world"},
    )
    assert submit_res.status_code == 200
    body = submit_res.json()

    assert body["session_id"] == created["session_id"]
    assert body["participant_id"] == joined["participant_id"]
    assert body["content"] == "hello world"
    assert isinstance(body["message_id"], str) and body["message_id"]

    assert any(c["type"] == "message_submitted" for c in fake_ws.calls)

    # Verify persistence
    result = await db_session.execute(select(Message).where(Message.id == body["message_id"]))
    msg = result.scalar_one_or_none()
    assert msg is not None
    assert msg.content == "hello world"

    # Instructor message listing
    list_res = await client.get(f"/sessions/{created['session_id']}/messages", headers=headers)
    assert list_res.status_code == 200
    listed = list_res.json()

    assert listed["session_id"] == created["session_id"]
    assert len(listed["messages"]) == 1
    assert listed["messages"][0]["id"] == body["message_id"]
    assert listed["messages"][0]["participant_id"] == joined["participant_id"]
    assert listed["messages"][0]["display_name"] == "Alice"
    assert listed["messages"][0]["content"] == "hello world"
    assert listed["messages"][0]["created_at"]
