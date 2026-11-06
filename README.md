# API COMPASS

**AI-powered API exploration, integration, and testing workbench.**

Upload an OpenAPI specification and explore it through a deterministic endpoint explorer, a grounded AI assistant (RAG over the spec), natural-language request generation, and a built-in mock execution and testing engine.

> Status: **Phase 3 (API explorer) complete.** See [Roadmap](#roadmap).

## Architecture

```text
Next.js (React, TS, Tailwind, shadcn/ui, TanStack Query)
        │  REST /api/v1
        ▼
FastAPI (Pydantic, SQLAlchemy async, structlog)
        │
        ▼
PostgreSQL + pgvector  (Supabase in production, Docker locally)
```

| Path | What it is |
|---|---|
| `frontend/` | Next.js 16 app router, TypeScript strict mode |
| `backend/app/core/` | Settings (env-based), structured logging, centralized error envelope |
| `backend/app/db/` | Async SQLAlchemy engine/session, declarative base |
| `backend/app/api/v1/` | Versioned REST routes |
| `backend/app/services/` | OpenAPI parser: safe loading, validation, and extraction of operations and schemas |
| `backend/alembic/` | Database migrations, including row-level security policies |
| `samples/` | The bundled Bookstore API specification |
| `docker-compose.yml` | Local Postgres+pgvector, backend, frontend |
| `.github/workflows/ci.yml` | Lint, type-check, migrate, test, build |

All error responses share one shape:

```json
{ "error": { "code": "not_found", "message": "Not Found", "details": null } }
```

## Local development

### Option A: Docker (recommended)

```bash
docker compose up --build
```

- Frontend: http://localhost:3000
- API: http://localhost:8000/api/v1/health
- API docs: http://localhost:8000/api/v1/docs

Migrations run automatically on backend start.

### Option B: Run services directly

Requires Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 22+, and a Postgres 15+ server with the pgvector extension available.

```bash
# Backend
cd backend
cp .env.example .env          # set DATABASE_URL
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000

# Frontend (second terminal)
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Without a reachable database the API still starts. `/api/v1/health` then returns `503` with `"database": "unavailable"`, and the dashboard shows this state.

### Using Supabase instead of local Postgres

1. Create a Supabase project. pgvector ships with Supabase; migration `0001` enables it.
2. Copy the connection string (Project Settings → Database) into `backend/.env` as `DATABASE_URL`. `postgres://` URLs are converted to the asyncpg driver automatically.
3. Run `uv run alembic upgrade head`.

## Checks

```bash
cd backend  && uv run ruff check . && uv run ruff format --check . && uv run mypy app tests && uv run pytest
cd frontend && npm run lint && npm run typecheck && npm run build
```

The database integration test is skipped locally when no Postgres is reachable. CI sets `REQUIRE_DB=1` so it can't be skipped there.

## Environment variables

| Variable | Where | Purpose |
|---|---|---|
| `DATABASE_URL` | backend | Postgres connection string |
| `CORS_ORIGINS` | backend | Comma-separated allowed browser origins |
| `ENVIRONMENT`, `LOG_LEVEL`, `LOG_JSON` | backend | Runtime/logging config |
| `SUPABASE_URL` | backend | Fetches the public keys that verify access tokens |
| `NEXT_PUBLIC_API_URL` | frontend | Backend base URL |
| `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | frontend | Supabase Auth in the browser |

Secrets live only in untracked `.env` files. `.env.example` files document the keys.

## Roadmap

- [x] **Phase 0:** Project setup (frontend, backend, Docker, migrations, health check, CI)
- [x] **Phase 1:** Authentication and projects
- [x] **Phase 2:** OpenAPI parser (JSON/YAML upload, validation, operation and schema extraction, import status)
- [x] **Phase 3:** API explorer (endpoint sidebar, search and method filters, endpoint details, schema viewer, authentication details)
- [ ] Phase 4: RAG pipeline
- [ ] Phase 5: AI assistant
- [ ] Phase 6: Request builder
- [ ] Phase 7: Mock execution and testing
- [ ] Phase 8: Polish and evaluation
- [ ] Phase 9: Deployment
