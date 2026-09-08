from __future__ import annotations

from typing import Any
from urllib.parse import quote

from jarvis.google_workspace import (
    GOOGLE_WORKSPACE_SCOPES,
    GoogleWorkspaceError,
    google_workspace,
)


DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
DOCS_SCOPE = "https://www.googleapis.com/auth/documents"
SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"
for _scope in (DRIVE_SCOPE, DOCS_SCOPE, SHEETS_SCOPE):
    if _scope not in GOOGLE_WORKSPACE_SCOPES:
        GOOGLE_WORKSPACE_SCOPES.append(_scope)

DRIVE_BASE = "https://www.googleapis.com/drive/v3"
DOCS_BASE = "https://docs.googleapis.com/v1"
SHEETS_BASE = "https://sheets.googleapis.com/v4"


class GoogleContentError(RuntimeError):
    pass


class GoogleContentClient:
    @staticmethod
    def status() -> dict[str, Any]:
        status = google_workspace.status()
        scopes = set(status.get("scopes", []))
        return {
            "connected": bool(status.get("connected")),
            "docs_scope": DOCS_SCOPE in scopes,
            "sheets_scope": SHEETS_SCOPE in scopes,
            "drive_scope": DRIVE_SCOPE in scopes,
            "reconnect_required": bool(status.get("connected"))
            and not {DRIVE_SCOPE, DOCS_SCOPE, SHEETS_SCOPE}.issubset(scopes),
        }

    @staticmethod
    def _mime(kind: str) -> str:
        return {
            "document": "application/vnd.google-apps.document",
            "spreadsheet": "application/vnd.google-apps.spreadsheet",
        }[kind]

    async def recent_files(self, kind: str, limit: int = 12) -> list[dict[str, Any]]:
        if kind not in {"document", "spreadsheet"}:
            raise GoogleContentError("kind must be document or spreadsheet")
        limit = min(max(int(limit), 1), 30)
        try:
            data = await google_workspace.request(
                "GET",
                f"{DRIVE_BASE}/files",
                params={
                    "q": f"mimeType='{self._mime(kind)}' and trashed=false",
                    "pageSize": limit,
                    "orderBy": "modifiedTime desc",
                    "fields": "files(id,name,mimeType,modifiedTime,webViewLink,owners(displayName,emailAddress))",
                },
            )
        except GoogleWorkspaceError as exc:
            raise GoogleContentError(str(exc)) from None
        return list(data.get("files", []))

    @staticmethod
    def _extract_doc_text(content: list[dict[str, Any]]) -> str:
        parts: list[str] = []
        for block in content or []:
            paragraph = block.get("paragraph")
            if paragraph:
                for element in paragraph.get("elements", []):
                    text = element.get("textRun", {}).get("content")
                    if text:
                        parts.append(text)
            table = block.get("table")
            if table:
                for row in table.get("tableRows", []):
                    for cell in row.get("tableCells", []):
                        parts.append(GoogleContentClient._extract_doc_text(cell.get("content", [])))
            toc = block.get("tableOfContents")
            if toc:
                parts.append(GoogleContentClient._extract_doc_text(toc.get("content", [])))
        return "".join(parts)

    async def document(self, file_id: str) -> dict[str, Any]:
        try:
            doc = await google_workspace.request("GET", f"{DOCS_BASE}/documents/{quote(file_id)}")
        except GoogleWorkspaceError as exc:
            raise GoogleContentError(str(exc)) from None
        body = doc.get("body", {})
        text = self._extract_doc_text(body.get("content", []))
        return {
            "id": doc.get("documentId") or file_id,
            "title": doc.get("title") or "Documento",
            "revision_id": doc.get("revisionId"),
            "text": text[:100000],
            "body_end_index": max(
                [int(x.get("endIndex") or 1) for x in body.get("content", [])] or [1]
            ),
            "url": f"https://docs.google.com/document/d/{file_id}/edit",
        }

    async def document_append(self, file_id: str, text: str) -> dict[str, Any]:
        snapshot = await self.document(file_id)
        index = max(int(snapshot.get("body_end_index") or 1) - 1, 1)
        try:
            result = await google_workspace.request(
                "POST",
                f"{DOCS_BASE}/documents/{quote(file_id)}:batchUpdate",
                json={"requests": [{"insertText": {"location": {"index": index}, "text": text}}]},
            )
        except GoogleWorkspaceError as exc:
            raise GoogleContentError(str(exc)) from None
        return {"ok": True, "document_id": file_id, "operation": "append", "result": result}

    async def document_replace(
        self, file_id: str, old_text: str, new_text: str, match_case: bool = False
    ) -> dict[str, Any]:
        if not old_text:
            raise GoogleContentError("old_text is required")
        try:
            result = await google_workspace.request(
                "POST",
                f"{DOCS_BASE}/documents/{quote(file_id)}:batchUpdate",
                json={
                    "requests": [
                        {
                            "replaceAllText": {
                                "containsText": {"text": old_text, "matchCase": bool(match_case)},
                                "replaceText": new_text,
                            }
                        }
                    ]
                },
            )
        except GoogleWorkspaceError as exc:
            raise GoogleContentError(str(exc)) from None
        return {"ok": True, "document_id": file_id, "operation": "replace", "result": result}

    async def spreadsheet(self, file_id: str) -> dict[str, Any]:
        try:
            meta = await google_workspace.request(
                "GET",
                f"{SHEETS_BASE}/spreadsheets/{quote(file_id)}",
                params={"includeGridData": "false"},
            )
        except GoogleWorkspaceError as exc:
            raise GoogleContentError(str(exc)) from None
        sheets = [
            {
                "sheet_id": x.get("properties", {}).get("sheetId"),
                "title": x.get("properties", {}).get("title"),
                "row_count": x.get("properties", {}).get("gridProperties", {}).get("rowCount"),
                "column_count": x.get("properties", {}).get("gridProperties", {}).get("columnCount"),
            }
            for x in meta.get("sheets", [])
        ]
        ranges: list[str] = []
        for sheet in sheets[:5]:
            title = sheet.get("title")
            if title:
                escaped = str(title).replace("'", "''")
                ranges.append(f"'{escaped}'!A1:Z50")
        values: dict[str, Any] = {}
        if ranges:
            try:
                data = await google_workspace.request(
                    "GET",
                    f"{SHEETS_BASE}/spreadsheets/{quote(file_id)}/values:batchGet",
                    params=[("ranges", r) for r in ranges] + [("majorDimension", "ROWS")],
                )
                for vr in data.get("valueRanges", []):
                    values[str(vr.get("range"))] = vr.get("values", [])
            except GoogleWorkspaceError as exc:
                raise GoogleContentError(str(exc)) from None
        props = meta.get("properties", {})
        return {
            "id": meta.get("spreadsheetId") or file_id,
            "title": props.get("title") or "Planilha",
            "locale": props.get("locale"),
            "time_zone": props.get("timeZone"),
            "sheets": sheets,
            "values": values,
            "url": f"https://docs.google.com/spreadsheets/d/{file_id}/edit",
        }

    async def spreadsheet_update(
        self, file_id: str, range_a1: str, values: list[list[Any]]
    ) -> dict[str, Any]:
        if not range_a1 or not values:
            raise GoogleContentError("range_a1 and values are required")
        try:
            result = await google_workspace.request(
                "PUT",
                f"{SHEETS_BASE}/spreadsheets/{quote(file_id)}/values/{quote(range_a1, safe='')}",
                params={"valueInputOption": "USER_ENTERED"},
                json={"range": range_a1, "majorDimension": "ROWS", "values": values},
            )
        except GoogleWorkspaceError as exc:
            raise GoogleContentError(str(exc)) from None
        return {"ok": True, "spreadsheet_id": file_id, "operation": "update", "result": result}

    async def spreadsheet_append(
        self, file_id: str, range_a1: str, values: list[list[Any]]
    ) -> dict[str, Any]:
        if not range_a1 or not values:
            raise GoogleContentError("range_a1 and values are required")
        try:
            result = await google_workspace.request(
                "POST",
                f"{SHEETS_BASE}/spreadsheets/{quote(file_id)}/values/{quote(range_a1, safe='')}:append",
                params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
                json={"majorDimension": "ROWS", "values": values},
            )
        except GoogleWorkspaceError as exc:
            raise GoogleContentError(str(exc)) from None
        return {"ok": True, "spreadsheet_id": file_id, "operation": "append", "result": result}


google_content = GoogleContentClient()
