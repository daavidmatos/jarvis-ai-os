from jarvis.google_workspace import google_workspace
from jarvis.schemas import RiskLevel
from jarvis.tools.base import Tool


class GoogleStatusTool(Tool):
    name = "google.status"
    description = "Check whether the user's Google Workspace account is connected and monitoring-capable."
    risk = RiskLevel.LOW

    async def run(self):
        status = google_workspace.status()
        if status["connected"]:
            try:
                status["profile"] = await google_workspace.gmail_profile()
            except Exception as exc:
                status["profile_error"] = str(exc)
        return status


class GmailSearchTool(Tool):
    name = "gmail.search"
    description = "Search the connected Gmail mailbox and return message metadata. Read-only."
    risk = RiskLevel.LOW

    async def run(self, query: str = "in:inbox", max_results: int = 10):
        return {"messages": await google_workspace.gmail_search(query, max_results)}


class GmailReadTool(Tool):
    name = "gmail.read"
    description = "Read one Gmail message by message ID. Read-only."
    risk = RiskLevel.LOW

    async def run(self, message_id: str):
        return await google_workspace.gmail_message(message_id)


class GmailDraftTool(Tool):
    name = "gmail.draft"
    description = "Create a Gmail draft without sending it. Reversible/preparatory external action."
    risk = RiskLevel.MEDIUM

    async def run(self, to: str, subject: str, body: str):
        return await google_workspace.gmail_draft(to, subject, body)


class GmailSendTool(Tool):
    name = "gmail.send"
    description = "Send an email through the connected Gmail account. External side effect."
    risk = RiskLevel.HIGH
    requires_approval = True
    mission_permission = "external_messages"

    async def run(self, to: str, subject: str, body: str):
        return await google_workspace.gmail_send(to, subject, body)


class CalendarUpcomingTool(Tool):
    name = "calendar.upcoming"
    description = "List upcoming events in the connected Google Calendar. Read-only."
    risk = RiskLevel.LOW

    async def run(self, hours: int = 168, max_results: int = 20):
        return {"events": await google_workspace.calendar_upcoming(hours, max_results)}


class CalendarCreateTool(Tool):
    name = "calendar.create"
    description = "Create a Google Calendar event and optionally invite attendees. External side effect."
    risk = RiskLevel.HIGH
    requires_approval = True
    mission_permission = "external_messages"

    async def run(
        self,
        summary: str,
        start: str,
        end: str,
        timezone_name: str = "America/Sao_Paulo",
        description: str = "",
        attendees: list[str] | None = None,
    ):
        return await google_workspace.calendar_create(
            summary=summary,
            start=start,
            end=end,
            timezone_name=timezone_name,
            description=description,
            attendees=attendees,
        )
