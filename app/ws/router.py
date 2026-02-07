from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.core.settings import Settings, get_settings
from app.db.deps import get_db_session
from app.db.models.exercise_session import ExerciseSession, SessionStatus
from app.db.models.instructor import Instructor
from app.db.models.participant import Participant
from app.services.participant_tokens import hash_participant_token
from app.ws.deps import get_ws_manager
from app.ws.manager import WsManager


router = APIRouter(tags=["ws"])

_TEAM_ID_RE = re.compile(r"^[A-HJ-NP-Z2-9]{6}$")


@router.websocket("/ws/instructor/{session_id}")
async def ws_instructor(
    websocket: WebSocket,
    session_id: uuid.UUID,
    access_token: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    ws: WsManager = Depends(get_ws_manager),
):
    auth_header = websocket.headers.get("authorization")
    token = None
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1].strip()
    token = token or access_token

    if not token:
        await websocket.close(code=1008)
        return

    try:
        token_data = decode_access_token(settings, token)
        instructor_id = uuid.UUID(token_data.instructor_id)
    except Exception:
        await websocket.close(code=1008)
        return

    instructor_result = await db.execute(select(Instructor).where(Instructor.id == instructor_id))
    instructor = instructor_result.scalar_one_or_none()
    if instructor is None:
        await websocket.close(code=1008)
        return

    session_result = await db.execute(
        select(ExerciseSession)
        .where(ExerciseSession.id == session_id)
        .where(ExerciseSession.instructor_id == instructor.id)
    )
    session = session_result.scalar_one_or_none()
    if session is None:
        await websocket.close(code=1008)
        return

    await ws.connect_instructor(session_id, websocket)
    try:
        while True:
            # MVP: server-push only
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws.disconnect(session_id, websocket)


@router.websocket("/ws/participant/{team_id}")
async def ws_participant(
    websocket: WebSocket,
    team_id: str,
    token: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    ws: WsManager = Depends(get_ws_manager),
):
    normalized_team_id = team_id.strip().upper()
    if not _TEAM_ID_RE.match(normalized_team_id):
        await websocket.close(code=1008)
        return

    token = token or websocket.headers.get("x-participant-token")
    if not token:
        await websocket.close(code=1008)
        return

    session_result = await db.execute(
        select(ExerciseSession).where(ExerciseSession.team_id == normalized_team_id)
    )
    session = session_result.scalar_one_or_none()
    if session is None:
        await websocket.close(code=1008)
        return

    if session.status == SessionStatus.ended:
        await websocket.close(code=1008)
        return

    token_hash = hash_participant_token(token=token, pepper=settings.participant_token_pepper)
    participant_result = await db.execute(
        select(Participant)
        .where(Participant.session_id == session.id)
        .where(Participant.token_hash == token_hash)
        .where(Participant.token_revoked_at.is_(None))
    )
    participant = participant_result.scalar_one_or_none()
    if participant is None:
        await websocket.close(code=1008)
        return

    await ws.connect_participant(session.id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await ws.disconnect(session.id, websocket)
