from datetime import datetime
from zoneinfo import ZoneInfo
from jarvis.schemas import RiskLevel
from jarvis.tools.base import Tool

class TimeTool(Tool):
    name="time.now"; description="Get current time in an IANA timezone."; risk=RiskLevel.LOW
    async def run(self, timezone: str="America/Sao_Paulo"):
        now=datetime.now(ZoneInfo(timezone))
        return {"timezone":timezone,"iso":now.isoformat()}
