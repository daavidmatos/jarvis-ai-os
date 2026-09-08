from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, JSON, String, select
from sqlalchemy.orm import Mapped, mapped_column

from jarvis.db import Base, Database


class ProactiveEventRow(Base):
    __tablename__ = "proactive_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source: Mapped[str] = mapped_column(String(60), index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ProactiveEventService:
    """Persistent queue for events that may cause JARVIS to contact the user.

    Webhooks write here immediately. A future notifier/automation worker consumes
    pending events and decides whether to alert, speak, act, or remain silent.
    """

    def __init__(self, db: Database):
        self.db = db
        Base.metadata.create_all(self.db.engine)

    def emit(self, source: str, event_type: str, payload: dict) -> str:
        event_id = str(uuid4())
        with self.db.Session() as session:
            session.add(
                ProactiveEventRow(
                    id=event_id,
                    source=source,
                    event_type=event_type,
                    payload=payload,
                    status="pending",
                )
            )
            session.commit()
        self.db.audit(
            "proactive.event.created",
            {"event_id": event_id, "source": source, "event_type": event_type},
        )
        return event_id

    def list(self, status: str | None = None, limit: int = 100) -> list[dict]:
        with self.db.Session() as session:
            stmt = select(ProactiveEventRow).order_by(ProactiveEventRow.created_at.desc())
            if status:
                stmt = stmt.where(ProactiveEventRow.status == status)
            rows = session.scalars(stmt.limit(min(max(limit, 1), 500))).all()
        return [
            {
                "id": row.id,
                "source": row.source,
                "event_type": row.event_type,
                "status": row.status,
                "payload": row.payload,
                "created_at": row.created_at.isoformat(),
                "acknowledged_at": row.acknowledged_at.isoformat()
                if row.acknowledged_at
                else None,
            }
            for row in rows
        ]

    def acknowledge(self, event_id: str) -> bool:
        with self.db.Session() as session:
            row = session.get(ProactiveEventRow, event_id)
            if not row:
                return False
            row.status = "acknowledged"
            row.acknowledged_at = datetime.now(timezone.utc)
            session.commit()
        return True
