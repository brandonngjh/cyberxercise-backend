from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class WsManager:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._instructor_connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._participant_connections: dict[str, set[WebSocket]] = defaultdict(set)

    @staticmethod
    def _key(session_id) -> str:
        return str(session_id)

    async def connect_instructor(self, session_id, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._instructor_connections[self._key(session_id)].add(websocket)

    async def connect_participant(self, session_id, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._participant_connections[self._key(session_id)].add(websocket)

    async def disconnect(self, session_id, websocket: WebSocket) -> None:
        key = self._key(session_id)
        async with self._lock:
            self._instructor_connections[key].discard(websocket)
            self._participant_connections[key].discard(websocket)

            if not self._instructor_connections[key] and key in self._instructor_connections:
                self._instructor_connections.pop(key, None)
            if not self._participant_connections[key] and key in self._participant_connections:
                self._participant_connections.pop(key, None)

    async def broadcast(self, *, session_id, event_type: str, data: dict[str, Any]) -> None:
        key = self._key(session_id)
        async with self._lock:
            targets = list(self._instructor_connections.get(key, set())) + list(
                self._participant_connections.get(key, set())
            )

        if not targets:
            return

        payload = {"type": event_type, "data": data}
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception:
                # Best-effort; stale sockets will be cleaned up on disconnect.
                pass
