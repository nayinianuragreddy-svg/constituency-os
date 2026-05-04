import asyncio
import os

import sqlalchemy as sa
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.admin_view import router as admin_router
from app.db import engine, init_db
from app.telegram.webhook import router as telegram_router

app = FastAPI(title="Constituency OS V2", version="2.0.0")
app.include_router(admin_router)
app.include_router(telegram_router)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
async def health():
    checks = {}
    overall_ok = True

    # DB check (2s timeout)
    try:
        await asyncio.wait_for(_check_db(), timeout=2.0)
        checks["db"] = "ok"
    except Exception as exc:
        checks["db"] = f"down: {str(exc)[:100]}"
        overall_ok = False

    # Redis check (2s timeout, failures do NOT cause 503 — degraded mode acceptable)
    try:
        await asyncio.wait_for(_check_redis(), timeout=2.0)
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"down: {str(exc)[:100]}"

    # OpenAI check (2s timeout)
    try:
        await asyncio.wait_for(_check_openai(), timeout=2.0)
        checks["openai"] = "ok"
    except Exception as exc:
        checks["openai"] = f"down: {str(exc)[:100]}"
        overall_ok = False

    status_code = 200 if overall_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={"status": "ok" if overall_ok else "degraded", "checks": checks},
    )


async def _check_db():
    with engine.connect() as conn:
        conn.execute(sa.text("SELECT 1"))


async def _check_redis():
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        raise Exception("env var unset")
    import redis as redis_lib
    r = redis_lib.Redis.from_url(redis_url, socket_connect_timeout=1)
    r.ping()


async def _check_openai():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise Exception("env var unset")
    import httpx
    async with httpx.AsyncClient(timeout=2.0) as client:
        response = await client.get(
            "https://api.openai.com/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
        if response.status_code not in (200, 401, 403):
            raise Exception(f"unexpected status {response.status_code}")
