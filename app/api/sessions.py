from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_instructor
from app.db.deps import get_db_session
from app.db.models.exercise_session import ExerciseSession, SessionEndedBy, SessionStatus
from app.db.models.instructor import Instructor
from app.db.models.participant import Participant
from app.services.team_id import generate_team_id
from app.ws.deps import get_ws_manager
from app.ws.manager import WsManager


router = APIRouter(prefix="/sessions", tags=["sessions"])


class CreateSessionRequest(BaseModel):
    max_participants: int = Field(default=10, ge=1, le=10)
    duration_seconds: int | None = Field(default=None, ge=1)


class SessionCreatedResponse(BaseModel):
    session_id: uuid.UUID
    team_id: str
    status: SessionStatus
    max_participants: int
    duration_seconds: int | None


class SessionDetailResponse(BaseModel):
    id: uuid.UUID
    instructor_id: uuid.UUID
    team_id: str
    status: SessionStatus
    max_participants: int
    duration_seconds: int | None
    started_at: datetime | None
    ended_at: datetime | None
    ended_by: SessionEndedBy | None
    created_at: datetime


class ParticipantResponse(BaseModel):
    id: uuid.UUID
    display_name: str
    is_ready: bool
    joined_at: datetime
    left_at: datetime | None


class ParticipantsListResponse(BaseModel):
    session_id: uuid.UUID
    participants: list[ParticipantResponse]


@router.post("", response_model=SessionCreatedResponse, status_code=status.HTTP_201_CREATED)
async def create_session(
    body: CreateSessionRequest | None = None,
    instructor: Instructor = Depends(get_current_instructor),
    db: AsyncSession = Depends(get_db_session),
) -> SessionCreatedResponse:
    body = body or CreateSessionRequest()
    # Team ID collisions are unlikely, but handle it gracefully.
    for _ in range(10):
        session = ExerciseSession(
            instructor_id=instructor.id,
            team_id=generate_team_id(),
            status=SessionStatus.lobby,
            max_participants=body.max_participants,
            duration_seconds=body.duration_seconds,
        )
        db.add(session)

        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            continue

        await db.refresh(session)
        return SessionCreatedResponse(
            session_id=session.id,
            team_id=session.team_id,
            status=session.status,
            max_participants=session.max_participants,
            duration_seconds=session.duration_seconds,
        )

    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Unable to allocate a unique team ID. Please retry.",
    )


@router.get("/{session_id}", response_model=SessionDetailResponse)
async def get_session_details(
    session_id: uuid.UUID,
    instructor: Instructor = Depends(get_current_instructor),
    db: AsyncSession = Depends(get_db_session),
) -> SessionDetailResponse:
    result = await db.execute(
        select(ExerciseSession)
        .where(ExerciseSession.id == session_id)
        .where(ExerciseSession.instructor_id == instructor.id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    return SessionDetailResponse(
        id=session.id,
        instructor_id=session.instructor_id,
        team_id=session.team_id,
        status=session.status,
        max_participants=session.max_participants,
        duration_seconds=session.duration_seconds,
        started_at=session.started_at,
        ended_at=session.ended_at,
        ended_by=session.ended_by,
        created_at=session.created_at,
    )


@router.get("/{session_id}/participants", response_model=ParticipantsListResponse)
async def list_session_participants(
    session_id: uuid.UUID,
    instructor: Instructor = Depends(get_current_instructor),
    db: AsyncSession = Depends(get_db_session),
) -> ParticipantsListResponse:
    session_result = await db.execute(
        select(ExerciseSession)
        .where(ExerciseSession.id == session_id)
        .where(ExerciseSession.instructor_id == instructor.id)
    )
    session = session_result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    participants_result = await db.execute(
        select(Participant)
        .where(Participant.session_id == session.id)
        .order_by(Participant.joined_at.asc())
    )
    participants = participants_result.scalars().all()

    return ParticipantsListResponse(
        session_id=session.id,
        participants=[
            ParticipantResponse(
                id=p.id,
                display_name=p.display_name,
                is_ready=p.is_ready,
                joined_at=p.joined_at,
                left_at=p.left_at,
            )
            for p in participants
        ],
    )


@router.post("/{session_id}/start", response_model=SessionDetailResponse)
async def start_session(
    session_id: uuid.UUID,
    instructor: Instructor = Depends(get_current_instructor),
    db: AsyncSession = Depends(get_db_session),
    ws: WsManager = Depends(get_ws_manager),
) -> SessionDetailResponse:
    result = await db.execute(
        select(ExerciseSession)
        .where(ExerciseSession.id == session_id)
        .where(ExerciseSession.instructor_id == instructor.id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session.status != SessionStatus.lobby:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session is not in lobby")

    active_count_result = await db.execute(
        select(func.count())
        .select_from(Participant)
        .where(Participant.session_id == session.id)
        .where(Participant.left_at.is_(None))
    )
    active_count = int(active_count_result.scalar_one())
    if active_count < 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No participants have joined",
        )

    not_ready_count_result = await db.execute(
        select(func.count())
        .select_from(Participant)
        .where(Participant.session_id == session.id)
        .where(Participant.left_at.is_(None))
        .where(Participant.is_ready.is_(False))
    )
    not_ready_count = int(not_ready_count_result.scalar_one())
    if not_ready_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Not all participants are ready",
        )

    session.status = SessionStatus.running
    session.started_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(session)

    await ws.broadcast(
        session_id=session.id,
        event_type="session_started",
        data={
            "session": {
                "id": str(session.id),
                "status": session.status,
                "started_at": session.started_at.isoformat() if session.started_at else None,
            }
        },
    )

    return SessionDetailResponse(
        id=session.id,
        instructor_id=session.instructor_id,
        team_id=session.team_id,
        status=session.status,
        max_participants=session.max_participants,
        duration_seconds=session.duration_seconds,
        started_at=session.started_at,
        ended_at=session.ended_at,
        ended_by=session.ended_by,
        created_at=session.created_at,
    )


@router.post("/{session_id}/end", response_model=SessionDetailResponse)
async def end_session(
    session_id: uuid.UUID,
    instructor: Instructor = Depends(get_current_instructor),
    db: AsyncSession = Depends(get_db_session),
    ws: WsManager = Depends(get_ws_manager),
) -> SessionDetailResponse:
    result = await db.execute(
        select(ExerciseSession)
        .where(ExerciseSession.id == session_id)
        .where(ExerciseSession.instructor_id == instructor.id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")

    if session.status != SessionStatus.running:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session is not running")

    session.status = SessionStatus.ended
    session.ended_at = datetime.now(timezone.utc)
    session.ended_by = SessionEndedBy.instructor
    await db.commit()
    await db.refresh(session)

    await ws.broadcast(
        session_id=session.id,
        event_type="session_ended",
        data={
            "session": {
                "id": str(session.id),
                "status": session.status,
                "ended_at": session.ended_at.isoformat() if session.ended_at else None,
                "ended_by": session.ended_by,
            }
        },
    )

    return SessionDetailResponse(
        id=session.id,
        instructor_id=session.instructor_id,
        team_id=session.team_id,
        status=session.status,
        max_participants=session.max_participants,
        duration_seconds=session.duration_seconds,
        started_at=session.started_at,
        ended_at=session.ended_at,
        ended_by=session.ended_by,
        created_at=session.created_at,
    )
