import pytest

from jarvis.mobility_assistant import MobilityAssistant


class FakeDB:
    def __init__(self):
        self.finished = None
        self.audits = []

    def create_workflow(self, sid, message, plan):
        self.plan = plan
        return "00000000-0000-4000-8000-000000000001"

    def finish_workflow(self, wid, status, output):
        self.finished = (wid, status, output)

    def audit(self, event, payload, wid):
        self.audits.append((event, payload, wid))


def test_detects_uber_and_extracts_destination():
    assert MobilityAssistant.looks_like_request(
        "Jarvis, peça um Uber pra mim para ir pro Shopping Tijuca"
    )
    assert (
        MobilityAssistant._destination(
            "Jarvis, peça um Uber pra mim para ir pro Shopping Tijuca"
        )
        == "Shopping Tijuca"
    )


@pytest.mark.asyncio
async def test_uber_requires_location_before_handoff():
    assistant = MobilityAssistant(FakeDB())
    result = await assistant.handle(
        "00000000-0000-4000-8000-000000000002",
        "Jarvis, peça um Uber pra mim para ir pro Shopping Tijuca",
        None,
    )
    assert result["provider"] == "uber"
    assert result["actions"][0]["type"] == "request_location"
    assert "localização" in result["message"].lower()


@pytest.mark.asyncio
async def test_uber_deep_link_uses_current_coordinates_and_destination():
    db = FakeDB()
    assistant = MobilityAssistant(db)
    result = await assistant.handle(
        "00000000-0000-4000-8000-000000000002",
        "Jarvis, peça um Uber pra mim para ir pro Shopping Tijuca",
        {"latitude": -22.9249, "longitude": -43.2331, "accuracy_m": 12},
    )
    action = result["actions"][0]
    assert action["type"] == "open_url"
    assert action["url"].startswith("uber://riderequest?")
    assert "pickup%5Blatitude%5D=-22.9249000" in action["url"]
    assert "pickup%5Blongitude%5D=-43.2331000" in action["url"]
    assert "Shopping+Tijuca" in action["url"]
    assert "confirmadas dentro do Uber" in result["message"]
    assert db.audits[0][0] == "mobility.uber.prepared"
