from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.join import router as join_router
from app.api.participant import router as participant_router
from app.api.sessions import router as sessions_router

api_router = APIRouter()
api_router.include_router(auth_router)
api_router.include_router(sessions_router)
api_router.include_router(join_router)
api_router.include_router(participant_router)
