from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


if TYPE_CHECKING:
    from app.db.models.instructor import Instructor
    from app.db.models.message import Message
    from app.db.models.participant import Participant


class SessionStatus(str, enum.Enum):
    lobby = "lobby"
    running = "running"
    ended = "ended"


class SessionEndedBy(str, enum.Enum):
    instructor = "instructor"
    system = "system"


class ExerciseSession(Base):
    __tablename__ = "exercise_sessions"

    __table_args__ = (
        sa.CheckConstraint("max_participants BETWEEN 1 AND 10", name="ck_sessions_max_participants"),
        sa.CheckConstraint(
            "team_id ~ '^[A-HJ-NP-Z2-9]{6}$'",
            name="ck_sessions_team_id_format",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    instructor_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), sa.ForeignKey("instructors.id", ondelete="CASCADE"), nullable=False
    )

    team_id: Mapped[str] = mapped_column(sa.String(6), unique=True, index=True, nullable=False)

    status: Mapped[SessionStatus] = mapped_column(
        sa.Enum(SessionStatus, name="session_status"),
        nullable=False,
        server_default=sa.text("'lobby'"),
    )

    max_participants: Mapped[int] = mapped_column(
        sa.Integer(), nullable=False, server_default=sa.text("10")
    )

    duration_seconds: Mapped[int | None] = mapped_column(sa.Integer(), nullable=True)

    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    ended_by: Mapped[SessionEndedBy | None] = mapped_column(
        sa.Enum(SessionEndedBy, name="session_ended_by"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )

    instructor: Mapped["Instructor"] = relationship(back_populates="sessions")
    participants: Mapped[list["Participant"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
    messages: Mapped[list["Message"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )
