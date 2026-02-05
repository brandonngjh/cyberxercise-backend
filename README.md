# Cyberxercise Backend (MVP)

Backend API for **Cyberxercise**.

Tech stack:
- FastAPI (async)
- PostgreSQL (via Docker Compose)
- SQLAlchemy 2.0 async + asyncpg
- Alembic migrations
- JWT auth (instructors)
- Opaque participant tokens (stored as HMAC hash)
- WebSockets for realtime lobby/events
- Pytest

## Quickstart (local)

### 1) Prereqs
- Python 3.11+ recommended
- Docker Desktop (or Docker Engine)
- uv installed: https://docs.astral.sh/uv/

### 2) Environment
Copy the example env file and adjust as needed:

```bash
# from repo root
cp .env.example .env
```

Key variables:
- `DATABASE_URL` (async SQLAlchemy URL; default points at local dockerized Postgres)
- `JWT_SECRET` (dev secret)
- `PARTICIPANT_TOKEN_PEPPER` (pepper used for HMAC hashing of participant tokens)

### 3) Start Postgres

```bash
docker compose up -d
```

To verify Postgres is healthy:

```bash
docker compose ps
```

### 4) Install dependencies (uv)

Once `pyproject.toml` exists (added in the next implementation step), you’ll run:

```bash
uv venv
uv sync
```

### 5) Run migrations (Alembic)

Once Alembic is initialized (added in the next implementation step), you’ll run:

```bash
uv run alembic upgrade head
```

### 6) Run the API

Once the FastAPI app entrypoint exists (added in the next implementation step), you’ll run:

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

OpenAPI docs will be available at:
- http://localhost:8000/docs

## Documentation (contract-first)

- Requirements and rules: [docs/requirements.md](docs/requirements.md)
- Endpoint contract: [docs/api.md](docs/api.md)
- DB schema + ERD: [docs/data-model.md](docs/data-model.md)

## Notes
- This repo currently contains scaffolding + contract docs. Core implementation (models/migrations/auth/ws/tests) is added in subsequent steps.
