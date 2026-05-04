from fastapi import FastAPI

from app.admin_view import router as admin_router
from app.db import init_db
from app.telegram.webhook import router as telegram_router

app = FastAPI(title="Constituency OS V2", version="2.0.0")
app.include_router(admin_router)
app.include_router(telegram_router)


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
