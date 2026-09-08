import asyncio
import base64
import json
import secrets
from dataclasses import asdict
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from jarvis.config import settings
from jarvis.desktop_bridge import desktop_bridge
from jarvis.events import ProactiveEventService
from jarvis.google_workspace import GoogleWorkspaceError, google_workspace
from jarvis.integrations.fuel import fuel_business
from jarvis.integrations.google_ads import google_ads
from jarvis.integrations.meta import instagram
from jarvis.local_assistant import google_places
from jarvis.missions import MissionStatus, mission_store
from jarvis.monitoring import GoogleMonitoringService
from jarvis.orchestrator_universal import UniversalOrchestrator as Orchestrator
from jarvis.permissions import standing_permissions
from jarvis.router import PrimaryAIUnavailable
from jarvis.schemas import ApprovalDecision, ChatRequest, ChatResponse, RiskLevel
from jarvis.setup import setup_service


app = FastAPI(
    title="JARVIS AI OS",
    version="0.7.0",
    description="OpenAI-first autonomous and collaborative personal AI operating system",
)
jarvis = Orchestrator()
events = ProactiveEventService(jarvis.db)
google_monitor = GoogleMonitoringService(events)
web_dir = Path(__file__).resolve().parent.parent / "apps" / "web"
app.mount("/static", StaticFiles(directory=str(web_dir)), name="static")


@app.on_event("startup")
async def start_background_services():
    google_monitor.start()


@app.get("/")
def home():
    return FileResponse(web_dir / "index.html")


def setup_status_payload():
    catalog = jarvis.router.catalog()
    primary = next((m for m in catalog if m["primary"]), None)
    specialists = [m for m in catalog if m["role"] == "specialist"]
    return {
        "ready": bool(primary and primary["available"]),
        "version": "0.7.0",
        "primary": primary,
        "specialists": specialists,
        "autonomous_routing": settings.autonomous_routing,
        "autonomy_enabled": settings.enable_autonomy,
        "autonomy_scope": "mission_envelopes_plus_collaborative_workspaces",
        "google_workspace": google_workspace.status(),
        "places": google_places.status(),
        "instagram": instagram.status(),
        "google_ads": google_ads.status(),
        "fuel": fuel_business.status(),
        "desktop_bridge": desktop_bridge.status(),
        "collaboration": {
            "mode": "universal_workbench",
            "catalog": jarvis.collaboration.capability_catalog(),
        },
    }


@app.get("/health")
def health():
    status = setup_status_payload()
    return {
        "status": "ok",
        "version": "0.7.0",
        "ready": status["ready"],
        "primary_provider": "openai",
        "google_connected": status["google_workspace"]["connected"],
        "places_configured": status["places"]["configured"],
        "desktop_bridge_connected": status["desktop_bridge"]["connected"],
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


# ---------------------------------------------------------------------------
# Google Workspace OAuth + monitoring
# ---------------------------------------------------------------------------


@app.get("/v1/integrations/google/status")
def google_status():
    return google_workspace.status()


@app.get("/v1/integrations/places/status")
def places_status():
    return google_places.status()


@app.get("/v1/integrations/google/connect")
def google_connect():
    try:
        return RedirectResponse(google_workspace.authorization_url(), status_code=302)
    except GoogleWorkspaceError as exc:
        raise HTTPException(503, str(exc)) from None


@app.get("/v1/integrations/google/callback")
async def google_callback(code: str, state: str):
    try:
        status = await google_workspace.exchange_code(code, state)
    except GoogleWorkspaceError as exc:
        raise HTTPException(400, str(exc)) from None
    return HTMLResponse(
        "<html><body style='font-family:system-ui;background:#061019;color:white;padding:40px'>"
        "<h2>Google conectado ao JARVIS.</h2>"
        "<p>Gmail, Calendar e os escopos Google autorizados já podem ser usados.</p>"
        "<p><a style='color:#7ee8ff' href='/'>Voltar ao JARVIS</a></p>"
        f"<small>Connected: {status['connected']}</small>"
        "</body></html>"
    )


@app.delete("/v1/integrations/google")
def google_disconnect():
    return {"disconnected": google_workspace.disconnect()}


@app.post("/v1/integrations/google/monitor/start")
async def google_monitor_start():
    try:
        return await google_monitor.ensure_watches()
    except GoogleWorkspaceError as exc:
        raise HTTPException(400, str(exc)) from None


@app.post("/v1/webhooks/google/gmail")
async def google_gmail_webhook(request: Request, token: str | None = None):
    expected = settings.google_pubsub_webhook_secret
    if expected and (not token or not secrets.compare_digest(token, expected)):
        raise HTTPException(403, "Invalid Pub/Sub webhook token")
    try:
        body = await request.json()
        encoded = body.get("message", {}).get("data")
        if not encoded:
            raise ValueError("missing message.data")
        padding = "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(encoded + padding).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(400, f"Invalid Gmail Pub/Sub payload: {exc}") from None
    event_id = events.emit("gmail", "mailbox.changed", payload)
    return {"ok": True, "event_id": event_id}


@app.post("/v1/webhooks/google/calendar")
async def google_calendar_webhook(request: Request):
    channel_id = request.headers.get("x-goog-channel-id")
    channel_token = request.headers.get("x-goog-channel-token")
    resource_id = request.headers.get("x-goog-resource-id")
    resource_state = request.headers.get("x-goog-resource-state")
    message_number = request.headers.get("x-goog-message-number")
    if not google_workspace.validate_calendar_webhook(channel_id, channel_token):
        raise HTTPException(403, "Invalid Google Calendar channel")
    if resource_state == "sync":
        return {"ok": True, "sync": True}
    event_id = events.emit(
        "calendar",
        "calendar.changed",
        {
            "channel_id": channel_id,
            "resource_id": resource_id,
            "resource_state": resource_state,
            "message_number": message_number,
        },
    )
    return {"ok": True, "event_id": event_id}


# ---------------------------------------------------------------------------
# Meta / Instagram + Fuel event ingress
# ---------------------------------------------------------------------------


@app.get("/v1/integrations/status")
def integrations_status():
    return {
        "google_workspace": google_workspace.status(),
        "places": google_places.status(),
        "google_ads": google_ads.status(),
        "instagram": instagram.status(),
        "fuel": fuel_business.status(),
        "desktop_bridge": desktop_bridge.status(),
    }


@app.get("/v1/webhooks/meta/instagram")
def meta_webhook_verify(
    mode: str | None = Query(default=None, alias="hub.mode"),
    verify_token: str | None = Query(default=None, alias="hub.verify_token"),
    challenge: str | None = Query(default=None, alias="hub.challenge"),
):
    expected = settings.meta_webhook_verify_token
    if mode == "subscribe" and expected and verify_token and secrets.compare_digest(verify_token, expected):
        return PlainTextResponse(challenge or "")
    raise HTTPException(403, "Meta webhook verification failed")


@app.post("/v1/webhooks/meta/instagram")
async def meta_instagram_webhook(request: Request):
    body = await request.body()
    if not instagram.verify_signature(body, request.headers.get("x-hub-signature-256")):
        raise HTTPException(403, "Invalid Meta webhook signature")
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(400, f"Invalid Meta webhook payload: {exc}") from None
    event_id = events.emit("instagram", "instagram.changed", payload)
    return {"ok": True, "event_id": event_id}


@app.post("/v1/webhooks/fuel")
async def fuel_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("x-jarvis-signature") or request.headers.get("x-signature")
    if not fuel_business.verify_webhook(body, signature):
        raise HTTPException(403, "Invalid Fuel webhook signature")
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(400, f"Invalid Fuel webhook payload: {exc}") from None
    event_type = str(payload.get("type") or "business.changed")
    event_id = events.emit("fuel", event_type, payload)
    return {"ok": True, "event_id": event_id}


@app.get("/v1/events")
def proactive_events(status: str | None = None, limit: int = 100):
    return {"events": events.list(status=status, limit=limit)}


@app.post("/v1/events/{event_id}/ack")
def acknowledge_event(event_id: str):
    if not events.acknowledge(event_id):
        raise HTTPException(404, "Event not found")
    return {"id": event_id, "status": "acknowledged"}


# ---------------------------------------------------------------------------
# Universal collaborative workspaces + desktop bridge
# ---------------------------------------------------------------------------


@app.get("/v1/workspaces")
def workspaces():
    return {
        "workspaces": jarvis.collaboration.list_workspaces(),
        "catalog": jarvis.collaboration.capability_catalog(),
    }


@app.get("/v1/workspaces/{session_id}")
def workspace_get(session_id: str):
    workspace = jarvis.collaboration.get_workspace(session_id)
    if not workspace:
        raise HTTPException(404, "Workspace not found")
    return {"workspace": workspace}


@app.get("/v1/desktop/status")
def desktop_status():
    return desktop_bridge.status()


@app.websocket("/ws/desktop-bridge")
async def desktop_bridge_ws(ws: WebSocket, token: str | None = None):
    expected = settings.desktop_bridge_token
    if expected and (not token or not secrets.compare_digest(token, expected)):
        await ws.close(code=4403)
        return
    if settings.app_env != "development" and not expected:
        # Never expose unauthenticated computer-control transport in hosted mode.
        await ws.close(code=4403)
        return

    await ws.accept()
    client_id: str | None = None
    try:
        hello = await asyncio.wait_for(ws.receive_json(), timeout=10)
        if hello.get("type") != "hello" or not hello.get("client_id"):
            await ws.send_json({"type": "error", "message": "hello with client_id is required"})
            await ws.close(code=4400)
            return
        client_id = str(hello["client_id"])
        client = desktop_bridge.register(
            client_id,
            str(hello.get("platform") or "unknown"),
            apps=[str(x) for x in hello.get("apps", [])],
            active_app=hello.get("active_app"),
            active_document=hello.get("active_document"),
            state=hello.get("state") if isinstance(hello.get("state"), dict) else {},
        )
        await ws.send_json({"type": "hello_ack", "client_id": client.client_id})

        while True:
            try:
                data = await asyncio.wait_for(ws.receive_json(), timeout=0.75)
                kind = str(data.get("type") or "")
                if kind == "state":
                    desktop_bridge.update_state(client_id, data)
                    await ws.send_json({"type": "state_ack"})
                elif kind == "frame":
                    desktop_bridge.update_frame(client_id, data)
                    await ws.send_json({"type": "frame_ack", "frame_id": data.get("frame_id")})
                elif kind == "result":
                    if isinstance(data.get("state"), dict):
                        desktop_bridge.update_state(client_id, data)
                    await ws.send_json({"type": "result_ack", "command_id": data.get("command_id")})
                elif kind == "ping":
                    await ws.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                pass

            command = await desktop_bridge.next_command(client_id, timeout=0.01)
            if command:
                await ws.send_json(command)
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    finally:
        if client_id:
            desktop_bridge.disconnect(client_id)


# ---------------------------------------------------------------------------
# Autonomous missions + standing permissions
# ---------------------------------------------------------------------------


class MissionProposalRequest(BaseModel):
    objective: str = Field(min_length=3)
    session_id: UUID | None = None


@app.get("/v1/missions")
def missions():
    return {"missions": [asdict(m) for m in mission_store.list()]}


@app.get("/v1/missions/{mission_id}")
def mission_get(mission_id: str):
    mission = mission_store.get(mission_id)
    if not mission:
        raise HTTPException(404, "Mission not found")
    return asdict(mission)


@app.post("/v1/missions/propose")
async def mission_propose(req: MissionProposalRequest):
    sid = jarvis.db.create_session(req.session_id)
    context = (
        f"Memory:\n{jarvis.memory.context_text(req.objective) or '(none)'}\n\n"
        f"Standing permissions:\n{standing_permissions.context_text()}"
    )
    try:
        result = await jarvis.mission_director.propose(
            req.objective, context, session_id=str(sid)
        )
    except PrimaryAIUnavailable as exc:
        raise HTTPException(503, str(exc)) from None
    return {
        "mission": asdict(result["mission"]),
        "approval_summary": result["approval_summary"],
        "provider": result["provider"],
        "model": result["model"],
    }


@app.post("/v1/missions/{mission_id}/approve")
def mission_approve(mission_id: str):
    try:
        return asdict(mission_store.approve(mission_id))
    except KeyError:
        raise HTTPException(404, "Mission not found") from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None


@app.post("/v1/missions/{mission_id}/execute")
async def mission_execute(mission_id: str):
    try:
        result = await jarvis.mission_executor.execute(mission_id)
    except KeyError:
        raise HTTPException(404, "Mission not found") from None
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from None
    mission = result.get("mission")
    return {
        **{k: v for k, v in result.items() if k != "mission"},
        "mission": asdict(mission) if mission else None,
    }


@app.post("/v1/missions/{mission_id}/cancel")
def mission_cancel(mission_id: str):
    try:
        return asdict(mission_store.update_status(mission_id, MissionStatus.CANCELLED))
    except KeyError:
        raise HTTPException(404, "Mission not found") from None


class StandingPermissionCreate(BaseModel):
    name: str = Field(min_length=2)
    channels: list[str] = Field(default_factory=list)
    allow_publish: bool = False
    allow_external_messages: bool = False
    allow_spend: bool = False
    allow_commerce: bool = False
    max_daily_spend: float | None = None
    max_total_spend: float | None = None
    currency: str = "BRL"


@app.get("/v1/permissions")
def permissions_list():
    return {"permissions": [asdict(p) for p in standing_permissions.list()]}


@app.post("/v1/permissions")
def permissions_create(req: StandingPermissionCreate):
    if req.allow_spend and req.max_daily_spend is None and req.max_total_spend is None:
        raise HTTPException(400, "Spend permission requires a daily or total ceiling")
    permission = standing_permissions.create(**req.model_dump())
    return asdict(permission)


@app.delete("/v1/permissions/{permission_id}")
def permissions_delete(permission_id: str):
    if not standing_permissions.delete(permission_id):
        raise HTTPException(404, "Permission not found")
    return {"deleted": True, "id": permission_id}


# ---------------------------------------------------------------------------
# Generated assets
# ---------------------------------------------------------------------------


@app.get("/v1/assets/{filename}")
def generated_asset(filename: str):
    if Path(filename).name != filename:
        raise HTTPException(400, "Invalid asset name")
    path = settings.workspace_path / "generated" / filename
    if not path.exists() or not path.is_file():
        raise HTTPException(404, "Asset not found")
    return FileResponse(path, headers={"X-Robots-Tag": "noindex, nofollow"})


# ---------------------------------------------------------------------------
# Core chat/workflow APIs
# ---------------------------------------------------------------------------


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    try:
        r = await jarvis.handle(
            req.message,
            req.session_id,
            req.location.model_dump() if req.location else None,
        )
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
            location = data.get("location") if isinstance(data.get("location"), dict) else None
            try:
                result = await jarvis.handle(msg, None, location)
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
                        k: str(v) if k in {"workflow_id", "session_id"} else v
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
    mission_id: str | None = None


@app.post("/v1/tools/{tool_name}/execute")
async def execute_tool(tool_name: str, req: ToolRun):
    tool = jarvis.tools.tools.get(tool_name)
    if not tool:
        raise HTTPException(404, "Tool not found")
    if tool.risk == RiskLevel.HIGH and not req.approved and not req.mission_id:
        if not req.workflow_id:
            raise HTTPException(400, "workflow_id is required for approval-gated tools")
        aid = jarvis.db.create_approval(req.workflow_id, tool_name, req.args)
        return {"ok": False, "approval_required": True, "approval_id": aid}
    return await jarvis.tools.execute(
        tool_name,
        approved=req.approved,
        mission_id=req.mission_id,
        **req.args,
    )
