from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import ModuleType


_LEGACY_MODULE: ModuleType | None = None


def _load_legacy_module() -> ModuleType:
    global _LEGACY_MODULE
    if _LEGACY_MODULE is not None:
        return _LEGACY_MODULE

    legacy_path = Path(__file__).resolve().parent.parent / "communication.py"
    spec = spec_from_file_location("app.agents._legacy_communication", legacy_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load legacy CommunicationAgent from {legacy_path}")

    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    _LEGACY_MODULE = module
    return module


CommunicationAgent = _load_legacy_module().CommunicationAgent


def handle_citizen_message(db, telegram_chat_id: str, text: str) -> str:
    agent = CommunicationAgent(name="communication_agent")
    return agent.handle_citizen_message(db=db, telegram_chat_id=telegram_chat_id, text=text)
