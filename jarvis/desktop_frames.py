from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
from typing import Any

from jarvis.config import settings


class DesktopFrameError(RuntimeError):
    pass


class DesktopFrameStore:
    def __init__(self, retention: int | None = None):
        self._retention_override = retention

    @property
    def retention(self) -> int:
        value = (
            self._retention_override
            if self._retention_override is not None
            else getattr(settings, "desktop_frame_retention", 2)
        )
        return max(1, int(value))

    @property
    def root(self) -> Path:
        p = settings.workspace_path / ".desktop_frames"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @staticmethod
    def _client_dir_name(client_id: str) -> str:
        return hashlib.sha256(client_id.encode("utf-8")).hexdigest()[:20]

    def _dir(self, client_id: str) -> Path:
        p = self.root / self._client_dir_name(client_id)
        p.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(p, 0o700)
        except OSError:
            pass
        return p

    @staticmethod
    def _extension(mime_type: str) -> str:
        return {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}.get(mime_type, "")

    def store(self, client_id: str, frame_id: str, mime_type: str, data_b64: str) -> dict[str, Any]:
        ext = self._extension(str(mime_type))
        if not ext:
            raise DesktopFrameError("Unsupported frame MIME type")
        try:
            data = base64.b64decode(data_b64, validate=True)
        except Exception as exc:
            raise DesktopFrameError("Invalid base64 desktop frame") from exc
        max_bytes = int(getattr(settings, "desktop_frame_max_bytes", 3_000_000))
        if len(data) > max_bytes:
            raise DesktopFrameError(f"Desktop frame exceeds {max_bytes} bytes")
        safe_id = "".join(ch for ch in str(frame_id) if ch.isalnum() or ch in {"-", "_"})[:80]
        if not safe_id:
            raise DesktopFrameError("Invalid frame id")
        folder = self._dir(client_id)
        path = folder / f"{safe_id}{ext}"
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
        files = sorted(
            [x for x in folder.iterdir() if x.is_file() and not x.name.endswith(".tmp")],
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )
        for old in files[self.retention :]:
            try:
                old.unlink()
            except OSError:
                pass
        storage_key = f"{self._client_dir_name(client_id)}/{path.name}"
        return {"storage_key": storage_key, "bytes": len(data)}

    def read(self, storage_key: str) -> bytes:
        key = str(storage_key).replace("\\", "/").strip("/")
        parts = key.split("/")
        if len(parts) != 2 or any(part in {"", ".", ".."} for part in parts):
            raise DesktopFrameError("Invalid frame storage key")
        path = (self.root / parts[0] / parts[1]).resolve()
        root = self.root.resolve()
        if root not in path.parents:
            raise DesktopFrameError("Frame path escaped storage root")
        if not path.exists() or not path.is_file():
            raise DesktopFrameError("Desktop frame not found")
        return path.read_bytes()


desktop_frames = DesktopFrameStore()
