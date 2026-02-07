from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.settings import Settings, get_settings
from app.db.deps import get_db_session
from app.db.models.exercise_session import ExerciseSession, SessionStatus
from app.db.models.participant import Participant
from app.services.participant_tokens import generate_participant_token, hash_participant_token
from app.ws.deps import get_ws_manager
from app.ws.manager import WsManager


router = APIRouter(tags=["participant"])


class JoinRequest(BaseModel):
    team_id: str = Field(min_length=6, max_length=6, pattern=r"^[A-HJ-NP-Z2-9]{6}$")
    display_name: str = Field(min_length=1, max_length=64)


class JoinResponse(BaseModel):
    participant_token: str
    participant_id: uuid.UUID
    session_id: uuid.UUID


@router.post("/join", response_model=JoinResponse)
async def join_session(
    body: JoinRequest,
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
    ws: WsManager = Depends(get_ws_manager),
) -> JoinResponse:
    result = await db.execute(select(ExerciseSession).where(ExerciseSession.team_id == body.team_id))
    session = result.scalar_one_or_none()

    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session.status != SessionStatus.lobby:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session is not joinable")

    count_result = await db.execute(
        select(func.count())
        .select_from(Participant)
        .where(Participant.session_id == session.id)
        .where(Participant.left_at.is_(None))
    )
    active_count = int(count_result.scalar_one())
    if active_count >= session.max_participants:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Session is full")

    exists_result = await db.execute(
        select(Participant.id)
        .where(Participant.session_id == session.id)
        .where(Participant.display_name == body.display_name)
    )
    if exists_result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Display name already taken")

    participant_token = generate_participant_token()
    token_hash = hash_participant_token(token=participant_token, pepper=settings.participant_token_pepper)

    participant = Participant(
        session_id=session.id,
        display_name=body.display_name,
        token_hash=token_hash,
    )
    db.add(participant)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        # Could be display_name uniqueness under concurrency or token_hash uniqueness (extremely unlikely).
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Unable to join")

    await db.refresh(participant)

    await ws.broadcast(
        session_id=session.id,
        event_type="participant_joined",
        data={
            "participant": {
                "id": str(participant.id),
                "display_name": participant.display_name,
                "is_ready": participant.is_ready,
            }
        },
    )

    return JoinResponse(
        participant_token=participant_token,
        participant_id=participant.id,
        session_id=session.id,
    )
