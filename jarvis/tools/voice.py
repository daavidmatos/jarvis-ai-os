from __future__ import annotations

import base64

from jarvis.natural_voice import natural_voice
from jarvis.schemas import RiskLevel
from jarvis.tools.base import Tool


class NaturalVoiceTool(Tool):
    name = "voice.synthesize"
    description = "Generate natural Brazilian Portuguese JARVIS speech as WAV audio for the owner UI."
    # This is intentionally not exposed to autonomous agent planning because the
    # base64 audio payload is large. The authenticated owner UI invokes it directly.
    risk = RiskLevel.HIGH
    requires_approval = True

    async def run(self, text: str, progress: bool = False):
        audio = await natural_voice.synthesize(text, progress=progress)
        return {
            "mime_type": "audio/wav",
            "audio_base64": base64.b64encode(audio).decode("ascii"),
            "voice": natural_voice.status(),
        }
