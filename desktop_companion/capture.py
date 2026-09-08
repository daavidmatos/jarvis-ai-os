from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4


@dataclass
class CapturedFrame:
    frame_id: str
    mime_type: str
    width: int
    height: int
    data_b64: str
    captured_at: str

    def to_message(self) -> dict:
        return {
            "type": "frame",
            "frame_id": self.frame_id,
            "mime_type": self.mime_type,
            "width": self.width,
            "height": self.height,
            "data_b64": self.data_b64,
            "captured_at": self.captured_at,
        }


def capture_primary_monitor(max_width: int = 1280, jpeg_quality: int = 68) -> CapturedFrame:
    """Capture a bounded primary-monitor frame.

    mss and Pillow are imported lazily so the server/CI does not need desktop
    graphics dependencies. The companion package installs them separately.
    """
    try:
        import mss
        from PIL import Image
    except ImportError as exc:
        raise RuntimeError(
            "Desktop screenshots require requirements-desktop.txt (mss + Pillow)."
        ) from exc

    with mss.mss() as sct:
        monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        raw = sct.grab(monitor)
        image = Image.frombytes("RGB", raw.size, raw.rgb)
    if image.width > max_width:
        ratio = max_width / image.width
        image = image.resize((max_width, max(1, int(image.height * ratio))))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=max(35, min(int(jpeg_quality), 85)), optimize=True)
    data = buffer.getvalue()
    return CapturedFrame(
        frame_id=str(uuid4()),
        mime_type="image/jpeg",
        width=image.width,
        height=image.height,
        data_b64=base64.b64encode(data).decode("ascii"),
        captured_at=datetime.now(timezone.utc).isoformat(),
    )
