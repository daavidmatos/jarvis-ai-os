from jarvis.natural_voice import (
    _audio_mime_for_gemini,
    _clean_text,
    _extract_audio_data,
    _extract_generate_content_text,
    pcm16_to_wav,
)
from jarvis.tools.registry import ToolRegistry


def test_clean_voice_text_removes_markup_and_urls():
    text = _clean_text("**Senhor**, veja https://example.com agora.\nTudo certo.")
    assert text == "Senhor , veja agora. Tudo certo."


def test_pcm16_to_wav_builds_valid_wave_header():
    wav = pcm16_to_wav(b"\x00\x00" * 16)
    assert wav[:4] == b"RIFF"
    assert wav[8:12] == b"WAVE"
    assert len(wav) > 44


def test_interactions_audio_parser_finds_output_audio():
    payload = {"outputs": [{"type": "audio", "data": "YWJj"}]}
    assert _extract_audio_data(payload) == "YWJj"


def test_generate_content_text_parser_extracts_transcript():
    payload = {
        "candidates": [
            {"content": {"parts": [{"text": "Jarvis, abra o Uber."}]}}
        ]
    }
    assert _extract_generate_content_text(payload) == "Jarvis, abra o Uber."


def test_ios_media_recorder_mp4_is_normalized_for_gemini():
    assert _audio_mime_for_gemini("audio/mp4") == "audio/m4a"
    assert _audio_mime_for_gemini("audio/webm;codecs=opus") == "audio/webm"


def test_voice_tools_are_registered():
    registry = ToolRegistry()
    assert "voice.synthesize" in registry.tools
    assert "voice.transcribe" in registry.tools
