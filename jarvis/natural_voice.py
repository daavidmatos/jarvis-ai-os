from __future__ import annotations

import base64
import io
import re
import wave

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


class NaturalVoiceService:
    """Natural pt-BR speech through Gemini TTS, with the API key kept server-side."""

    @property
    def available(self) -> bool:
        return bool(settings.google_api_key)

    def status(self) -> dict:
        return {
            "available": self.available,
            "provider": "google_gemini_tts",
            "model": settings.google_tts_model,
            "voice": settings.google_tts_voice,
            "language": "pt-BR",
        }

    async def synthesize(self, text: str, *, progress: bool = False) -> bytes:
        if not self.available:
            raise NaturalVoiceError("Gemini API key is not configured")
        clean = _clean_text(text)
        if not clean:
            raise NaturalVoiceError("No speakable text")
        # Keep spoken answers concise. The complete text remains visible in the terminal.
        limit = 360 if progress else 900
        if len(clean) > limit:
            cut = clean[:limit]
            last = max(cut.rfind("."), cut.rfind("?"), cut.rfind("!"))
            clean = cut[: last + 1] if last > 180 else cut.rstrip() + "."
            clean += " O restante está na tela, senhor."

        direction = (
            "Fale exatamente a mensagem abaixo em português brasileiro do Brasil. "
            "Use sotaque brasileiro neutro, voz masculina madura, natural, calma e segura. "
            "Ritmo levemente pausado, dicção clara, pequenas pausas naturais entre frases, "
            "sem soar robótico, sem exagero teatral e sem sotaque de Portugal. "
            "Não traduza e não acrescente conteúdo.\n\nMensagem: " + clean
        )
        body = {
            "contents": [{"parts": [{"text": direction}]}],
            "generationConfig": {
                "responseModalities": ["AUDIO"],
                "speechConfig": {
                    "voiceConfig": {
                        "prebuiltVoiceConfig": {"voiceName": settings.google_tts_voice}
                    }
                },
            },
        }
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{settings.google_tts_model}:generateContent"
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
                detail = response.text[:500]
                raise NaturalVoiceError(
                    f"Gemini TTS returned HTTP {response.status_code}: {detail}"
                )
            payload = response.json()
            part = payload.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0]
            inline = part.get("inlineData") or part.get("inline_data") or {}
            data = inline.get("data")
            if not data:
                raise NaturalVoiceError("Gemini TTS returned no audio")
            pcm = base64.b64decode(data)
            return pcm16_to_wav(pcm)
        except httpx.HTTPError as exc:
            raise NaturalVoiceError(f"Gemini TTS network error: {exc}") from None
        except (ValueError, KeyError, IndexError) as exc:
            raise NaturalVoiceError(f"Invalid Gemini TTS response: {exc}") from None


natural_voice = NaturalVoiceService()
