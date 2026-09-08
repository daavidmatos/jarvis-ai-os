from __future__ import annotations

from typing import Any

from jarvis.desktop_actions import DesktopActionPlanner
from jarvis.desktop_bridge import desktop_bridge
from jarvis.integrations.google_content import google_content
from jarvis.integrations.trello import trello
from jarvis.router import ModelRouter
from jarvis.schemas import RiskLevel
from jarvis.tools.base import Tool


class GoogleDocsRecentTool(Tool):
    name = "google_docs.recent"
    description = "List recent Google Docs available to the connected user. Read-only."
    risk = RiskLevel.LOW

    async def run(self, limit: int = 12):
        return {"documents": await google_content.recent_files("document", limit)}


class GoogleDocsReadTool(Tool):
    name = "google_docs.read"
    description = "Read the current text/state of a Google Doc by file id. Read-only."
    risk = RiskLevel.LOW

    async def run(self, file_id: str):
        return await google_content.document(file_id)


class GoogleDocsAppendTool(Tool):
    name = "google_docs.append"
    description = "Append explicit text to a Google Doc. Mutates the document."
    risk = RiskLevel.HIGH
    requires_approval = True
    mission_permission = "workspace_edit"

    async def run(self, file_id: str, text: str):
        return await google_content.document_append(file_id, text)


class GoogleDocsReplaceTool(Tool):
    name = "google_docs.replace"
    description = "Replace an exact text occurrence throughout a Google Doc. Mutates the document."
    risk = RiskLevel.HIGH
    requires_approval = True
    mission_permission = "workspace_edit"

    async def run(self, file_id: str, old_text: str, new_text: str, match_case: bool = False):
        return await google_content.document_replace(file_id, old_text, new_text, match_case)


class GoogleSheetsRecentTool(Tool):
    name = "google_sheets.recent"
    description = "List recent Google Sheets available to the connected user. Read-only."
    risk = RiskLevel.LOW

    async def run(self, limit: int = 12):
        return {"spreadsheets": await google_content.recent_files("spreadsheet", limit)}


class GoogleSheetsReadTool(Tool):
    name = "google_sheets.read"
    description = "Read spreadsheet metadata and a bounded preview of current cell values. Read-only."
    risk = RiskLevel.LOW

    async def run(self, file_id: str):
        return await google_content.spreadsheet(file_id)


class GoogleSheetsUpdateTool(Tool):
    name = "google_sheets.update"
    description = "Write explicit values/formulas to a concrete A1 range in Google Sheets."
    risk = RiskLevel.HIGH
    requires_approval = True
    mission_permission = "workspace_edit"

    async def run(self, file_id: str, range_a1: str, values: list[list[Any]]):
        return await google_content.spreadsheet_update(file_id, range_a1, values)


class GoogleSheetsAppendTool(Tool):
    name = "google_sheets.append"
    description = "Append explicit rows to a Google Sheet range."
    risk = RiskLevel.HIGH
    requires_approval = True
    mission_permission = "workspace_edit"

    async def run(self, file_id: str, range_a1: str, values: list[list[Any]]):
        return await google_content.spreadsheet_append(file_id, range_a1, values)


class TrelloBoardsTool(Tool):
    name = "trello.boards"
    description = "List open Trello boards for the connected user. Read-only."
    risk = RiskLevel.LOW

    async def run(self, limit: int = 20):
        return {"boards": await trello.boards(limit)}


class TrelloBoardTool(Tool):
    name = "trello.board"
    description = "Read a Trello board with lists and open cards. Read-only."
    risk = RiskLevel.LOW

    async def run(self, board_id: str):
        return await trello.board(board_id)


class TrelloCreateCardTool(Tool):
    name = "trello.create_card"
    description = "Create a Trello card in a specific list."
    risk = RiskLevel.HIGH
    requires_approval = True
    mission_permission = "workspace_edit"

    async def run(
        self,
        list_id: str,
        name: str,
        description: str | None = None,
        due: str | None = None,
    ):
        return await trello.create_card(list_id, name, description, due)


class TrelloMoveCardTool(Tool):
    name = "trello.move_card"
    description = "Move a Trello card to a specific list."
    risk = RiskLevel.HIGH
    requires_approval = True
    mission_permission = "workspace_edit"

    async def run(self, card_id: str, list_id: str):
        return await trello.move_card(card_id, list_id)


class TrelloUpdateCardTool(Tool):
    name = "trello.update_card"
    description = "Update explicit Trello card fields such as description or due date."
    risk = RiskLevel.HIGH
    requires_approval = True
    mission_permission = "workspace_edit"

    async def run(
        self,
        card_id: str,
        name: str | None = None,
        description: str | None = None,
        due: str | None = None,
        due_complete: bool | None = None,
    ):
        return await trello.update_card(
            card_id,
            name=name,
            description=description,
            due=due,
            due_complete=due_complete,
        )


class DesktopStatusTool(Tool):
    name = "desktop.status"
    description = "Read connected JARVIS Desktop Bridge clients and available applications. Read-only."
    risk = RiskLevel.LOW

    async def run(self):
        return desktop_bridge.status()


class DesktopInspectTool(Tool):
    name = "desktop.inspect"
    description = "Read the latest reported application state/frame metadata from the Desktop Bridge. Read-only."
    risk = RiskLevel.LOW

    async def run(self, app: str):
        return desktop_bridge.snapshot_for_app(app) or {"connected": False, "app": app}


class DesktopCommandTool(Tool):
    name = "desktop.command"
    description = (
        "Send one approved semantic edit/control command to a connected desktop application. "
        "Commands are translated to an allow-listed structured action before local execution."
    )
    risk = RiskLevel.HIGH
    requires_approval = True
    mission_permission = "computer_control"

    async def run(self, app: str, instruction: str):
        client = desktop_bridge.find_app(app)
        if not client:
            raise RuntimeError(f"No connected Desktop Bridge client exposes {app}.")
        snapshot = desktop_bridge.snapshot_for_app(app) or {}
        planner = DesktopActionPlanner(ModelRouter())
        plan = await planner.plan(
            app,
            instruction,
            snapshot.get("state") if isinstance(snapshot.get("state"), dict) else {},
        )
        if plan.action == "unsupported":
            raise RuntimeError(
                plan.reason
                or f"No safe structured write adapter is available for {app}."
            )
        return await desktop_bridge.queue_command(
            client.client_id,
            app,
            instruction,
            mode="autonomous",
            approval_scope="mission_or_single_command",
            plan=plan.to_dict(),
        )
