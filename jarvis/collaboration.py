from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jarvis.config import settings
from jarvis.integrations.google_ads import GoogleAdsError, google_ads
from jarvis.router import ModelRouter
from jarvis.tools.registry import ToolRegistry


WORKBENCH_SYSTEM = """You are JARVIS operating an interactive Google Ads workbench with the user.
This is COLLABORATIVE mode, not autonomous Mission mode. The user wants to build and edit things together while seeing the current state.
Return ONLY valid JSON with this shape:
{
  "intent":"show_dashboard|analyze|list_keywords|select_campaign|replace_keyword|add_keywords|remove_keyword|update_draft|create_campaign|open_google_ads|close|discuss",
  "campaign_id":null,
  "campaign_name":null,
  "old_keyword":null,
  "new_keyword":null,
  "keywords":[],
  "match_type":"PHRASE",
  "draft_updates":{},
  "reply":"short direct reply"
}
Rules:
- 'vamos criar', 'vamos montar', or 'quero criar junto' means collaborate. NEVER interpret that alone as permission to create/publish the campaign.
- 'vamos mudar as palavras-chave' means list/show keywords and ask which ones, not mutate anything yet.
- replace_keyword/add_keywords/remove_keyword require an explicit user instruction naming the change.
- create_campaign is allowed only when the user explicitly says to create/confirm/publish the prepared campaign now.
- Read-only dashboard/statistics/analysis actions need no approval.
- Keep replies concise and operational.
- Never invent campaign IDs, keywords, metrics, or draft fields.
"""

ANALYSIS_SYSTEM = """You are JARVIS analyzing a Google Ads account inside an interactive workbench.
Use only the supplied live account data. Be concise: summarize direction, strongest signal, biggest concern, and the single best next action. If data is sparse, say so. Never invent attribution or causality."""


@dataclass
class WorkbenchState:
    session_id: str
    kind: str = "google_ads"
    mode: str = "collaborative"
    title: str = "Google Ads"
    status: str = "active"
    selected_campaign_id: str | None = None
    selected_campaign_name: str | None = None
    campaigns: list[dict[str, Any]] = field(default_factory=list)
    keywords: list[dict[str, Any]] = field(default_factory=list)
    draft: dict[str, Any] = field(default_factory=dict)
    note: str | None = None
    created_at: str = ""
    updated_at: str = ""


class WorkbenchStore:
    @property
    def path(self) -> Path:
        return settings.secrets_file.parent / "workbenches.json"

    def _read(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write(self, data: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(self.path.parent, 0o700)
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, self.path)

    def get(self, session_id: str) -> WorkbenchState | None:
        raw = self._read().get(session_id)
        return WorkbenchState(**raw) if raw else None

    def save(self, state: WorkbenchState) -> WorkbenchState:
        now = datetime.now(timezone.utc).isoformat()
        if not state.created_at:
            state.created_at = now
        state.updated_at = now
        data = self._read()
        data[state.session_id] = asdict(state)
        self._write(data)
        return state

    def start(self, session_id: str) -> WorkbenchState:
        existing = self.get(session_id)
        if existing and existing.status == "active":
            return existing
        return self.save(WorkbenchState(session_id=session_id))

    def close(self, session_id: str) -> WorkbenchState | None:
        state = self.get(session_id)
        if not state:
            return None
        state.status = "closed"
        return self.save(state)


workbench_store = WorkbenchStore()


class CollaborativeWorkbench:
    def __init__(self, router: ModelRouter, tools: ToolRegistry):
        self.router = router
        self.tools = tools

    @staticmethod
    def looks_like_start(message: str) -> bool:
        text = message.lower()
        google_ads = "google ads" in text or "google ad" in text
        together = any(
            marker in text
            for marker in (
                "vamos criar",
                "vamos montar",
                "vamos fazer",
                "vamos configurar",
                "criar junto",
                "fazer junto",
                "montar junto",
                "quero criar com você",
                "quero criar com voce",
            )
        )
        return google_ads and together

    @staticmethod
    def _explicit_create(message: str) -> bool:
        text = message.lower().strip()
        phrases = (
            "pode criar a campanha",
            "crie a campanha agora",
            "pode criar agora",
            "confirmo a criação",
            "confirmo a criacao",
            "publique a campanha",
            "pode publicar a campanha",
        )
        return any(p in text for p in phrases)

    @staticmethod
    def _workbench_payload(state: WorkbenchState) -> dict[str, Any]:
        campaigns = state.campaigns
        impressions = sum(int(c.get("impressions") or 0) for c in campaigns)
        clicks = sum(int(c.get("clicks") or 0) for c in campaigns)
        cost = sum(float(c.get("cost_brl") or 0) for c in campaigns)
        conversions = sum(float(c.get("conversions") or 0) for c in campaigns)
        return {
            "kind": state.kind,
            "mode": state.mode,
            "title": state.title,
            "status": state.status,
            "selected_campaign_id": state.selected_campaign_id,
            "selected_campaign_name": state.selected_campaign_name,
            "metrics": {
                "impressions": impressions,
                "clicks": clicks,
                "cost_brl": round(cost, 2),
                "conversions": round(conversions, 2),
                "ctr_percent": round((clicks / impressions * 100) if impressions else 0, 2),
            },
            "campaigns": campaigns,
            "keywords": state.keywords,
            "draft": state.draft,
            "note": state.note,
            "external_url": "https://ads.google.com/aw/campaigns",
        }

    @staticmethod
    def _normalize_campaigns(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in rows:
            campaign = row.get("campaign", {}) if isinstance(row, dict) else {}
            metrics = row.get("metrics", {}) if isinstance(row, dict) else {}
            micros = float(metrics.get("costMicros") or metrics.get("cost_micros") or 0)
            out.append(
                {
                    "id": str(campaign.get("id") or ""),
                    "name": campaign.get("name") or "Campanha sem nome",
                    "status": campaign.get("status") or "UNKNOWN",
                    "impressions": int(metrics.get("impressions") or 0),
                    "clicks": int(metrics.get("clicks") or 0),
                    "cost_brl": round(micros / 1_000_000, 2),
                    "conversions": float(metrics.get("conversions") or 0),
                    "conversion_value": float(
                        metrics.get("conversionsValue") or metrics.get("conversions_value") or 0
                    ),
                }
            )
        return out

    @staticmethod
    def _normalize_keywords(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for row in rows:
            criterion = row.get("adGroupCriterion", {}) if isinstance(row, dict) else {}
            keyword = criterion.get("keyword", {}) if isinstance(criterion, dict) else {}
            ad_group = row.get("adGroup", {}) if isinstance(row, dict) else {}
            metrics = row.get("metrics", {}) if isinstance(row, dict) else {}
            text = keyword.get("text")
            if not text:
                continue
            out.append(
                {
                    "text": text,
                    "match_type": keyword.get("matchType") or "UNKNOWN",
                    "status": criterion.get("status") or "UNKNOWN",
                    "resource_name": criterion.get("resourceName"),
                    "ad_group_resource": ad_group.get("resourceName"),
                    "ad_group_name": ad_group.get("name"),
                    "impressions": int(metrics.get("impressions") or 0),
                    "clicks": int(metrics.get("clicks") or 0),
                    "cost_brl": round(float(metrics.get("costMicros") or 0) / 1_000_000, 2),
                    "conversions": float(metrics.get("conversions") or 0),
                }
            )
        return out

    async def _refresh_campaigns(self, state: WorkbenchState) -> WorkbenchState:
        try:
            state.campaigns = self._normalize_campaigns(await google_ads.performance(30))
            state.note = None
        except GoogleAdsError as exc:
            state.note = str(exc)
        return workbench_store.save(state)

    async def _refresh_keywords(self, state: WorkbenchState) -> WorkbenchState:
        if not state.selected_campaign_id:
            state.keywords = []
            state.note = "Selecione uma campanha para visualizar as palavras-chave."
            return workbench_store.save(state)
        try:
            rows = await google_ads.keywords(state.selected_campaign_id)
            state.keywords = self._normalize_keywords(rows)
            state.note = None
        except GoogleAdsError as exc:
            state.note = str(exc)
        return workbench_store.save(state)

    async def start(self, session_id: str) -> dict[str, Any]:
        state = workbench_store.start(session_id)
        state.draft = state.draft or {
            "name": None,
            "daily_budget_brl": None,
            "final_url": None,
            "headlines": [],
            "descriptions": [],
            "keywords": [],
            "match_type": "PHRASE",
        }
        state = await self._refresh_campaigns(state)
        return {
            "message": (
                "Modo colaborativo do Google Ads aberto. Não vou criar ou publicar a campanha sozinho. "
                "Posso mostrar a conta, analisar métricas e ir montando a campanha com você."
            ),
            "provider": "google_ads",
            "model": None,
            "actions": [
                {"type": "open_workspace", "label": "ABRIR WORKBENCH"},
                {
                    "type": "open_url",
                    "label": "GOOGLE ADS",
                    "url": "https://ads.google.com/aw/campaigns",
                },
            ],
            "workspace": self._workbench_payload(state),
        }

    async def _command(self, message: str, state: WorkbenchState) -> dict[str, Any]:
        provider = self.router.primary()
        reply = await provider.complete(
            WORKBENCH_SYSTEM,
            json.dumps(
                {
                    "message": message,
                    "state": self._workbench_payload(state),
                },
                ensure_ascii=False,
            ),
        )
        raw = reply.text.strip()
        match = re.search(r"\{.*\}", raw, re.S)
        command = json.loads(match.group(0) if match else raw)
        command["provider"] = reply.provider
        command["model"] = reply.model
        return command

    async def handle(self, session_id: str, message: str) -> dict[str, Any] | None:
        state = workbench_store.get(session_id)
        if not state or state.status != "active":
            return None

        command = await self._command(message, state)
        intent = str(command.get("intent") or "discuss")
        actions: list[dict[str, Any]] = [{"type": "open_workspace", "label": "WORKBENCH"}]
        text = str(command.get("reply") or "")

        if intent == "close":
            state = workbench_store.close(session_id) or state
            return {
                "message": text or "Workbench fechado. Nenhuma outra alteração será feita.",
                "provider": command.get("provider"),
                "model": command.get("model"),
                "actions": [],
                "workspace": self._workbench_payload(state),
            }

        if intent in {"show_dashboard", "analyze", "select_campaign"}:
            state = await self._refresh_campaigns(state)

        if intent == "select_campaign":
            campaign_id = str(command.get("campaign_id") or "").strip()
            campaign_name = str(command.get("campaign_name") or "").strip().lower()
            selected = None
            for campaign in state.campaigns:
                if campaign_id and campaign["id"] == campaign_id:
                    selected = campaign
                    break
                if campaign_name and campaign_name in campaign["name"].lower():
                    selected = campaign
                    break
            if selected:
                state.selected_campaign_id = selected["id"]
                state.selected_campaign_name = selected["name"]
                state = workbench_store.save(state)
                state = await self._refresh_keywords(state)
                text = text or f"Campanha {selected['name']} selecionada."
            else:
                text = "Não consegui identificar essa campanha. Escolha uma das campanhas mostradas no painel."

        if intent == "list_keywords":
            if not state.selected_campaign_id and len(state.campaigns) == 1:
                state.selected_campaign_id = state.campaigns[0]["id"]
                state.selected_campaign_name = state.campaigns[0]["name"]
                workbench_store.save(state)
            state = await self._refresh_keywords(state)
            if not state.selected_campaign_id:
                text = "Qual campanha você quer alterar? Selecione uma no painel e eu mostro as palavras-chave."
            else:
                text = text or "Palavras-chave carregadas no painel. Diga qual você quer adicionar, remover ou trocar."

        if intent in {"replace_keyword", "add_keywords", "remove_keyword"}:
            if not state.selected_campaign_id:
                text = "Primeiro preciso saber em qual campanha você quer fazer essa alteração."
            else:
                state = await self._refresh_keywords(state)
                if intent == "replace_keyword":
                    old = str(command.get("old_keyword") or "").strip()
                    new = str(command.get("new_keyword") or "").strip()
                    row = next((k for k in state.keywords if k["text"].lower() == old.lower()), None)
                    if not old or not new:
                        text = "Qual palavra-chave você quer trocar e qual deve entrar no lugar?"
                    elif not row:
                        text = f"Não encontrei '{old}' entre as palavras-chave carregadas."
                    else:
                        result = await self.tools.execute(
                            "google_ads.replace_keyword",
                            approved=True,
                            criterion_resource=row["resource_name"],
                            ad_group_resource=row["ad_group_resource"],
                            new_keyword=new,
                            match_type=str(command.get("match_type") or row["match_type"] or "PHRASE"),
                        )
                        text = (
                            f"Troquei '{old}' por '{new}'."
                            if result.get("ok")
                            else f"Não consegui alterar: {result.get('error')}"
                        )
                elif intent == "add_keywords":
                    words = [str(x).strip() for x in command.get("keywords", []) if str(x).strip()]
                    ad_group_resource = next(
                        (k.get("ad_group_resource") for k in state.keywords if k.get("ad_group_resource")),
                        None,
                    )
                    if not words:
                        text = "Quais palavras-chave você quer adicionar?"
                    elif not ad_group_resource:
                        text = "Não consegui determinar o grupo de anúncios. Selecione uma campanha com palavras-chave existentes."
                    else:
                        result = await self.tools.execute(
                            "google_ads.add_keywords",
                            approved=True,
                            ad_group_resource=ad_group_resource,
                            keywords=words,
                            match_type=str(command.get("match_type") or "PHRASE"),
                        )
                        text = (
                            "Adicionei: " + ", ".join(words) + "."
                            if result.get("ok")
                            else f"Não consegui adicionar: {result.get('error')}"
                        )
                else:
                    words = [str(x).strip() for x in command.get("keywords", []) if str(x).strip()]
                    if not words and command.get("old_keyword"):
                        words = [str(command["old_keyword"]).strip()]
                    targets = [k for k in state.keywords if k["text"].lower() in {w.lower() for w in words}]
                    if not words:
                        text = "Quais palavras-chave você quer remover?"
                    elif not targets:
                        text = "Não encontrei essas palavras-chave na campanha selecionada."
                    else:
                        errors = []
                        for target in targets:
                            result = await self.tools.execute(
                                "google_ads.remove_keyword",
                                approved=True,
                                criterion_resource=target["resource_name"],
                            )
                            if not result.get("ok"):
                                errors.append(result.get("error"))
                        text = (
                            "Removi: " + ", ".join(t["text"] for t in targets) + "."
                            if not errors
                            else "Algumas remoções falharam: " + "; ".join(str(x) for x in errors)
                        )
                state = await self._refresh_keywords(state)

        if intent == "update_draft":
            updates = command.get("draft_updates") or {}
            allowed = {
                "name",
                "daily_budget_brl",
                "final_url",
                "headlines",
                "descriptions",
                "keywords",
                "match_type",
            }
            for key, value in updates.items():
                if key in allowed and value is not None:
                    state.draft[key] = value
            state = workbench_store.save(state)
            text = text or "Atualizei o rascunho. Ele está visível no painel."

        if intent == "create_campaign":
            if not self._explicit_create(message):
                text = (
                    "A campanha continua apenas como rascunho. Quando quiser criar de verdade, diga: "
                    "'pode criar a campanha'."
                )
            else:
                required = ["name", "daily_budget_brl", "final_url", "headlines", "descriptions", "keywords"]
                missing = [key for key in required if not state.draft.get(key)]
                if missing:
                    text = "Antes de criar, ainda falta: " + ", ".join(missing) + "."
                else:
                    result = await self.tools.execute(
                        "google_ads.create_search_campaign",
                        approved=True,
                        name=state.draft["name"],
                        daily_budget_brl=float(state.draft["daily_budget_brl"]),
                        final_url=state.draft["final_url"],
                        headlines=list(state.draft["headlines"]),
                        descriptions=list(state.draft["descriptions"]),
                        keywords=list(state.draft["keywords"]),
                        match_type=str(state.draft.get("match_type") or "PHRASE"),
                    )
                    text = (
                        "Campanha criada em PAUSED. Ela não começará a gastar até você mandar ativá-la."
                        if result.get("ok")
                        else f"Não consegui criar a campanha: {result.get('error')}"
                    )
                    state = await self._refresh_campaigns(state)

        if intent == "analyze":
            provider = self.router.primary()
            reply = await provider.complete(
                ANALYSIS_SYSTEM,
                json.dumps(self._workbench_payload(state), ensure_ascii=False),
            )
            text = reply.text
            command["provider"] = reply.provider
            command["model"] = reply.model

        if intent == "open_google_ads":
            actions.append(
                {
                    "type": "open_url",
                    "label": "ABRIR GOOGLE ADS",
                    "url": "https://ads.google.com/aw/campaigns",
                }
            )
            text = text or "Google Ads pronto para abrir. O painel do JARVIS continua disponível aqui."

        if intent == "show_dashboard":
            text = text or "Atualizei as estatísticas da conta no painel."

        return {
            "message": text or "Workbench atualizado.",
            "provider": command.get("provider"),
            "model": command.get("model"),
            "actions": actions,
            "workspace": self._workbench_payload(state),
        }
