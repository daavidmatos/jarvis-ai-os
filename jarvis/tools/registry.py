from jarvis.policy import PolicyEngine
from jarvis.schemas import RiskLevel
from jarvis.tools.calculator import CalculatorTool
from jarvis.tools.files import FileReadTool, FileWriteTool
from jarvis.tools.web import WebFetchTool, WebSearchTool
from jarvis.tools.time import TimeTool
from jarvis.tools.external import EmailSendTool

class ToolRegistry:
    def __init__(self):
        tools=[CalculatorTool(),FileReadTool(),FileWriteTool(),WebFetchTool(),WebSearchTool(),TimeTool(),EmailSendTool()]
        self.tools={t.name:t for t in tools}; self.policy=PolicyEngine()

    def list(self): return [t.spec.model_dump() for t in self.tools.values()]

    async def execute(self, name: str, approved: bool=False, **kwargs):
        if name not in self.tools: raise KeyError(f"Unknown tool: {name}")
        tool=self.tools[name]
        if not self.policy.can_execute(tool.risk,approved=approved):
            return {"ok":False,"approval_required":tool.risk==RiskLevel.HIGH,"error":f"Policy blocked {name}"}
        try:
            result=await tool.run(**kwargs)
            return {"ok":True,"result":result}
        except Exception as e:
            return {"ok":False,"error":str(e)}
