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
async def test_leave_requires_participant_token(client):
    res = await client.post("/participant/leave")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_leave_sets_left_at_revokes_token_broadcasts_and_frees_capacity(client, db_session, app):
    fake_ws = FakeWsManager()
    app.dependency_overrides[get_ws_manager] = lambda: fake_ws

    headers = await _login_and_get_headers(client, db_session)
    create_res = await client.post("/sessions", headers=headers, json={"max_participants": 1})
    assert create_res.status_code == 201
    created = create_res.json()

    join1 = await client.post("/join", json={"team_id": created["team_id"], "display_name": "Alice"})
    assert join1.status_code == 200
    p1 = join1.json()

    leave_res = await client.post(
        "/participant/leave",
        headers={"X-Participant-Token": p1["participant_token"]},
    )
    assert leave_res.status_code == 200
    left_body = leave_res.json()
    assert left_body["participant_id"] == p1["participant_id"]
    assert left_body["session_id"] == created["session_id"]
    assert left_body["left_at"]

    assert any(c["type"] == "participant_left" for c in fake_ws.calls)

    # Token should be invalid after leaving
    ready_res = await client.post(
        "/participant/ready",
        headers={"X-Participant-Token": p1["participant_token"]},
        json={"is_ready": True},
    )
    assert ready_res.status_code == 401

    # Capacity should be freed (max_participants=1)
    join2 = await client.post("/join", json={"team_id": created["team_id"], "display_name": "Bob"})
    assert join2.status_code == 200
