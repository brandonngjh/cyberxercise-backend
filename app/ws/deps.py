from __future__ import annotations

from functools import lru_cache

from app.ws.manager import WsManager


@lru_cache
def get_ws_manager() -> WsManager:
    return WsManager()
