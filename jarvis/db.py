from __future__ import annotations
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import create_engine, String, Text, DateTime, Integer, JSON, ForeignKey, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from jarvis.config import settings

class Base(DeclarativeBase):
    pass

class SessionRow(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class MessageRow(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class WorkflowRow(Base):
    __tablename__ = "workflows"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), ForeignKey("sessions.id"), index=True)
    goal: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), index=True)
    plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class TaskRow(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String(36), ForeignKey("workflows.id"), index=True)
    task_key: Mapped[str] = mapped_column(String(64))
    agent: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(40), index=True)
    input: Mapped[dict] = mapped_column(JSON)
    output: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class MemoryRow(Base):
    __tablename__ = "memories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    content: Mapped[str] = mapped_column(Text)
    importance: Mapped[int] = mapped_column(Integer, default=50)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class ApprovalRow(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String(36), index=True)
    tool_name: Mapped[str] = mapped_column(String(120))
    payload: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class AuditRow(Base):
    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workflow_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    event: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

class Database:
    def __init__(self, url: str | None = None):
        self.url = url or settings.database_url
        kwargs = {"connect_args": {"check_same_thread": False}} if self.url.startswith("sqlite") else {}
        self.engine = create_engine(self.url, future=True, pool_pre_ping=True, **kwargs)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False)

    def init(self):
        Base.metadata.create_all(self.engine)

    def create_session(self, session_id: UUID | None = None) -> UUID:
        sid = session_id or uuid4()
        with self.Session() as db:
            if not db.get(SessionRow, str(sid)):
                db.add(SessionRow(id=str(sid)))
                db.commit()
        return sid

    def add_message(self, session_id: UUID, role: str, content: str):
        with self.Session() as db:
            db.add(MessageRow(id=str(uuid4()), session_id=str(session_id), role=role, content=content))
            db.commit()

    def recent_messages(self, session_id: UUID, limit: int = 12) -> list[dict]:
        with self.Session() as db:
            rows = db.scalars(select(MessageRow).where(MessageRow.session_id == str(session_id)).order_by(MessageRow.created_at.desc()).limit(limit)).all()
        rows = list(reversed(rows))
        return [{"role": r.role, "content": r.content} for r in rows]

    def create_workflow(self, session_id: UUID, goal: str, plan: dict) -> UUID:
        wid = uuid4()
        with self.Session() as db:
            db.add(WorkflowRow(id=str(wid), session_id=str(session_id), goal=goal, status="running", plan=plan))
            db.commit()
        return wid

    def create_task(self, workflow_id: UUID, task_key: str, agent: str, input_data: dict) -> UUID:
        tid = uuid4()
        with self.Session() as db:
            db.add(TaskRow(id=str(tid), workflow_id=str(workflow_id), task_key=task_key, agent=agent, status="pending", input=input_data))
            db.commit()
        return tid

    def update_task(self, task_id: UUID, status: str, output: dict | None = None, retry_count: int | None = None):
        with self.Session() as db:
            row = db.get(TaskRow, str(task_id))
            if not row: return
            row.status = status
            if output is not None: row.output = output
            if retry_count is not None: row.retry_count = retry_count
            db.commit()

    def finish_workflow(self, workflow_id: UUID, status: str, output: dict):
        with self.Session() as db:
            row = db.get(WorkflowRow, str(workflow_id))
            if not row: return
            row.status = status
            row.output = output
            row.completed_at = datetime.now(timezone.utc)
            db.commit()

    def list_tasks(self, workflow_id: UUID) -> list[dict]:
        with self.Session() as db:
            rows = db.scalars(select(TaskRow).where(TaskRow.workflow_id == str(workflow_id)).order_by(TaskRow.created_at)).all()
        return [{"id": r.id, "task_key": r.task_key, "agent": r.agent, "status": r.status, "input": r.input, "output": r.output, "retry_count": r.retry_count} for r in rows]

    def get_workflow(self, workflow_id: UUID) -> dict | None:
        with self.Session() as db:
            r = db.get(WorkflowRow, str(workflow_id))
            if not r: return None
            return {"id": r.id, "session_id": r.session_id, "goal": r.goal, "status": r.status, "plan": r.plan, "output": r.output, "created_at": r.created_at.isoformat()}

    def add_memory(self, kind: str, content: str, importance: int = 50) -> UUID:
        mid = uuid4()
        with self.Session() as db:
            db.add(MemoryRow(id=str(mid), kind=kind, content=content, importance=importance))
            db.commit()
        return mid

    def search_memories(self, query: str, limit: int = 6) -> list[dict]:
        tokens = {t.lower() for t in query.split() if len(t) > 3}
        with self.Session() as db:
            rows = db.scalars(select(MemoryRow).order_by(MemoryRow.importance.desc(), MemoryRow.created_at.desc()).limit(100)).all()
        scored = []
        for r in rows:
            text = r.content.lower()
            score = sum(1 for t in tokens if t in text)
            if score or not tokens:
                scored.append((score, r.importance, r))
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [{"id": r.id, "kind": r.kind, "content": r.content, "importance": r.importance} for _,_,r in scored[:limit]]

    def list_memories(self, limit: int = 50) -> list[dict]:
        with self.Session() as db:
            rows = db.scalars(select(MemoryRow).order_by(MemoryRow.created_at.desc()).limit(limit)).all()
        return [{"id": r.id, "kind": r.kind, "content": r.content, "importance": r.importance} for r in rows]

    def create_approval(self, workflow_id: UUID, tool_name: str, payload: dict) -> UUID:
        aid=uuid4()
        with self.Session() as db:
            db.add(ApprovalRow(id=str(aid), workflow_id=str(workflow_id), tool_name=tool_name, payload=payload, status="pending"))
            db.commit()
        return aid

    def list_approvals(self, status: str | None=None) -> list[dict]:
        with self.Session() as db:
            stmt=select(ApprovalRow).order_by(ApprovalRow.created_at.desc())
            if status: stmt=stmt.where(ApprovalRow.status==status)
            rows=db.scalars(stmt).all()
        return [{"id":r.id,"workflow_id":r.workflow_id,"tool_name":r.tool_name,"payload":r.payload,"status":r.status,"created_at":r.created_at.isoformat()} for r in rows]

    def decide_approval(self, approval_id: UUID, approved: bool) -> dict | None:
        with self.Session() as db:
            r=db.get(ApprovalRow,str(approval_id))
            if not r: return None
            r.status="approved" if approved else "rejected"
            db.commit()
            return {"id":r.id,"status":r.status,"tool_name":r.tool_name,"payload":r.payload}

    def audit(self, event: str, payload: dict, workflow_id: UUID | None = None):
        with self.Session() as db:
            db.add(AuditRow(id=str(uuid4()), workflow_id=str(workflow_id) if workflow_id else None, event=event, payload=payload))
            db.commit()
