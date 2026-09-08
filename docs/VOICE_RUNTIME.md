# JARVIS mobile voice runtime

The mobile UI must not depend exclusively on the Web Speech API because browser speech recognition has limited availability and can behave inconsistently on iOS.

## Output (JARVIS -> owner)

- Primary: Gemini `gemini-3.1-flash-tts-preview` through the current Interactions API.
- Voice: `Gacrux`, prompted for neutral Brazilian Portuguese, calm mature delivery and measured pacing.
- Playback: a persistent HTMLAudioElement is primed by a user gesture on iOS before asynchronous TTS audio arrives.
- Fallback: browser speech synthesis only when an exact `pt-BR` voice exists. Never intentionally fall back to `pt-PT`.

## Input (owner -> JARVIS)

- Primary: `getUserMedia` + `MediaRecorder` records a short command in the browser.
- Tap MIC once to start recording and again to stop.
- The recording is sent server-side as base64 to the low-risk `voice.transcribe` tool.
- Short audio is transcribed with the configured Gemini multimodal STT model (`gemini-3.5-flash-lite` by default) using inline audio.
- The transcript is inserted into the text box for review before sending.
- Web Speech recognition remains only as a last-resort fallback when MediaRecorder is unavailable.

## Privacy and limits

- Gemini API keys stay server-side.
- Microphone tracks are stopped immediately after recording.
- Audio is kept only in browser memory long enough to transcribe; JARVIS does not persist microphone recordings.
- Recordings are capped at 30 seconds in the UI and 8 MB server-side by default.
