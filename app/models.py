from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class RuntimeEvent(Base):
    __tablename__ = "runtime_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    actor: Mapped[str] = mapped_column(String(128), index=True)
    message: Mapped[str] = mapped_column(String(1000))
    created_at: Mapped[str] = mapped_column(DateTime(timezone=True), server_default=func.now())
