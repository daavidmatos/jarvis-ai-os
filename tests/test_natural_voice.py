from jarvis.natural_voice import _clean_text, pcm16_to_wav
from jarvis.tools.registry import ToolRegistry


def test_clean_voice_text_removes_markup_and_urls():
    text = _clean_text("**Senhor**, veja https://example.com agora.\nTudo certo.")
    assert text == "Senhor , veja agora. Tudo certo."


def test_pcm16_to_wav_builds_valid_wave_header():
    wav = pcm16_to_wav(b"\x00\x00" * 16)
    assert wav[:4] == b"RIFF"
    assert wav[8:12] == b"WAVE"
    assert len(wav) > 44


def test_natural_voice_tool_is_registered():
    registry = ToolRegistry()
    assert "voice.synthesize" in registry.tools
