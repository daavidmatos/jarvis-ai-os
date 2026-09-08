from jarvis.voice_persona import ensure_senhor


def test_ensure_senhor_adds_preferred_address():
    assert ensure_senhor("Posso ajudar com isso.").startswith("Senhor,")


def test_ensure_senhor_does_not_duplicate():
    assert ensure_senhor("Sim, senhor. Já verifiquei.") == "Sim, senhor. Já verifiquei."


def test_ensure_senhor_handles_empty():
    assert ensure_senhor("") == "Sim, senhor."
