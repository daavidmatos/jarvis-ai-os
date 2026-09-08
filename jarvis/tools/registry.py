from __future__ import annotations

from typing import Any

from jarvis.missions import MissionStatus, mission_store
from jarvis.policy import PolicyEngine
from jarvis.schemas import RiskLevel
from jarvis.tools.base import Tool
from jarvis.tools.calculator import CalculatorTool
from jarvis.tools.external import EmailSendTool
from jarvis.tools.files import FileReadTool, FileWriteTool
from jarvis.tools.google import (
    CalendarCreateTool,
    CalendarUpcomingTool,
    GmailDraftTool,
    GmailReadTool,
    GmailSearchTool,
    GmailSendTool,
    GoogleStatusTool,
)
from jarvis.tools.local import PlacesSearchTool, PlacesStatusTool
from jarvis.tools.marketing import (
    CreativeImageGenerateTool,
    FuelCreateCouponTool,
    FuelRecentOrdersTool,
    FuelSalesSummaryTool,
    FuelStatusTool,
    GoogleAdsAddKeywordsTool,
    GoogleAdsCreateSearchCampaignTool,
    GoogleAdsKeywordsTool,
    GoogleAdsPerformanceTool,
    GoogleAdsRemoveKeywordTool,
    GoogleAdsReplaceKeywordTool,
    GoogleAdsSetCampaignStatusTool,
    GoogleAdsStatusTool,
    InstagramPublishPhotoTool,
    InstagramStatusTool,
    InstagramTaggedMediaTool,
)
from jarvis.tools.time import TimeTool
from jarvis.tools.web import WebFetchTool, WebSearchTool
from jarvis.tools.workspaces import (
    DesktopCommandTool,
    DesktopInspectTool,
    DesktopStatusTool,
    GoogleDocsAppendTool,
    GoogleDocsReadTool,
    GoogleDocsRecentTool,
    GoogleDocsReplaceTool,
    GoogleSheetsAppendTool,
    GoogleSheetsReadTool,
    GoogleSheetsRecentTool,
    GoogleSheetsUpdateTool,
    TrelloBoardTool,
    TrelloBoardsTool,
    TrelloCreateCardTool,
    TrelloMoveCardTool,
    TrelloUpdateCardTool,
)


class ToolRegistry:
    def __init__(self):
        tools = [
            CalculatorTool(),
            FileReadTool(),
            FileWriteTool(),
            WebFetchTool(),
            WebSearchTool(),
            TimeTool(),
            PlacesStatusTool(),
            PlacesSearchTool(),
            GoogleStatusTool(),
            GmailSearchTool(),
            GmailReadTool(),
            GmailDraftTool(),
            GmailSendTool(),
            CalendarUpcomingTool(),
            CalendarCreateTool(),
            EmailSendTool(),
            InstagramStatusTool(),
            InstagramTaggedMediaTool(),
            InstagramPublishPhotoTool(),
            GoogleAdsStatusTool(),
            GoogleAdsPerformanceTool(),
            GoogleAdsKeywordsTool(),
            GoogleAdsAddKeywordsTool(),
            GoogleAdsRemoveKeywordTool(),
            GoogleAdsReplaceKeywordTool(),
            GoogleAdsCreateSearchCampaignTool(),
            GoogleAdsSetCampaignStatusTool(),
            CreativeImageGenerateTool(),
            FuelStatusTool(),
            FuelRecentOrdersTool(),
            FuelSalesSummaryTool(),
            FuelCreateCouponTool(),
            GoogleDocsRecentTool(),
            GoogleDocsReadTool(),
            GoogleDocsAppendTool(),
            GoogleDocsReplaceTool(),
            GoogleSheetsRecentTool(),
            GoogleSheetsReadTool(),
            GoogleSheetsUpdateTool(),
            GoogleSheetsAppendTool(),
            TrelloBoardsTool(),
            TrelloBoardTool(),
            TrelloCreateCardTool(),
            TrelloMoveCardTool(),
            TrelloUpdateCardTool(),
            DesktopStatusTool(),
            DesktopInspectTool(),
            DesktopCommandTool(),
        ]
        self.tools = {t.name: t for t in tools}
        self.policy = PolicyEngine()

        # Google Ads' collaborative workbench remains a HIGH-risk surface because
        # an explicit turn can perform a paid-ad mutation. Vague collaboration
        # phrases are filtered inside CollaborativeWorkbench before any mutation.
        from jarvis.collaboration import CollaborativeWorkbench, workbench_store
        from jarvis.router import ModelRouter

        handler = CollaborativeWorkbench(ModelRouter(), self)

        class GoogleAdsWorkbenchTool(Tool):
            name = "google_ads.workbench"
            description = (
                "Interactive Google Ads workbench. Starts collaborative mode, shows live metrics, "
                "builds campaign drafts, and applies only explicit user-requested edits."
            )
            risk = RiskLevel.HIGH
            requires_approval = True

            async def run(inner_self, session_id: str, message: str):
                state = workbench_store.get(session_id)
                if state and state.status == "active":
                    result = await handler.handle(session_id, message)
                    if result is not None:
                        return result
                if handler.looks_like_start(message):
                    return await handler.start(session_id)
                return {
                    "message": (
                        "Nenhum workbench do Google Ads está ativo. Diga algo como "
                        "'vamos criar uma campanha no Google Ads'."
                    ),
                    "actions": [],
                    "workspace": None,
                    "provider": "google_ads",
                    "model": None,
                }

        workbench_tool = GoogleAdsWorkbenchTool()
        self.tools[workbench_tool.name] = workbench_tool

    def list(self):
        return [t.spec.model_dump() for t in self.tools.values()]

    def autonomous_specs(self):
        return [
            t.spec.model_dump()
            for t in self.tools.values()
            if t.risk in {RiskLevel.LOW, RiskLevel.MEDIUM}
        ]

    @staticmethod
    def _mission_authority(tool, mission_id: str, args: dict[str, Any]) -> tuple[bool, str]:
        mission = mission_store.get(mission_id)
        if not mission:
            return False, "Mission not found"
        if mission.status not in {
            MissionStatus.APPROVED.value,
            MissionStatus.RUNNING.value,
            MissionStatus.MONITORING.value,
        }:
            return False, "Mission is not approved/running"
        permission = getattr(tool, "mission_permission", None)
        if not permission:
            return False, "Tool has no mission permission mapping"
        envelope = mission.envelope
        allowed = {
            "publish": bool(envelope.get("allow_publish")),
            "external_messages": bool(envelope.get("allow_external_messages")),
            "spend": bool(envelope.get("allow_spend")),
            "commerce": bool(envelope.get("allow_commerce")),
            "workspace_edit": bool(envelope.get("allow_workspace_edits")),
            "computer_control": bool(envelope.get("allow_computer_control")),
        }.get(permission, False)
        if not allowed:
            return False, f"Mission envelope does not authorize {permission}"

        spend_arg = getattr(tool, "spend_arg", None)
        if permission == "spend" and spend_arg:
            value = args.get(spend_arg)
            if value is None:
                return False, f"{spend_arg} is required for budget enforcement"
            try:
                amount = float(value)
            except (TypeError, ValueError):
                return False, f"{spend_arg} must be numeric"
            daily_limit = envelope.get("daily_budget_limit")
            total_limit = envelope.get("total_budget_limit")
            if daily_limit is not None and amount > float(daily_limit):
                return False, f"Requested daily spend {amount} exceeds mission limit {daily_limit}"
            if daily_limit is None and total_limit is not None and amount > float(total_limit):
                return False, f"Requested spend {amount} exceeds mission total limit {total_limit}"
        return True, "authorized by approved mission envelope"

    def mission_specs(self, mission_id: str) -> list[dict[str, Any]]:
        specs = []
        for tool in self.tools.values():
            if tool.risk in {RiskLevel.LOW, RiskLevel.MEDIUM}:
                specs.append(tool.spec.model_dump())
                continue
            ok, _ = self._mission_authority(tool, mission_id, {})
            # Spend tools need a runtime amount, so they are visible when the mission
            # grants spend authority even though the final amount check happens later.
            if not ok and getattr(tool, "mission_permission", None) == "spend":
                mission = mission_store.get(mission_id)
                if mission and mission.status in {
                    MissionStatus.APPROVED.value,
                    MissionStatus.RUNNING.value,
                    MissionStatus.MONITORING.value,
                } and mission.envelope.get("allow_spend"):
                    ok = True
            if ok:
                spec = tool.spec.model_dump()
                spec["mission_authorized"] = True
                specs.append(spec)
        return specs

    async def execute(
        self,
        name: str,
        approved: bool = False,
        mission_id: str | None = None,
        **kwargs,
    ):
        if name not in self.tools:
            raise KeyError(f"Unknown tool: {name}")
        tool = self.tools[name]
        mission_reason = None
        if tool.risk == RiskLevel.HIGH and mission_id and not approved:
            mission_ok, mission_reason = self._mission_authority(tool, mission_id, kwargs)
            if mission_ok:
                approved = True
        if not self.policy.can_execute(tool.risk, approved=approved):
            return {
                "ok": False,
                "approval_required": tool.risk == RiskLevel.HIGH,
                "error": mission_reason or f"Policy blocked {name}",
            }
        try:
            result = await tool.run(**kwargs)
            return {
                "ok": True,
                "result": result,
                "authority": mission_reason if mission_id else None,
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}
