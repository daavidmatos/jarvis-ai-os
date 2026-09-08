import pytest

from jarvis.browser_assistant import BrowserAssistant
from jarvis.orchestrator_universal import UniversalOrchestrator
from jarvis.universal_collaboration_desktop import EnhancedUniversalCollaborationHub


class FakeDB:
    def __init__(self):
        self.finished = None
        self.audit_event = None

    def create_workflow(self, sid, message, plan):
        self.plan = plan
        return "00000000-0000-4000-8000-000000000001"

    def finish_workflow(self, wid, status, output):
        self.finished = (wid, status, output)

    def audit(self, event, payload, wid):
        self.audit_event = (event, payload, wid)


def test_browser_intent_and_query_extraction():
    message = "Abra uma nova guia pra mim no navegador e pesquise por televisões"
    assert BrowserAssistant.looks_like_request(message)
    assert BrowserAssistant._query(message) == "televisões"
    assert not BrowserAssistant.looks_like_request("Qual televisão você recomenda?")


@pytest.mark.asyncio
async def test_browser_handoff_opens_google_search_automatically():
    assistant = BrowserAssistant(FakeDB())
    result = await assistant.handle(
        "00000000-0000-4000-8000-000000000002",
        "Abra uma nova guia e pesquise por televisões",
    )
    action = result["actions"][0]
    assert action["type"] == "open_url"
    assert action["auto"] is True
    assert action["url"].startswith("https://www.google.com/search?q=")
    assert "televis" in action["url"]


def test_direct_figma_speech_command_routes_to_collaboration():
    target = EnhancedUniversalCollaborationHub.detect_target(
        "Cria um projeto no Fig MØ pra mim"
    )
    assert target is not None
    assert target["target"] == "figma"
    assert EnhancedUniversalCollaborationHub._explicit_single_edit(
        "Cria um projeto no Fig MØ pra mim"
    )


def test_unrelated_command_is_not_mission_followup():
    assert not UniversalOrchestrator._mission_followup_like("Abra uma nova guia")
    assert not UniversalOrchestrator._mission_followup_like("Quem é essa pessoa?")
    assert UniversalOrchestrator._mission_followup_like("Pode prosseguir com essa campanha")
