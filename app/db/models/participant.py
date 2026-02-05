from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


if TYPE_CHECKING:
    from app.db.models.exercise_session import ExerciseSession
    from app.db.models.message import Message


class Participant(Base):
    __tablename__ = "participants"

    __table_args__ = (
        sa.UniqueConstraint("session_id", "display_name", name="uq_participants_session_display_name"),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32",
            name="ck_participants_token_hash_len",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    session_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("exercise_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    display_name: Mapped[str] = mapped_column(sa.String(64), nullable=False)

    is_ready: Mapped[bool] = mapped_column(
        sa.Boolean(), nullable=False, server_default=sa.text("false")
    )

    token_hash: Mapped[bytes] = mapped_column(
        postgresql.BYTEA, nullable=False, unique=True, index=True
    )
    token_revoked_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    joined_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )
    left_at: Mapped[datetime | None] = mapped_column(sa.DateTime(timezone=True), nullable=True)

    session: Mapped["ExerciseSession"] = relationship(back_populates="participants")
    messages: Mapped[list["Message"]] = relationship(
        back_populates="participant", cascade="all, delete-orphan"
    )
