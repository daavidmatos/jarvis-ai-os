from pathlib import Path
from uuid import UUID
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from jarvis.schemas import ChatRequest, ChatResponse, ApprovalDecision, RiskLevel
from jarvis.orchestrator import Orchestrator

app=FastAPI(title="JARVIS AI OS",version="0.3.0",description="Autonomous multi-model personal AI orchestration system")
jarvis=Orchestrator()
web_dir=Path(__file__).resolve().parent.parent/"apps"/"web"
app.mount("/static",StaticFiles(directory=str(web_dir)),name="static")

@app.get("/")
def home(): return FileResponse(web_dir/"index.html")

@app.get("/health")
def health():
    return {"status":"ok","version":"0.3.0","primary_ai":"openai","primary_ai_ready":jarvis.router.providers["openai"].available,"autonomous_routing":True}

@app.post("/v1/chat",response_model=ChatResponse)
async def chat(req: ChatRequest):
    try:
        r=await jarvis.handle(req.message,req.session_id)
    except Exception as e:
        message=str(e)
        if "OPENAI_API_KEY" in message or "primary AI is not configured" in message:
            raise HTTPException(503,"JARVIS requires a one-time OpenAI API credential. After configuration, OpenAI is used automatically and model routing is autonomous.")
        raise
    return ChatResponse(**{k:r.get(k) for k in ChatResponse.model_fields})

@app.get("/v1/models")
def models(): return {"models":jarvis.router.catalog()}

@app.get("/v1/tools")
def tools(): return {"tools":jarvis.tools.list()}

@app.get("/v1/workflows/{workflow_id}")
def workflow(workflow_id: UUID):
    row=jarvis.db.get_workflow(workflow_id)
    if not row: raise HTTPException(404,"Workflow not found")
    row["tasks"]=jarvis.db.list_tasks(workflow_id)
    return row

@app.get("/v1/memory")
def memories(limit: int=50): return {"memories":jarvis.db.list_memories(min(max(limit,1),100))}

class MemoryCreate(BaseModel):
    content: str
    kind: str="semantic"
    importance: int=50

@app.post("/v1/memory")
def memory_create(req: MemoryCreate):
    mid=jarvis.memory.remember(req.content,req.kind,min(max(req.importance,0),100))
    return {"id":mid,"status":"created"}

@app.websocket("/ws/jarvis")
async def ws(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            data=await ws.receive_json(); msg=str(data.get("message","")).strip()
            if not msg:
                await ws.send_json({"type":"error","message":"message is required"}); continue
            await ws.send_json({"type":"status","status":"thinking"})
            result=await jarvis.handle(msg,None)
            await ws.send_json({"type":"result",**{k:(str(v) if k in {"workflow_id","session_id"} else v) for k,v in result.items()}})
    except WebSocketDisconnect:
        return

@app.get("/v1/approvals")
def approvals(status: str | None=None): return {"approvals":jarvis.db.list_approvals(status)}

@app.post("/v1/approvals/{approval_id}")
def decide_approval(approval_id: UUID,req:ApprovalDecision):
    row=jarvis.db.decide_approval(approval_id,req.approved)
    if not row: raise HTTPException(404,"Approval not found")
    return row

class ToolRun(BaseModel):
    args: dict = {}
    workflow_id: UUID | None = None
    approved: bool = False

@app.post("/v1/tools/{tool_name}/execute")
async def execute_tool(tool_name:str,req:ToolRun):
    tool=jarvis.tools.tools.get(tool_name)
    if not tool: raise HTTPException(404,"Tool not found")
    if tool.risk==RiskLevel.HIGH and not req.approved:
        if not req.workflow_id: raise HTTPException(400,"workflow_id is required for approval-gated tools")
        aid=jarvis.db.create_approval(req.workflow_id,tool_name,req.args)
        return {"ok":False,"approval_required":True,"approval_id":aid}
    return await jarvis.tools.execute(tool_name,approved=req.approved,**req.args)
