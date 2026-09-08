import pytest

from jarvis.orchestrator import Orchestrator
from jarvis.providers.base import ModelReply
from jarvis.strategic_advisor import StrategicAdvisor, StrategicAssessment


class FakeProvider:
    name = "openai"
    model = "test-model"

    async def complete(self, system: str, user: str, *, temperature: float = 0.2):
        return ModelReply(
            text='''{
              "verdict":"adjust",
              "recommendation":"A meta é boa, mas eu mudaria o canal e começaria com um teste menor.",
              "reasons":["O custo de oportunidade está alto", "A hipótese ainda não foi validada"],
              "alternatives":["Teste orgânico por 7 dias", "Campanha Search de baixa verba"],
              "recommended_objective":"Validar a oferta em um teste controlado antes de escalar mídia paga",
              "confidence":0.84,
              "assumptions":["Ainda não existe prova de conversão para essa oferta"]
            }''',
            provider=self.name,
            model=self.model,
        )


class FakeRouter:
    def primary(self):
        return FakeProvider()


@pytest.mark.asyncio
async def test_strategic_advisor_can_reframe_weak_idea():
    advisor = StrategicAdvisor(FakeRouter())
    result = await advisor.assess("escale a campanha", "baixo histórico de conversão")
    assert result.verdict == "adjust"
    assert result.recommended_objective
    assert result.confidence == 0.84
    assert len(result.reasons) == 2


def test_concise_advice_is_direct():
    assessment = StrategicAssessment(
        verdict="do_not_recommend",
        recommendation="Eu não faria essa campanha agora.",
        reasons=["Margem insuficiente", "Canal não validado"],
        alternatives=["Teste orgânico", "Remarketing"],
        recommended_objective=None,
        confidence=0.8,
        assumptions=[],
    )
    text = assessment.concise_text()
    assert "Eu não faria" in text
    assert "Motivo:" in text
    assert "Melhores opções:" in text


def test_strategic_override_requires_explicit_language():
    assert not Orchestrator._strategic_override_like("ok")
    assert Orchestrator._strategic_override_like("execute mesmo assim")
    assert Orchestrator._strategic_override_like("quero prosseguir mesmo assim")
