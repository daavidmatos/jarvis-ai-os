from pathlib import Path
from jarvis.config import settings
from jarvis.schemas import RiskLevel
from jarvis.tools.base import Tool

def safe_path(relative: str) -> Path:
    root=settings.workspace_path
    target=(root/relative).resolve()
    if root != target and root not in target.parents:
        raise ValueError("Path outside JARVIS workspace")
    return target

class FileReadTool(Tool):
    name="files.read"; description="Read UTF-8 text inside the JARVIS workspace."; risk=RiskLevel.LOW
    async def run(self, path: str):
        p=safe_path(path)
        return {"path":str(p.relative_to(settings.workspace_path)),"content":p.read_text(encoding="utf-8")}

class FileWriteTool(Tool):
    name="files.write"; description="Write UTF-8 text inside the JARVIS workspace."; risk=RiskLevel.MEDIUM
    async def run(self, path: str, content: str):
        p=safe_path(path); p.parent.mkdir(parents=True,exist_ok=True); p.write_text(content,encoding="utf-8")
        return {"path":str(p.relative_to(settings.workspace_path)),"bytes":len(content.encode())}
