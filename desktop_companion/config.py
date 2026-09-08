from __future__ import annotations

import json
import os
import socket
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlencode, urlparse, urlunparse
from uuid import uuid4


@dataclass
class CompanionConfig:
    server_url: str = "http://localhost:8000"
    token: str = ""
    client_id: str = ""
    screenshots: bool = False
    state_interval: float = 2.0
    capture_interval: float = 5.0
    max_frame_width: int = 1280
    jpeg_quality: int = 68

    @property
    def data_dir(self) -> Path:
        return Path("~/.config/jarvis/desktop-companion").expanduser().resolve()

    @property
    def config_path(self) -> Path:
        return Path("~/.config/jarvis/desktop-bridge.json").expanduser().resolve()

    def ensure_client_id(self) -> str:
        if not self.client_id:
            host = socket.gethostname().strip() or "desktop"
            self.client_id = f"{host}-{uuid4().hex[:10]}"
        return self.client_id

    def websocket_url(self, *, allow_insecure_remote: bool = False) -> str:
        raw = self.server_url.strip().rstrip("/")
        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https", "ws", "wss"}:
            raise ValueError("server_url must start with http://, https://, ws:// or wss://")
        scheme = {"http": "ws", "https": "wss", "ws": "ws", "wss": "wss"}[parsed.scheme]
        host = (parsed.hostname or "").lower()
        local = host in {"localhost", "127.0.0.1", "::1"}
        if scheme == "ws" and not local and not allow_insecure_remote:
            raise ValueError("Refusing insecure remote Desktop Bridge connection. Use HTTPS/WSS.")
        path = (parsed.path.rstrip("/") if parsed.path not in {"", "/"} else "") + "/ws/desktop-bridge"
        query = urlencode({"token": self.token}) if self.token else ""
        return urlunparse((scheme, parsed.netloc, path, "", query, ""))

    def save(self) -> Path:
        self.ensure_client_id()
        path = self.config_path
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(path.parent, 0o700)
        except OSError:
            pass
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return path

    @classmethod
    def load(cls) -> "CompanionConfig":
        path = Path("~/.config/jarvis/desktop-bridge.json").expanduser().resolve()
        if not path.exists():
            cfg = cls()
            cfg.ensure_client_id()
            return cfg
        raw = json.loads(path.read_text(encoding="utf-8"))
        known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__}
        cfg = cls(**known)
        cfg.ensure_client_id()
        return cfg
