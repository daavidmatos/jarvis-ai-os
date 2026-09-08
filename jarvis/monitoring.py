from __future__ import annotations

import asyncio
import time

from jarvis.config import settings
from jarvis.events import ProactiveEventService
from jarvis.google_workspace import google_workspace


class GoogleMonitoringService:
    """Keeps Google push watches alive while the JARVIS server is running."""

    def __init__(self, events: ProactiveEventService):
        self.events = events
        self._task: asyncio.Task | None = None
        self._last_gmail_watch = 0.0

    def start(self) -> None:
        if not settings.enable_google_monitoring or self._task is not None:
            return
        self._task = asyncio.create_task(self._loop())

    async def _loop(self) -> None:
        while True:
            try:
                await self.ensure_watches()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.events.emit(
                    "google",
                    "monitor.error",
                    {"message": str(exc)},
                )
            await asyncio.sleep(max(settings.google_monitor_interval_seconds, 3600))

    async def ensure_watches(self) -> dict:
        status = google_workspace.status()
        result = {"connected": status["connected"], "gmail": None, "calendar": None}
        if not status["connected"]:
            return result

        # Gmail watches expire within seven days; Google recommends renewing daily.
        if settings.gmail_pubsub_topic and time.time() - self._last_gmail_watch >= 24 * 3600:
            result["gmail"] = await google_workspace.gmail_watch()
            self._last_gmail_watch = time.time()

        # Calendar notification channels expire. Renew only when missing or near expiry.
        if settings.public_base_url.startswith("https://"):
            state = google_workspace._read_json(google_workspace.monitor_path).get("calendar", {})
            expiration_ms = int(state.get("expiration") or 0)
            renew_before_ms = int((time.time() + 24 * 3600) * 1000)
            if not expiration_ms or expiration_ms <= renew_before_ms:
                result["calendar"] = await google_workspace.calendar_watch()
        return result
