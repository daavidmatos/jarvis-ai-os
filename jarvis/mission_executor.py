from __future__ import annotations

import json
import re
from typing import Any

from jarvis.config import settings
from jarvis.missions import Mission, MissionStatus, mission_store
from jarvis.router import ModelRouter
from jarvis.tools.registry import ToolRegistry


MISSION_EXECUTOR_SYSTEM = """You are JARVIS Mission Executor.
You are executing one already-approved mission step. Make decisions yourself and minimize questions.
Use available tools when they materially advance the step. Never claim a tool ran unless the runtime returned its result.
Output either normal concise text OR exactly one JSON tool request:
{"tool":"tool.name","arguments":{...}}
Stay inside the approved mission envelope and budget. Do not invent credentials, budgets, URLs, account IDs, or successful actions.
If a required connector is unavailable, say exactly what is missing so the runtime can block the mission cleanly."""


class MissionExecutor:
    def __init__(self, router: ModelRouter, tools: ToolRegistry):
        self.router = router
        self.tools = tools

    @staticmethod
    def _tool_call(text: str) -> dict[str, Any] | None:
        match = re.search(r"\{.*\}", text.strip(), re.S)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except Exception:
            return None
        if not isinstance(data, dict) or not isinstance(data.get("tool"), str):
            return None
        if not isinstance(data.get("arguments", {}), dict):
            return None
        return data

    async def _execute_step(self, mission: Mission, step: dict[str, Any]) -> dict[str, Any]:
        provider = self.router.primary()
        transcript: list[str] = []
        specs = self.tools.mission_specs(mission.id)
        base = json.dumps(
            {
                "mission": {
                    "id": mission.id,
                    "title": mission.title,
                    "objective": mission.objective,
                    "envelope": mission.envelope,
                },
                "step": step,
                "available_tools": specs,
            },
            ensure_ascii=False,
        )
        for _ in range(settings.max_agent_steps):
            prompt = base
            if transcript:
                prompt += "\n\nTool transcript:\n" + "\n".join(transcript)
            reply = await provider.complete(MISSION_EXECUTOR_SYSTEM, prompt)
            call = self._tool_call(reply.text)
            if not call:
                return {
                    "ok": True,
                    "summary": reply.text,
                    "provider": reply.provider,
                    "model": reply.model,
                    "tool_steps": len(transcript),
                }
            tool_name = call["tool"]
            if tool_name not in self.tools.tools:
                transcript.append(f"Unknown tool requested: {tool_name}")
                continue
            result = await self.tools.execute(
                tool_name,
                mission_id=mission.id,
                **call.get("arguments", {}),
            )
            transcript.append(
                json.dumps({"tool": tool_name, "result": result}, ensure_ascii=False)[:16000]
            )
            mission_store.append_log(
                mission.id,
                "tool.executed",
                {"tool": tool_name, "result": result},
            )
            if not result.get("ok"):
                error = str(result.get("error") or "Tool execution failed")
                if result.get("approval_required"):
                    return {"ok": False, "blocked": True, "error": error}
                if any(
                    marker in error.lower()
                    for marker in ("not configured", "not connected", "missing", "required")
                ):
                    return {"ok": False, "blocked": True, "error": error}
        final = await provider.complete(
            "You are JARVIS. Summarize the completed mission step from the tool transcript. Do not request another tool.",
            base + "\n\nTool transcript:\n" + "\n".join(transcript),
        )
        return {
            "ok": True,
            "summary": final.text,
            "provider": final.provider,
            "model": final.model,
            "tool_steps": len(transcript),
        }

    async def execute(self, mission_id: str) -> dict[str, Any]:
        mission = mission_store.get(mission_id)
        if not mission:
            raise KeyError("Mission not found")
        if mission.blockers:
            raise ValueError("Mission still has blockers")
        if mission.status not in {
            MissionStatus.APPROVED.value,
            MissionStatus.RUNNING.value,
        }:
            raise ValueError("Mission must be approved before execution")

        mission_store.update_status(mission.id, MissionStatus.RUNNING)
        mission_store.append_log(mission.id, "mission.started", {})
        outputs: list[dict[str, Any]] = []

        for index in range(mission.current_step, len(mission.plan)):
            step = mission.plan[index]
            mission_store.set_current_step(mission.id, index)
            mission_store.append_log(mission.id, "step.started", {"index": index, "step": step})
            current = mission_store.get(mission.id) or mission
            result = await self._execute_step(current, step)
            outputs.append({"index": index, "step": step, "result": result})
            mission_store.append_output(mission.id, outputs[-1])
            if not result.get("ok"):
                error = str(result.get("error") or "Mission step failed")
                if result.get("blocked"):
                    mission_store.add_blocker(mission.id, error)
                    mission_store.append_log(mission.id, "mission.blocked", {"reason": error})
                    return {
                        "mission": mission_store.get(mission.id),
                        "ok": False,
                        "blocked": True,
                        "error": error,
                        "outputs": outputs,
                    }
                mission_store.update_status(mission.id, MissionStatus.FAILED)
                return {
                    "mission": mission_store.get(mission.id),
                    "ok": False,
                    "error": error,
                    "outputs": outputs,
                }
            mission_store.set_current_step(mission.id, index + 1)
            mission_store.append_log(mission.id, "step.completed", {"index": index})

        has_monitoring = any(
            str(step.get("phase", "")).lower() in {"monitor", "optimize"}
            for step in mission.plan
        )
        final_status = MissionStatus.MONITORING if has_monitoring else MissionStatus.COMPLETED
        mission_store.update_status(mission.id, final_status)
        mission_store.append_log(
            mission.id,
            "mission.execution_complete",
            {"status": final_status.value},
        )
        return {
            "mission": mission_store.get(mission.id),
            "ok": True,
            "outputs": outputs,
        }
