from __future__ import annotations

import base64
import io
import re
import wave
from typing import Any

import httpx

from jarvis.config import settings


class NaturalVoiceError(RuntimeError):
    pass


def _clean_text(text: str) -> str:
    value = re.sub(r"https?://\S+", "", str(text or ""))
    value = re.sub(r"[`*_#>|]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def pcm16_to_wav(pcm: bytes, sample_rate: int = 24000) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


def _audio_mime_for_gemini(mime_type: str | None) -> str:
    value = (mime_type or "").lower().split(";", 1)[0].strip()
    aliases = {
        "audio/mp4": "audio/m4a",
        "audio/x-m4a": "audio/m4a",
        "audio/x-wav": "audio/wav",
        "audio/webm": "audio/webm",
        "audio/ogg": "audio/ogg",
        "audio/mpeg": "audio/mpeg",
        "audio/mp3": "audio/mp3",
        "audio/aac": "audio/aac",
        "audio/m4a": "audio/m4a",
        "audio/wav": "audio/wav",
        "audio/flac": "audio/flac",
    }
    return aliases.get(value, value or "audio/webm")


def _extract_audio_data(payload: Any) -> str | None:
    """Find audio bytes in Interactions API responses without depending on SDK helpers."""
    if isinstance(payload, dict):
        output_audio = payload.get("output_audio")
        if isinstance(output_audio, dict) and isinstance(output_audio.get("data"), str):
            return output_audio["data"]
        if payload.get("type") == "audio" and isinstance(payload.get("data"), str):
            return payload["data"]
        mime = str(payload.get("mime_type") or payload.get("mimeType") or "")
        if mime.startswith("audio/") and isinstance(payload.get("data"), str):
            return payload["data"]
        for value in payload.values():
            found = _extract_audio_data(value)
            if found:
                return found
    elif isinstance(payload, list):
        for value in payload:
            found = _extract_audio_data(value)
            if found:
                return found
    return None


def _extract_generate_content_text(payload: dict[str, Any]) -> str:
    rows: list[str] = []
    for candidate in payload.get("candidates") or []:
        content = candidate.get("content") if isinstance(candidate, dict) else None
        parts = content.get("parts") if isinstance(content, dict) else None
        for part in parts or []:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                value = part["text"].strip()
                if value:
                    rows.append(value)
    return "\n".join(rows).strip()


class NaturalVoiceService:
    """Natural pt-BR TTS and reliable short-command transcription via Gemini."""

    @property
    def available(self) -> bool:
        return bool(settings.google_api_key)

    def status(self) -> dict:
        return {
            "available": self.available,
            "provider": "google_gemini",
            "tts_model": settings.google_tts_model,
            "stt_model": settings.google_stt_model,
            "voice": settings.google_tts_voice,
            "language": "pt-BR",
        }

    async def synthesize(self, text: str, *, progress: bool = False) -> bytes:
        if not self.available:
            raise NaturalVoiceError("Gemini API key is not configured")
        clean = _clean_text(text)
        if not clean:
            raise NaturalVoiceError("No speakable text")

        limit = 360 if progress else 900
        if len(clean) > limit:
            cut = clean[:limit]
            last = max(cut.rfind("."), cut.rfind("?"), cut.rfind("!"))
            clean = cut[: last + 1] if last > 180 else cut.rstrip() + "."
            clean += " O restante está na tela, senhor."

        direction = (
            "Fale exatamente a mensagem abaixo em português brasileiro do Brasil. "
            "Use sotaque brasileiro neutro, voz masculina madura, natural, calma e segura. "
            "Ritmo levemente pausado, dicção clara e pequenas pausas naturais entre frases. "
            "Não use sotaque de Portugal. Não traduza e não acrescente conteúdo.\n\n"
            "Mensagem: " + clean
        )
        body = {
            "model": settings.google_tts_model,
            "input": direction,
            "response_format": {"type": "audio"},
            "generation_config": {
                "speech_config": [{"voice": settings.google_tts_voice}],
            },
        }
        try:
            async with httpx.AsyncClient(timeout=35) as client:
                response = await client.post(
                    "https://generativelanguage.googleapis.com/v1beta/interactions",
                    headers={
                        "x-goog-api-key": settings.google_api_key,
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
            if response.status_code >= 400:
                raise NaturalVoiceError(
                    f"Gemini TTS returned HTTP {response.status_code}: {response.text[:500]}"
                )
            payload = response.json()
            encoded = _extract_audio_data(payload)
            if not encoded:
                raise NaturalVoiceError("Gemini TTS returned no audio")
            return pcm16_to_wav(base64.b64decode(encoded))
        except httpx.HTTPError as exc:
            raise NaturalVoiceError(f"Gemini TTS network error: {exc}") from None
        except (ValueError, KeyError, IndexError) as exc:
            raise NaturalVoiceError(f"Invalid Gemini TTS response: {exc}") from None

    async def transcribe(self, audio: bytes, mime_type: str | None) -> str:
        if not self.available:
            raise NaturalVoiceError("Gemini API key is not configured")
        if not audio:
            raise NaturalVoiceError("No audio received")
        if len(audio) > settings.voice_max_audio_bytes:
            raise NaturalVoiceError("Audio is too large for a short JARVIS command")

        mime = _audio_mime_for_gemini(mime_type)
        encoded = base64.b64encode(audio).decode("ascii")
        body = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": (
                                "Transcreva somente a fala desta gravação. "
                                "O usuário fala principalmente português brasileiro. "
                                "Preserve nomes próprios, marcas e termos como JARVIS, Fuel, Figma, Uber, "
                                "Google Ads, Gmail e Shopping Tijuca quando forem audíveis. "
                                "Aplique pontuação natural e retorne apenas o texto transcrito, sem aspas, "
                                "sem explicações e sem responder ao conteúdo."
                            )
                        },
                        {"inlineData": {"mimeType": mime, "data": encoded}},
                    ]
                }
            ],
            "generationConfig": {"temperature": 0},
        }
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.google_stt_model}:generateContent"
        )
        try:
            async with httpx.AsyncClient(timeout=35) as client:
                response = await client.post(
                    url,
                    headers={
                        "x-goog-api-key": settings.google_api_key,
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
            if response.status_code >= 400:
                raise NaturalVoiceError(
                    f"Gemini transcription returned HTTP {response.status_code}: {response.text[:500]}"
                )
            text = _extract_generate_content_text(response.json())
            if not text:
                raise NaturalVoiceError("Gemini transcription returned no text")
            return text
        except httpx.HTTPError as exc:
            raise NaturalVoiceError(f"Gemini transcription network error: {exc}") from None
        except (ValueError, KeyError, IndexError) as exc:
            raise NaturalVoiceError(f"Invalid Gemini transcription response: {exc}") from None


natural_voice = NaturalVoiceService()
