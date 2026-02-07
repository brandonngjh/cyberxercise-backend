from __future__ import annotations

import secrets


_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_team_id(*, length: int = 6) -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(length))
