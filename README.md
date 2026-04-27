# Constituency OS V1 Runtime Scaffold

This repository now contains the **V0 runtime scaffold** plus a **V1 office loop** for one real complaint flow:

`Public Issue -> Electricity -> Streetlight / Power cut / Transformer fault / Other`

## Stack
- FastAPI
- PostgreSQL (or SQLite for local smoke test)
- Redis
- Celery
- SQLAlchemy

## Runtime-first architecture (unchanged)
The runtime still orchestrates stateless agents around explicit contracts:
- `CommunicationAgent`
- `DashboardAgent`
- `MasterAgent`

V1 extends this with office-loop components while keeping agents stateless and using DB/tool layers:
- `DepartmentCoordinationAgent`
- DB-backed citizen conversation state
- Master alert queue polling (`agent_alerts`)
- Dry-run tool gateway for department/citizen sends

## V1 data model additions
- `citizens`
- `tickets`
- `ticket_updates`
- `officer_mappings`
- `officer_messages`
- `human_approvals`
- `agent_alerts`
- `citizen_conversations`

All operational tables use `office_id` with default `1`.

## Quick start
```bash
docker compose up --build
```

API available at `http://localhost:8000`.

## Endpoints
### V0
- `GET /health`
- `POST /runtime/dispatch`

### V1
- `POST /v1/citizen/message`
- `POST /v1/department/process`
- `POST /v1/officer/reply`
- `POST /v1/human-approvals/{approval_id}/approve`
- `POST /v1/master/consume`

## Smoke tests
With dependencies installed:
```bash
python smoke_test_v0.py
python smoke_test_v1.py
python -m compileall app smoke_test_v0.py smoke_test_v1.py
```

`smoke_test_v1.py` demonstrates:
1. Citizen registration through DB-backed conversation state.
2. Electricity complaint ticket creation.
3. Department escalation dry-run send.
4. Master consuming department alert.
5. Officer reply simulation.
6. Human approval creation and approval.
7. Citizen update dry-run send and final ticket status progression.
