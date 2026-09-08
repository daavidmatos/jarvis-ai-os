from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from jarvis.config import settings
from jarvis.orchestrator import Orchestrator
from jarvis.router import PrimaryAIUnavailable
from jarvis.schemas import ApprovalDecision, ChatRequest, ChatResponse, RiskLevel
from jarvis.setup import setup_service


app = FastAPI(
    title="JARVIS AI OS",
    version="0.3.0",
    description="OpenAI-first autonomous personal AI orchestration system",
)
jarvis = Orchestrator()
web_dir = Path(__file__).resolve().parent.parent / "apps" / "web"
app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")


@app.get("/")
def home():
    return FileResponse(web_dir / "index.html")


def setup_status_payload():
    catalog = jarvis.router.catalog()
    primary = next((m for m in catalog if m["primary"]), None)
    specialists = [m for m in catalog if m["role"] == "specialist"]
    return {
        "ready": bool(primary and primary["available"]),
        "version": "0.3.0",
        "primary": primary,
        "specialists": specialists,
        "autonomous_routing": settings.autonomous_routing,
        "autonomy_enabled": True,
        "autonomy_scope": "low_and_medium_risk_tools",
    }


@app.get("/health")
def health():
    status = setup_status_payload()
    return {
        "status": "ok",
        "version": "0.3.0",
        "ready": status["ready"],
        "primary_provider": "openai",
    }


@app.get("/v1/setup/status")
def setup_status():
    return setup_status_payload()


class ProviderCredential(BaseModel):
    api_key: str = Field(min_length=20)


@app.post("/v1/setup/providers/{provider}")
async def configure_provider(provider: str, req: ProviderCredential):
    provider = provider.lower().strip()
    try:
        result = await setup_service.configure(provider, req.api_key)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    result["status"] = setup_status_payload()
    return result


@app.delete("/v1/setup/providers/{provider}")
def disconnect_provider(provider: str):
    provider = provider.lower().strip()
    try:
        result = setup_service.disconnect(provider)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    result["status"] = setup_status_payload()
    return result


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    try:
        r = await jarvis.handle(req.message, req.session_id)
    except PrimaryAIUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "setup_required",
                "message": str(exc),
                "primary_provider": "openai",
            },
        ) from None
    return ChatResponse(**{k: r.get(k) for k in ChatResponse.model_fields})


@app.get("/v1/models")
def models():
    return {"models": jarvis.router.catalog()}


@app.get("/v1/tools")
def tools():
    return {"tools": jarvis.tools.list()}


@app.get("/v1/workflows/{workflow_id}")
def workflow(workflow_id: UUID):
    row = jarvis.db.get_workflow(workflow_id)
    if not row:
        raise HTTPException(404, "Workflow not found")
    row["tasks"] = jarvis.db.list_tasks(workflow_id)
    return row


@app.get("/v1/memory")
def memories(limit: int = 50):
    return {"memories": jarvis.db.list_memories(min(max(limit, 1), 100))}


class MemoryCreate(BaseModel):
    content: str
    kind: str = "semantic"
    importance: int = 50


@app.post("/v1/memory")
def memory_create(req: MemoryCreate):
    mid = jarvis.memory.remember(
        req.content, req.kind, min(max(req.importance, 0), 100)
    )
    return {"id": mid, "status": "created"}


@app.websocket("/ws/jarvis")
async def ws(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            data = await ws.receive_json()
            msg = str(data.get("message", "")).strip()
            if not msg:
                await ws.send_json({"type": "error", "message": "message is required"})
                continue
            await ws.send_json({"type": "status", "status": "thinking"})
            try:
                result = await jarvis.handle(msg, None)
            except PrimaryAIUnavailable as exc:
                await ws.send_json(
                    {
                        "type": "setup_required",
                        "message": str(exc),
                        "primary_provider": "openai",
                    }
                )
                continue
            await ws.send_json(
                {
                    "type": "result",
                    **{
                        k: (
                            str(v)
                            if k in {"workflow_id", "session_id"}
                            else v
                        )
                        for k, v in result.items()
                    },
                }
            )
    except WebSocketDisconnect:
        return


@app.get("/v1/approvals")
def approvals(status: str | None = None):
    return {"approvals": jarvis.db.list_approvals(status)}


@app.post("/v1/approvals/{approval_id}")
def decide_approval(approval_id: UUID, req: ApprovalDecision):
    row = jarvis.db.decide_approval(approval_id, req.approved)
    if not row:
        raise HTTPException(404, "Approval not found")
    return row


class ToolRun(BaseModel):
    args: dict = {}
    workflow_id: UUID | None = None
    approved: bool = False


@app.post("/v1/tools/{tool_name}/execute")
async def execute_tool(tool_name: str, req: ToolRun):
    tool = jarvis.tools.tools.get(tool_name)
    if not tool:
        raise HTTPException(404, "Tool not found")
    if tool.risk == RiskLevel.HIGH and not req.approved:
        if not req.workflow_id:
            raise HTTPException(
                400, "workflow_id is required for approval-gated tools"
            )
        aid = jarvis.db.create_approval(req.workflow_id, tool_name, req.args)
        return {"ok": False, "approval_required": True, "approval_id": aid}
    return await jarvis.tools.execute(
        tool_name, approved=req.approved, **req.args
    )
