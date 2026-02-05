from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.core.settings import Settings, get_settings
from app.db.deps import get_db_session
from app.db.models.instructor import Instructor


router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=72)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=72)


class InstructorResponse(BaseModel):
    id: uuid.UUID
    username: str


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> TokenResponse:
    result = await db.execute(select(Instructor).where(Instructor.username == body.username))
    instructor = result.scalar_one_or_none()

    if instructor is None or not verify_password(body.password, instructor.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token(settings, instructor_id=str(instructor.id))
    return TokenResponse(access_token=token)


@router.post("/register", response_model=InstructorResponse, status_code=status.HTTP_201_CREATED)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db_session),
    settings: Settings = Depends(get_settings),
) -> InstructorResponse:
    if not settings.allow_instructor_register:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found")

    instructor = Instructor(username=body.username, password_hash=hash_password(body.password))
    db.add(instructor)

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

    await db.refresh(instructor)
    return InstructorResponse(id=instructor.id, username=instructor.username)
