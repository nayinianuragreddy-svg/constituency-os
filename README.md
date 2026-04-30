# Constituency OS V1 Runtime Scaffold

This repository now contains the **V0 runtime scaffold** plus a **V1 office loop** for one real complaint flow, and a **V1.5 Telegram live interface adapter**.

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

V1.5 adds a Telegram channel adapter layer while preserving core product logic in existing V1 flows:
- Shared `process_incoming_update(update)` message processing function
- Polling runner for local development
- Webhook-ready adapter reuse
- Update idempotency via `agent_actions.idempotency_key`

## V1 data model additions
- `citizens`
- `tickets`
- `ticket_updates`
- `officer_mappings`
- `officer_messages`
- `human_approvals`
- `agent_alerts`
- `citizen_conversations`
- `agent_actions` (idempotency for channel events)

All operational tables use `office_id` with default `1`.

## Quick start
```bash
docker compose up --build
```

API available at `http://localhost:8000`.

## Telegram bot setup (V1.5)
1. Create a bot via [@BotFather](https://t.me/BotFather) and copy the token.
2. Set the token in `.env`:
   ```env
   TELEGRAM_BOT_TOKEN=123456:your-real-token
   ```
3. Start local polling mode:
   ```bash
   python -m app.telegram_polling
   ```

### Missing token behavior
If `TELEGRAM_BOT_TOKEN` is missing, polling mode and webhook mode fail clearly with an explicit error message instead of failing unexpectedly.

### Local citizen flow test through adapter
Use `smoke_test_v15.py` to validate Telegram adapter behavior (processed once, duplicate skipped via idempotency key, and reply sent through Telegram sender abstraction).

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

### V1.5
- `POST /v1/telegram/webhook` (reuses shared Telegram update processor)

## Smoke tests
With dependencies installed:
```bash
python smoke_test_v0.py
python smoke_test_v1.py
python smoke_test_v15.py
python -m compileall app smoke_test_v0.py smoke_test_v1.py smoke_test_v15.py
```

`smoke_test_v1.py` demonstrates:
1. Citizen registration through DB-backed conversation state.
2. Electricity complaint ticket creation.
3. Department escalation dry-run send.
4. Master consuming department alert.
5. Officer reply simulation.
6. Human approval creation and approval.
7. Citizen update dry-run send and final ticket status progression.

`smoke_test_v15.py` demonstrates:
1. Telegram update processing through shared adapter logic.
2. Idempotent duplicate update skip using `telegram:update:{update_id}`.
3. Citizen reply generation routed through Telegram sender abstraction.


## V1.8 Intake Template
- Deterministic intake body for ~99 state flow and 14 category codes.
- Run migrations: `python scripts/run_v18_migrations.py`
- Seed baseline data: `python scripts/seed_v18.py`
- Run smoke tests:
  - `python smoke_test_v1.py`
  - `python smoke_test_v15.py`
  - `python smoke_test_v16a.py`
  - `python smoke_test_llm_spine.py`
  - `python smoke_test_v2_communication_brain.py`
  - `python smoke_test_v18_full_intake.py`
- V1.8 implements deterministic body; V1.9 will update LLM prompts for extraction.
