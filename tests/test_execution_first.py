from jarvis.browser_assistant import BrowserAssistant
from jarvis.commerce_assistant import CommerceAssistant
from jarvis.content_assistant import ContentAssistant
from jarvis.integrations.browserless_agent import browserless_agent
from jarvis.tools.web import _parse_bing_html


def test_browser_routes_google_visual_search():
    text = "Eu quero que você pesquise aqui no Google tipos de manteiga e eu quero ver o resultado dentro do Google."
    assert BrowserAssistant.looks_like_request(text)
    url, query = BrowserAssistant._target_url(text)
    assert "google.com/search" in url
    assert "tipos de manteiga" in query.lower()


def test_ifood_request_is_operational():
    assert CommerceAssistant.looks_like_request("Faça um pedido pra mim no iFood na Pizzaria do Rão")


def test_content_creation_detects_docs_and_sheets():
    assert ContentAssistant.looks_like_request("Crie um documento sobre a Fuel")
    assert ContentAssistant.looks_like_request("Crie uma planilha chamada Vendas")


def test_bing_parser_extracts_live_rows():
    html = '''<li class="b_algo"><h2><a href="https://example.com">Exemplo</a></h2><div><p>Trecho real</p></div></li>'''
    rows = _parse_bing_html(html, 5)
    assert rows == [{"title": "Exemplo", "url": "https://example.com", "snippet": "Trecho real"}]


def test_browserless_status_is_safe_without_token():
    status = browserless_agent.status()
    assert "configured" in status
    assert status["provider"] == "browserless_agent"
