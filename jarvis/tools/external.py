from jarvis.google_workspace import google_workspace
from jarvis.schemas import RiskLevel
from jarvis.tools.base import Tool


class EmailSendTool(Tool):
    name = "email.send"
    description = "Send email through the connected Gmail account. High-risk external side effect."
    risk = RiskLevel.HIGH
    requires_approval = True

    async def run(self, to: str, subject: str, body: str):
        return await google_workspace.gmail_send(to, subject, body)
