# Cyberxercise MVP Requirements

## Roles

### Instructor (authenticated)
- Logs in with username/password (JWT access token returned)
- Creates a lobby (creates an Exercise Session with generated Team ID)
- Sees participants and ready states in realtime
- Can start a session only when:
  - session status is `lobby`
  - participant count is in `1..10`
  - **all participants are ready**
- Session runs until:
  - duration ends (if `duration_seconds` is set), **or**
  - instructor ends it
- Once ended, instructor can create another session
- All session data and participant messages are stored

### Participant (no login)
- Joins by `team_id` + `display_name`
- `display_name` must be unique **within the session**, but may be reused across other sessions
- Can ready/unready during lobby
- When session is running: can submit text messages
- Messages are stored under the session and broadcast to the instructor in realtime

## Realtime Events (WebSocket)

Broadcast events:
- `participant_joined`
- `participant_left`
- `participant_ready_changed`
- `session_started`
- `session_ended`
- `message_submitted`

## Rules / Invariants

### Team ID format
- Generated server-side
- Exactly 6 characters
- Allowed alphabet: `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`
- Input normalization: `strip()` then `upper()`

### Participant join
- Allowed only when session status is `lobby`
- Allowed only when current participant count is `< 10` (capacity)
- Fails if `display_name` already exists in the session

### Starting a session
- Allowed only when session status is `lobby`
- Allowed only when participant count is `1..10`
- Allowed only when **all participants are ready**

### Messages
- Allowed only when session status is `running`

### Ending a session
- Transitions session to `ended`
- Once ended, session is locked (no re-start, no new joins, no new messages)

## Security

### Instructor auth
- JWT access token required for instructor HTTP endpoints
- JWT required for instructor WebSocket

### Participant auth
- Participant endpoints require a participant token returned by `/join`
- Token is **opaque** and stored server-side **only as a hash**:
  - `token_hash = HMAC-SHA256(token, PARTICIPANT_TOKEN_PEPPER)`
  - store `token_hash` as Postgres `BYTEA`
  - never store raw token
  - compare using constant-time equality
- Token valid until session ends, or explicit revoke

## Limits
- Max participants per session: 10
- Session start requires 1..10 participants
- Rate limiting / abuse protection is part of MVP implementation plan (later step)
