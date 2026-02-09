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

Response (200): returns the full Session Detail object (same shape as `GET /sessions/{session_id}`), with `status=running` and `started_at` set.

Errors:

- 400 `Session is not in lobby`
- 400 `No participants have joined`
- 400 `Not all participants are ready`

### POST /sessions/{session_id}/end

End session.

Response (200): returns the full Session Detail object (same shape as `GET /sessions/{session_id}`), with `status=ended`, `ended_at` set, and `ended_by=instructor`.

Errors:

- 400 `Session is not running`

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

Response (200):

```json
{
  "participant_token": "<opaque_token>",
  "participant_id": "<uuid>",
  "session_id": "<uuid>"
}
```

Rules:

- allowed only when status is `lobby`
- allowed only when capacity < 10
- `display_name` unique per session

Errors:

- 404 unknown team_id
- 409 session not joinable / session full / display name already taken / unable to join

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

Response (200):

```json
{
  "message_id": "<uuid>",
  "session_id": "<uuid>",
  "participant_id": "<uuid>",
  "content": "Hello instructor"
}
```

Errors:

- 401 invalid/revoked/expired token
- 400 if session status != `running`

### POST /participant/leave

Leave the session (best-effort). Revokes the participant token and marks `left_at`.

Headers:

- `X-Participant-Token: <participant_token>`

Response (200):

```json
{
  "participant_id": "<uuid>",
  "session_id": "<uuid>",
  "left_at": "2026-02-04T00:00:00Z"
}
```

Errors:

- 401 invalid/revoked/expired token

## WebSockets

### WS /ws/instructor/{session_id}

Instructor realtime feed for a session.

Auth:

- Prefer `Authorization: Bearer <jwt>` if client supports it.
- Otherwise allow query param: `?access_token=<jwt>`.

Event envelope:

```json
{
  "type": "participant_joined",
  "data": {
    "participant": {
      "id": "<uuid>",
      "display_name": "Alice",
      "is_ready": false
    }
  }
}
```

### WS /ws/participant/{team_id}

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

Event envelope (all events):

```json
{
  "type": "<event_type>",
  "data": { "...": "..." }
}
```

Payload shapes:

- `participant_joined`, `participant_ready_changed`:
  - `data.participant`: `{ id, display_name, is_ready }`
- `participant_left`:
  - `data.participant`: `{ id, display_name, left_at }`
- `session_started`:
  - `data.session`: `{ id, status, started_at }`
- `session_ended`:
  - `data.session`: `{ id, status, ended_at, ended_by }`
- `message_submitted`:
  - `data.message`: `{ id, participant_id, content, created_at }`
  - `data.participant`: `{ id, display_name }`
