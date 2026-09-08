import base64
import json

from fastapi.testclient import TestClient

from jarvis.api import app, jarvis


def test_google_workspace_status_endpoint():
    client = TestClient(app)
    response = client.get('/v1/integrations/google/status')
    assert response.status_code == 200
    data = response.json()
    assert 'configured' in data
    assert 'connected' in data
    assert 'gmail_monitoring_available' in data


def test_google_tools_are_registered():
    names = set(jarvis.tools.tools)
    assert 'google.status' in names
    assert 'gmail.search' in names
    assert 'gmail.read' in names
    assert 'gmail.draft' in names
    assert 'gmail.send' in names
    assert 'calendar.upcoming' in names
    assert 'calendar.create' in names


def test_gmail_pubsub_webhook_creates_proactive_event(monkeypatch):
    from jarvis.config import settings

    monkeypatch.setattr(settings, 'google_pubsub_webhook_secret', None)
    client = TestClient(app)
    payload = {'emailAddress': 'test@example.com', 'historyId': '12345'}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    response = client.post(
        '/v1/webhooks/google/gmail',
        json={'message': {'data': encoded, 'messageId': 'm1'}},
    )
    assert response.status_code == 200
    event_id = response.json()['event_id']
    events = client.get('/v1/events', params={'status': 'pending'}).json()['events']
    assert any(e['id'] == event_id and e['source'] == 'gmail' for e in events)


def test_high_risk_google_tools_are_not_autonomous():
    autonomous_names = {x['name'] for x in jarvis.tools.autonomous_specs()}
    assert 'gmail.send' not in autonomous_names
    assert 'calendar.create' not in autonomous_names
    assert 'gmail.search' in autonomous_names
    assert 'calendar.upcoming' in autonomous_names
