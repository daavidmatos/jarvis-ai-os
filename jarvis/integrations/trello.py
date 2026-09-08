from __future__ import annotations

from typing import Any

import httpx

from jarvis.config import settings


TRELLO_BASE = "https://api.trello.com/1"


class TrelloError(RuntimeError):
    pass


class TrelloClient:
    def status(self) -> dict[str, Any]:
        return {"configured": bool(settings.trello_api_key and settings.trello_token)}

    def _auth(self) -> dict[str, str]:
        if not settings.trello_api_key or not settings.trello_token:
            raise TrelloError("Trello is not configured. Set TRELLO_API_KEY and TRELLO_TOKEN.")
        return {"key": settings.trello_api_key, "token": settings.trello_token}

    async def request(self, method: str, path: str, **kwargs) -> Any:
        params = dict(kwargs.pop("params", {}))
        params.update(self._auth())
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.request(
                method,
                f"{TRELLO_BASE}/{path.lstrip('/')}",
                params=params,
                **kwargs,
            )
        if response.status_code >= 400:
            raise TrelloError(f"Trello API HTTP {response.status_code}: {response.text[:1000]}")
        if not response.content:
            return {}
        return response.json()

    async def boards(self, limit: int = 20) -> list[dict[str, Any]]:
        data = await self.request(
            "GET",
            "members/me/boards",
            params={
                "fields": "id,name,url,closed,dateLastActivity,desc",
                "filter": "open",
                "lists": "none",
            },
        )
        return list(data[: min(max(int(limit), 1), 50)]) if isinstance(data, list) else []

    async def board(self, board_id: str) -> dict[str, Any]:
        board = await self.request(
            "GET",
            f"boards/{board_id}",
            params={"fields": "id,name,url,desc,dateLastActivity"},
        )
        lists = await self.request(
            "GET",
            f"boards/{board_id}/lists",
            params={"fields": "id,name,pos,closed"},
        )
        cards = await self.request(
            "GET",
            f"boards/{board_id}/cards",
            params={
                "fields": "id,name,desc,idList,due,dueComplete,labels,url,pos,dateLastActivity",
                "filter": "open",
            },
        )
        return {"board": board, "lists": lists, "cards": cards}

    async def create_card(
        self,
        list_id: str,
        name: str,
        description: str | None = None,
        due: str | None = None,
    ) -> dict[str, Any]:
        data = {"idList": list_id, "name": name}
        if description is not None:
            data["desc"] = description
        if due is not None:
            data["due"] = due
        return await self.request("POST", "cards", data=data)

    async def move_card(self, card_id: str, list_id: str) -> dict[str, Any]:
        return await self.request("PUT", f"cards/{card_id}", data={"idList": list_id})

    async def update_card(
        self,
        card_id: str,
        *,
        name: str | None = None,
        description: str | None = None,
        due: str | None = None,
        due_complete: bool | None = None,
    ) -> dict[str, Any]:
        data: dict[str, Any] = {}
        if name is not None:
            data["name"] = name
        if description is not None:
            data["desc"] = description
        if due is not None:
            data["due"] = due
        if due_complete is not None:
            data["dueComplete"] = str(bool(due_complete)).lower()
        if not data:
            raise TrelloError("No card changes were supplied.")
        return await self.request("PUT", f"cards/{card_id}", data=data)


trello = TrelloClient()
