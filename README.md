# Constituency OS V0 Runtime Scaffold

This repository contains the **V0 runtime-first scaffold** for Constituency OS.

## Stack
- FastAPI
- PostgreSQL
- Redis
- Celery
- SQLAlchemy

## Runtime-first architecture
The runtime orchestrates stateless agents around explicit contracts:
- `CommunicationAgent`
- `DashboardAgent`
- `MasterAgent`

Data and behavior are separated:
- **Contracts** (`app/contracts.py`) define request/response schemas.
- **Agents** (`app/agents/`) remain stateless and pure.
- **Runtime** (`app/runtime.py`) composes agents and dispatches workflows.

## Quick start
```bash
docker compose up --build
```

API available at `http://localhost:8000`.

## Smoke test
With the API running:
```bash
python smoke_test_v0.py
```

## Endpoints
- `GET /health`
- `POST /runtime/dispatch`
