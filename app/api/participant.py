from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Settings, get_settings
from app.db.deps import get_db_session
from app.db.models.exercise_session import ExerciseSession, SessionStatus
from app.db.models.message import Message
from app.db.models.participant import Participant
from app.services.participant_tokens import hash_participant_token
from app.ws.deps import get_ws_manager
from app.ws.manager import WsManager


router = APIRouter(prefix="/participant", tags=["participant"])


async def get_current_participant(
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    x_participant_token: str | None = Header(default=None, alias="X-Participant-Token"),
) -> tuple[ExerciseSession, Participant]:
    if not x_participant_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    token_hash = hash_participant_token(token=x_participant_token, pepper=settings.participant_token_pepper)

    result = await db.execute(select(Participant).where(Participant.token_hash == token_hash))
    participant = result.scalar_one_or_none()
    if participant is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if participant.token_revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if participant.left_at is not None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    session_result = await db.execute(
        select(ExerciseSession).where(ExerciseSession.id == participant.session_id)
    )
    session = session_result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if session.status == SessionStatus.ended:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    return session, participant


class ReadyRequest(BaseModel):
    is_ready: bool


class ReadyResponse(BaseModel):
    participant_id: uuid.UUID
    is_ready: bool


@router.post("/ready", response_model=ReadyResponse)
async def set_ready_state(
    body: ReadyRequest,
    current: tuple[ExerciseSession, Participant] = Depends(get_current_participant),
    db: AsyncSession = Depends(get_db_session),
    ws: WsManager = Depends(get_ws_manager),
) -> ReadyResponse:
    session, participant = current

    if session.status != SessionStatus.lobby:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session is not in lobby")

    participant.is_ready = body.is_ready
    await db.commit()

    await ws.broadcast(
        session_id=session.id,
        event_type="participant_ready_changed",
        data={
            "participant": {
                "id": str(participant.id),
                "display_name": participant.display_name,
                "is_ready": participant.is_ready,
            }
        },
    )

    return ReadyResponse(participant_id=participant.id, is_ready=participant.is_ready)


class SubmitMessageRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2000)


class SubmitMessageResponse(BaseModel):
    message_id: uuid.UUID
    session_id: uuid.UUID
    participant_id: uuid.UUID
    content: str


@router.post("/message", response_model=SubmitMessageResponse)
async def submit_message(
    body: SubmitMessageRequest,
    current: tuple[ExerciseSession, Participant] = Depends(get_current_participant),
    db: AsyncSession = Depends(get_db_session),
    ws: WsManager = Depends(get_ws_manager),
) -> SubmitMessageResponse:
    session, participant = current

    if session.status != SessionStatus.running:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session is not running")

    message = Message(
        session_id=session.id,
        participant_id=participant.id,
        content=body.content,
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)

    await ws.broadcast(
        session_id=session.id,
        event_type="message_submitted",
        data={
            "message": {
                "id": str(message.id),
                "participant_id": str(message.participant_id),
                "content": message.content,
                "created_at": message.created_at.isoformat(),
            },
            "participant": {
                "id": str(participant.id),
                "display_name": participant.display_name,
            },
        },
    )

    return SubmitMessageResponse(
        message_id=message.id,
        session_id=session.id,
        participant_id=participant.id,
        content=message.content,
    )
