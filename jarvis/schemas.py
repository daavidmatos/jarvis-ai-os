from enum import Enum
from typing import Any, Literal
from uuid import UUID, uuid4
from pydantic import BaseModel, Field

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class TaskStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    APPROVAL_REQUIRED = "approval_required"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class LocationContext(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy_m: float | None = Field(default=None, ge=0)

class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: UUID | None = None
    # Ephemeral device location supplied only for the current request. The core
    # does not write this into long-term memory.
    location: LocationContext | None = None

class ChatResponse(BaseModel):
    workflow_id: UUID
    session_id: UUID
    status: TaskStatus
    message: str
    provider: str | None = None
    model: str | None = None
    actions: list[dict[str, Any]] = Field(default_factory=list)
    # Optional visual state for interactive/collaborative work such as Google Ads.
    workspace: dict[str, Any] | None = None

class PlanTask(BaseModel):
    id: str
    agent: Literal["research", "coding", "creative", "data", "operations", "general"] = "general"
    action: str
    instruction: str
    dependencies: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=lambda: ["text"])

class ExecutionPlan(BaseModel):
    goal: str
    tasks: list[PlanTask]

class AgentResult(BaseModel):
    ok: bool
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[str] = Field(default_factory=list)

class ToolSpec(BaseModel):
    name: str
    description: str
    risk: RiskLevel
    requires_approval: bool = False

class ApprovalDecision(BaseModel):
    approved: bool
