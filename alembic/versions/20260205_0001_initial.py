"""initial

Revision ID: 20260205_0001
Revises:
Create Date: 2026-02-05

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "20260205_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create PG ENUM types once (checkfirst=True), and ensure table creation does
    # not try to create them again.
    session_status_enum = postgresql.ENUM(
        "lobby", "running", "ended", name="session_status"
    )
    session_ended_by_enum = postgresql.ENUM(
        "instructor", "system", name="session_ended_by"
    )

    session_status_enum.create(op.get_bind(), checkfirst=True)
    session_ended_by_enum.create(op.get_bind(), checkfirst=True)

    session_status = postgresql.ENUM(
        "lobby", "running", "ended", name="session_status", create_type=False
    )
    session_ended_by = postgresql.ENUM(
        "instructor", "system", name="session_ended_by", create_type=False
    )

    op.create_table(
        "instructors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("username", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("username", name="uq_instructors_username"),
    )
    op.create_index("ix_instructors_username", "instructors", ["username"], unique=False)

    op.create_table(
        "exercise_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "instructor_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("instructors.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("team_id", sa.String(length=6), nullable=False),
        sa.Column(
            "status",
            session_status,
            server_default=sa.text("'lobby'"),
            nullable=False,
        ),
        sa.Column(
            "max_participants",
            sa.Integer(),
            server_default=sa.text("10"),
            nullable=False,
        ),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_by", session_ended_by, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "max_participants BETWEEN 1 AND 10",
            name="ck_sessions_max_participants",
        ),
        sa.CheckConstraint(
            "team_id ~ '^[A-HJ-NP-Z2-9]{6}$'",
            name="ck_sessions_team_id_format",
        ),
        sa.UniqueConstraint("team_id", name="uq_exercise_sessions_team_id"),
    )
    op.create_index(
        "ix_exercise_sessions_team_id", "exercise_sessions", ["team_id"], unique=False
    )

    op.create_table(
        "participants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("exercise_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("display_name", sa.String(length=64), nullable=False),
        sa.Column(
            "is_ready",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("token_hash", postgresql.BYTEA(), nullable=False),
        sa.Column("token_revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "octet_length(token_hash) = 32",
            name="ck_participants_token_hash_len",
        ),
        sa.UniqueConstraint(
            "session_id",
            "display_name",
            name="uq_participants_session_display_name",
        ),
        sa.UniqueConstraint("token_hash", name="uq_participants_token_hash"),
    )
    op.create_index("ix_participants_session_id", "participants", ["session_id"], unique=False)
    op.create_index("ix_participants_token_hash", "participants", ["token_hash"], unique=True)

    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("exercise_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "participant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("participants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_messages_participant_id", "messages", ["participant_id"], unique=False)
    op.create_index("ix_messages_session_id", "messages", ["session_id"], unique=False)
    op.create_index(
        "ix_messages_session_id_created_at",
        "messages",
        ["session_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_messages_session_id_created_at", table_name="messages")
    op.drop_index("ix_messages_session_id", table_name="messages")
    op.drop_index("ix_messages_participant_id", table_name="messages")
    op.drop_table("messages")

    op.drop_index("ix_participants_token_hash", table_name="participants")
    op.drop_index("ix_participants_session_id", table_name="participants")
    op.drop_table("participants")

    op.drop_index("ix_exercise_sessions_team_id", table_name="exercise_sessions")
    op.drop_table("exercise_sessions")

    op.drop_index("ix_instructors_username", table_name="instructors")
    op.drop_table("instructors")

    postgresql.ENUM(name="session_ended_by").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="session_status").drop(op.get_bind(), checkfirst=True)
