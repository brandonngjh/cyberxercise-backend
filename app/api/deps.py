from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.core.settings import Settings, get_settings
from app.db.deps import get_db_session
from app.db.models.instructor import Instructor


_bearer = HTTPBearer(auto_error=False)


async def get_current_instructor(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> Instructor:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    try:
        token_data = decode_access_token(settings, credentials.credentials)
        instructor_id = uuid.UUID(token_data.instructor_id)
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    result = await db.execute(select(Instructor).where(Instructor.id == instructor_id))
    instructor = result.scalar_one_or_none()
    if instructor is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    return instructor
