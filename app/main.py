from fastapi import FastAPI

from app.contracts import RuntimeRequest, RuntimeResponse
from app.db import init_db
from app.runtime import RuntimeOrchestrator

app = FastAPI(title="Constituency OS V0", version="0.1.0")
runtime = RuntimeOrchestrator()


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/runtime/dispatch", response_model=RuntimeResponse)
def dispatch_runtime(request: RuntimeRequest) -> RuntimeResponse:
    return runtime.dispatch(request)
