# Claude Code Development Guide for Vicoa

This document contains everything you need to know to work effectively on the Vicoa project.

## Project Overview

Vicoa is a platform that allows users to communicate with their AI agents (like you!) from anywhere. It uses the Model Context Protocol (MCP) to enable real-time communication between agents and users through a web dashboard.

## Quick Context

- **Purpose**: Let users see what their AI agents are doing and communicate with them in real-time
- **Key Innovation**: Agents can ask questions and receive feedback while working
- **Architecture**: Separate read (backend) and write (servers) operations for optimal performance
- **Open Source**: This is a community project - code quality and clarity matter!

## Project Structure

```
backend/
└── src/
    ├── backend/        # FastAPI - user-facing web dashboard API
    ├── servers/        # FastAPI + MCP + WebSocket - agent-facing server
    ├── shared/         # models, DB, config, auth, Alembic migrations, hooks
    ├── vicoa/          # the `vicoa` CLI and the local daemon
    ├── protocol/       # wire contracts shared by daemon and servers
    └── integrations/   # agent CLI wrappers (Claude Code, Codex, ACP, …)
```

## Key Technical Decisions

### Authentication Architecture
- **Two separate JWT systems**:
  1. **Backend**: Supabase JWTs for web users
  2. **Servers**: Custom JWT with weaker RSA (shorter API keys for agents)
- API keys are hashed (SHA256) before storage - never store raw tokens

### Database Design
- **PostgreSQL** with **SQLAlchemy 2.0+**
- **Alembic** for migrations - ALWAYS create migrations for schema changes
- Multi-tenant design - all data is scoped by user_id
- Key tables: users, user_agents, agent_instances, messages, api_keys
- **Unified messaging system**: All agent interactions (steps, questions, feedback) are now stored in the `messages` table with `sender_type` and `requires_user_input` fields

### Server Architecture
- **Unified server** (`servers/app.py`) supports both MCP and REST
- MCP endpoint: `/mcp/`
- REST endpoints: `/api/v1/*`
- Both use the same authentication and business logic

## Development Workflow

### Setting Up
1. **Always activate the virtual environment first**:
   ```bash
   source .venv/bin/activate  # macOS/Linux
   .venv\Scripts\activate     # Windows
   ```

2. **Install pre-commit hooks** (one-time):
   ```bash
   make pre-commit-install
   ```

### Before Making Changes
1. **Check current branch**: Ensure you're on the right branch
2. **Update dependencies**: Run `pip install -r requirements.txt` if needed
3. **Check migrations**: Run `alembic current` in `shared/` directory

### Making Changes

#### Database Changes
1. Modify models in `shared/models/`
2. Generate migration:
   ```bash
   cd shared/
   alembic revision --autogenerate -m "Descriptive message"
   ```
3. Review the generated migration file
4. Test migration: `alembic upgrade head`
5. Include migration file in your commit

#### Code Changes
1. **Follow existing patterns** - check similar files first
2. **Use type hints** - We use Python 3.12 with full type annotations
3. **Import style**: Prefer absolute imports from project root

#### Testing
```bash
make test              # Run all tests
make test-integration  # Integration tests (needs Docker)
```

### Before Committing
1. **Run linting and formatting**:
   ```bash
   make lint    # Check for issues
   make format  # Auto-fix formatting
   ```

2. **Verify your changes work**:
   - Test the specific functionality you changed
   - Run relevant test suites
   - Check that migrations apply cleanly

3. **Update documentation** if you changed functionality

## Common Tasks

### Working with Messages
The unified messaging system uses a single `messages` table:
- **Agent messages**: Set `sender_type=AGENT`, use `requires_user_input=True` for questions
- **User messages**: Set `sender_type=USER` for feedback/responses
- **Reading messages**: Use `last_read_message_id` to track reading progress
- **Queued messages**: Agent receives unread user messages when sending new messages

### Adding a New API Endpoint
1. Add route in `backend/api/` or `servers/fastapi_server/routers.py`
2. Create Pydantic models for request/response in `models.py`
3. Add database queries in appropriate query files
4. Write tests for the endpoint

### Adding a New MCP Tool
1. Add tool definition in `servers/mcp_server/tools.py`
2. Register tool in `servers/mcp_server/server.py`
3. Share logic with REST endpoint if applicable
4. Update agent documentation

### Modifying Database Schema
1. Change models in `shared/models/`
2. Generate and review migration
3. Update any affected queries
4. Update Pydantic models if needed
5. Test thoroughly with existing data

## Important Files to Know

- `shared/config.py` - Central configuration using Pydantic settings
- `shared/models/base.py` - SQLAlchemy base configuration
- `servers/app.py` - Unified server entry point
- `backend/auth/` - Authentication logic for web users
- `servers/api/auth.py` - Agent authentication

## Environment Variables

Key variables you might need:
- `DATABASE_URL` - PostgreSQL connection
- `JWT_PUBLIC_KEY` / `JWT_PRIVATE_KEY` - For agent auth
- `SUPABASE_URL` / `SUPABASE_ANON_KEY` - For web auth
- `ENVIRONMENT` - Set to "development" for auto-reload

## Common Pitfalls to Avoid

1. **Don't commit without migrations** - Pre-commit hooks will catch this
2. **Don't store raw JWT tokens** - Always hash API keys
3. **Don't mix authentication systems** - Backend uses Supabase, Servers use custom JWT
4. **Don't forget user scoping** - All queries must filter by user_id
5. **Don't skip type hints** - Pyright will complain
6. **If you add a `db.commit()` in `src/backend/api/` or `src/servers/api/`**, bump or add the file's entry in `scripts/websocket_freeze_baseline.json` in the same PR — CI's WebSocket freeze check fails otherwise.
7. **Don't introduce `CREATE TRIGGER` or `pg_notify` in new Alembic migrations** — same freeze check rejects them. Realtime fan-out is moving to the in-process `ConnectionManager`; only the migrations listed under `grandfathered_trigger_migrations` are allowed to retain them.
8. **Don't wrap `await websocket.close(...)` outside `_safe_close`** in `src/servers/api/ws_handler.py` — uvicorn's default `websockets-legacy` backend has a close-time `AttributeError` race (`'WebSocketProtocol' object has no attribute 'transfer_data_task'`) when the underlying TCP died early. Letting it propagate cascades through Starlette's exception handlers; under load this starves `accept()` and wedges the server. All close call sites must route through `_safe_close` so the exception is caught, logged, and reported to Sentry. The structural fix is to switch uvicorn to `wsproto`.

## Debugging Tips

1. **Database issues**: Check migrations are up to date
2. **Auth failures**: Verify JWT keys are properly formatted (with newlines)
3. **Import errors**: Ensure you're using absolute imports
4. **Type errors**: Run `make typecheck` to catch issues early

## Getting Help

- Check existing code for patterns
- Read test files for usage examples
- Error messages usually indicate what's wrong
- The codebase is well-structured - similar things are grouped together

## Your Superpowers on This Project

As Claude Code, you're particularly good at:
- Understanding the full codebase quickly
- Maintaining consistency across files
- Catching potential security issues
- Writing comprehensive tests
- Suggesting architectural improvements

Remember: This is an open-source project that helps AI agents communicate with humans. Your work here directly improves the AI-human collaboration experience!

# Repository Guidelines

## Project Structure & Module Organization
- `src/backend/` provides the FastAPI dashboard API; routers live in `api/`, auth flows in `auth/`, and database helpers in `db/`.
- `src/servers/` hosts the unified MCP + REST server (`app.py`) and related routers under `servers/api`.
- `src/shared/` centralizes configuration, SQLAlchemy models, Alembic migrations, and other cross-service utilities.
- `src/integrations/` keeps provider adapters; generated CLI wrappers under `cli_wrappers/codex` should stay untouched unless regenerated.
- Tests live in `src/backend/tests/`, `src/servers/tests/`, and root `tests/`; automation scripts land in `scripts/`.

## Build, Test, and Development Commands
- `./dev-start.sh` provisions Docker services, runs migrations, and starts APIs; `./dev-stop.sh` tears everything down.
- `make dev-install` plus `make pre-commit-install` bootstraps dependencies and Git hooks inside an activated virtualenv.
- `make lint` runs Ruff lint/format checks and Pyright; `make format` applies Ruff auto-fixes.
- `make test`, `make test-unit`, and `make test-integration` drive Pytest; `make test-k ARGS="pattern"` targets specific nodes.
- `make test-coverage` reports coverage across `src/backend`, `src/servers`, `src/vicoa`, and `src/shared`.

## Coding Style & Naming Conventions
- Target Python 3.11, 4-space indentation, explicit type hints, and snake_case for modules, functions, and package names.
- Let Ruff manage import order; prefer package-relative imports and share constants through `src/shared`.
- Run `make format` before commits; pre-commit enforces Ruff and Pyright, so keep the hook enabled.

## Testing Guidelines
- Pytest discovers `test_*.py` within the configured testpaths; mirror package layout when adding suites.
- Decorate long-running flows with `@pytest.mark.integration` so `make test-unit` remains quick.
- Extend fixtures in `tests/conftest.py`, prefer fakes for external calls, and use `make test-coverage` before requesting review.

## Commit & Pull Request Guidelines
- Follow Conventional Commits (`feat:`, `fix:`, `docs:`); keep subject lines imperative and under 72 characters.
- Branch names typically start with `feature/`, `bugfix/`, or `docs/` to match the patterns in `CONTRIBUTING.md`.
- Ensure `make lint` and relevant tests pass, mention schema or migration steps, and link issues or product specs in the PR body.
- Provide screenshots or curl snippets when API behavior changes and confirm secrets stay in `.env`, not commits.

## Environment & Configuration Tips
- Copy `.env.example` to `.env`, then generate JWT keys with `./scripts/generate-jwt-keys.sh`.
- When running services manually, export `PYTHONPATH="$(pwd)/src"` before `uvicorn backend.main:app --port 8000` or `python -m servers.app`.
