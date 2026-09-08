from jarvis.schemas import RiskLevel
from jarvis.tools.base import Tool

class EmailSendTool(Tool):
    name="email.send"
    description="Send email through a configured OAuth connector. High-risk external side effect."
    risk=RiskLevel.HIGH
    requires_approval=True
    async def run(self, to: str, subject: str, body: str):
        raise RuntimeError("Email connector is not configured in this standalone MVP. Add OAuth connector before enabling this tool.")
