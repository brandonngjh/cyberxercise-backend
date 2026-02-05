# Cyberxercise API Contract (MVP)

Base URL: `/`

## Auth

### POST /auth/login
Instructor login.

Request body:
```json
{
  "username": "instructor1",
  "password": "secret"
}
```

Response (200):
```json
{
  "access_token": "<jwt>",
  "token_type": "bearer"
}
```

Errors:
- 401 invalid credentials

### POST /auth/register (optional)
Optional dev-only endpoint.

Request body:
```json
{
  "username": "instructor1",
  "password": "secret"
}
```

Response (201):
```json
{
  "id": "<uuid>",
  "username": "instructor1"
}
```

## Instructor (JWT required)

Auth header:
- `Authorization: Bearer <access_token>`

### POST /sessions
Create a lobby (exercise session) and generate a `team_id`.

Request body (optional):
```json
{
  "max_participants": 10,
  "duration_seconds": 900
}
```

Response (201):
```json
{
  "session_id": "<uuid>",
  "team_id": "ABCDEF",
  "status": "lobby",
  "max_participants": 10,
  "duration_seconds": 900
}
```

### GET /sessions/{session_id}
Get session details.

Response (200):
```json
{
  "id": "<uuid>",
  "instructor_id": "<uuid>",
  "team_id": "ABCDEF",
  "status": "lobby",
  "max_participants": 10,
  "duration_seconds": 900,
  "started_at": null,
  "ended_at": null,
  "ended_by": null,
  "created_at": "2026-02-04T00:00:00Z"
}
```

### GET /sessions/{session_id}/participants
List participants and ready state.

Response (200):
```json
{
  "session_id": "<uuid>",
  "participants": [
    {
      "id": "<uuid>",
      "display_name": "Alice",
      "is_ready": true,
      "joined_at": "2026-02-04T00:00:00Z",
      "left_at": null
    }
  ]
}
```

### POST /sessions/{session_id}/start
Start session (only if rules satisfied).

Response (200):
```json
{
  "id": "<uuid>",
  "status": "running",
  "started_at": "2026-02-04T00:00:00Z"
}
```

Errors:
- 400 if status != `lobby`
- 400 if participant count not in 1..10
- 400 if not all participants ready

### POST /sessions/{session_id}/end
End session.

Response (200):
```json
{
  "id": "<uuid>",
  "status": "ended",
  "ended_at": "2026-02-04T00:00:00Z",
  "ended_by": "instructor"
}
```

Errors:
- 400 if already ended

### GET /sessions/{session_id}/messages
List messages in session.

Response (200):
```json
{
  "session_id": "<uuid>",
  "messages": [
    {
      "id": "<uuid>",
      "participant_id": "<uuid>",
      "display_name": "Alice",
      "content": "hello",
      "created_at": "2026-02-04T00:00:00Z"
    }
  ]
}
```

## Participant

Participant token auth:
- Header: `X-Participant-Token: <participant_token>`

### POST /join
Join lobby by Team ID + display name. Creates a participant and returns an opaque participant token.

Request body:
```json
{
  "team_id": "ABCDEF",
  "display_name": "Alice"
}
```

Response (201):
```json
{
  "session_id": "<uuid>",
  "participant_id": "<uuid>",
  "participant_token": "<opaque_token>",
  "status": "lobby"
}
```

Rules:
- allowed only when status is `lobby`
- allowed only when capacity < 10
- `display_name` unique per session

Errors:
- 404 unknown team_id
- 409 display_name already exists
- 400 session not in lobby / session full

### POST /participant/ready
Set ready state (lobby only).

Headers:
- `X-Participant-Token: <participant_token>`

Request body:
```json
{
  "is_ready": true
}
```

Response (200):
```json
{
  "participant_id": "<uuid>",
  "is_ready": true
}
```

Errors:
- 401 invalid/revoked/expired token
- 400 if session status != `lobby`

### POST /participant/message
Submit message (running only).

Headers:
- `X-Participant-Token: <participant_token>`

Request body:
```json
{
  "content": "Hello instructor"
}
```

Response (201):
```json
{
  "message_id": "<uuid>",
  "created_at": "2026-02-04T00:00:00Z"
}
```

Errors:
- 401 invalid/revoked/expired token
- 400 if session status != `running`

## WebSockets

### GET ws/instructor/{session_id}
Instructor realtime feed for a session.

Auth:
- Prefer `Authorization: Bearer <jwt>` if client supports it.
- Otherwise allow query param: `?access_token=<jwt>`.

Server events (JSON):
```json
{ "type": "participant_joined", "participant": { "id": "<uuid>", "display_name": "Alice", "is_ready": false } }
```

### GET ws/participant/{team_id}
Participant realtime feed.

Auth:
- Query param: `?token=<participant_token>`
- Team ID input normalized by `strip()` + `upper()`.

Server events (JSON):
- `participant_joined`
- `participant_left`
- `participant_ready_changed`
- `session_started`
- `session_ended`
- `message_submitted`

Event envelope:
```json
{
  "type": "message_submitted",
  "data": {
    "message_id": "<uuid>",
    "participant_id": "<uuid>",
    "display_name": "Alice",
    "content": "hello",
    "created_at": "2026-02-04T00:00:00Z"
  }
}
```
