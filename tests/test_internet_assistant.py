from jarvis.internet_assistant import InternetAssistant
from jarvis.tools.web import _parse_duckduckgo_html


def test_internet_intent_is_explicit_and_shopping_aware():
    assert InternetAssistant.looks_like_request("Pesquise na internet onde comprar manteiga")
    assert InternetAssistant.looks_like_request("Procure no iFood um mercado para comprar manteiga")
    assert InternetAssistant.looks_like_request("Qual o preço atual desse produto?")
    assert not InternetAssistant.looks_like_request("Oi, tudo bem?")


def test_duckduckgo_html_parser_returns_real_urls_and_snippets():
    body = """
    <div class="result">
      <a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fproduto">Loja &amp; Produto</a>
      <a class="result__snippet">Manteiga por R$ 10,90 em estoque.</a>
    </div>
    """
    results = _parse_duckduckgo_html(body, 5)
    assert results == [
        {
            "title": "Loja & Produto",
            "url": "https://example.com/produto",
            "snippet": "Manteiga por R$ 10,90 em estoque.",
        }
    ]
