from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class Check:
    name: str
    ok: bool
    detail: str


def _request(base_url: str, path: str, *, method: str = "GET", body: dict[str, Any] | None = None):
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(base_url.rstrip("/") + path, data=data, headers=headers, method=method)
    try:
        with urlopen(req, timeout=8) as response:
            raw = response.read()
            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type:
                payload = json.loads(raw.decode("utf-8"))
            else:
                payload = raw.decode("utf-8", errors="replace")
            return response.status, payload
    except HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw.decode("utf-8"))
        except Exception:
            payload = raw.decode("utf-8", errors="replace")
        return exc.code, payload


def _wait_for_server(base_url: str, seconds: float) -> None:
    deadline = time.monotonic() + seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            status, _ = _request(base_url, "/health")
            if status == 200:
                return
        except (URLError, TimeoutError, ConnectionError) as exc:
            last_error = exc
        time.sleep(0.4)
    raise RuntimeError(f"JARVIS did not become ready at {base_url}: {last_error or 'timeout'}")


def _is_dict(value: Any) -> bool:
    return isinstance(value, dict)


def run(base_url: str, *, wait_seconds: float = 0.0, expect_unconfigured: bool = False) -> list[Check]:
    if wait_seconds:
        _wait_for_server(base_url, wait_seconds)

    checks: list[Check] = []

    status, home = _request(base_url, "/")
    checks.append(Check("web UI", status == 200 and isinstance(home, str) and "JARVIS" in home.upper(), f"HTTP {status}"))

    status, health = _request(base_url, "/health")
    health_ok = (
        status == 200
        and _is_dict(health)
        and health.get("status") == "ok"
        and health.get("primary_provider") == "openai"
    )
    checks.append(Check("health endpoint", health_ok, f"HTTP {status}; ready={health.get('ready') if _is_dict(health) else '?'}"))

    status, setup = _request(base_url, "/v1/setup/status")
    setup_ok = status == 200 and _is_dict(setup) and "primary" in setup and "collaboration" in setup
    checks.append(Check("setup diagnostics", setup_ok, f"HTTP {status}"))

    status, integrations = _request(base_url, "/v1/integrations/status")
    expected_integrations = {"google_workspace", "places", "google_ads", "instagram", "fuel", "desktop_bridge"}
    integrations_ok = status == 200 and _is_dict(integrations) and expected_integrations.issubset(integrations)
    checks.append(Check("integration diagnostics", integrations_ok, f"HTTP {status}"))

    status, desktop = _request(base_url, "/v1/desktop/status")
    desktop_ok = status == 200 and _is_dict(desktop) and isinstance(desktop.get("connected"), bool)
    checks.append(Check("desktop bridge diagnostics", desktop_ok, f"HTTP {status}; connected={desktop.get('connected') if _is_dict(desktop) else '?'}"))

    status, workspaces = _request(base_url, "/v1/workspaces")
    workspaces_ok = status == 200 and _is_dict(workspaces) and isinstance(workspaces.get("catalog"), list)
    checks.append(Check("universal workbench catalog", workspaces_ok, f"HTTP {status}"))

    if expect_unconfigured:
        status, chat = _request(base_url, "/v1/chat", method="POST", body={"message": "runtime smoke test"})
        detail = chat.get("detail") if _is_dict(chat) else None
        setup_required = (
            status == 503
            and _is_dict(detail)
            and detail.get("code") == "setup_required"
            and detail.get("primary_provider") == "openai"
        )
        checks.append(Check("no fake AI fallback", setup_required, f"HTTP {status}"))

    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description="JARVIS live HTTP runtime smoke test")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--wait", type=float, default=0.0, help="seconds to wait for the server")
    parser.add_argument(
        "--expect-unconfigured",
        action="store_true",
        help="verify that an instance without OpenAI returns setup_required instead of a fake answer",
    )
    args = parser.parse_args()

    try:
        checks = run(args.base_url, wait_seconds=args.wait, expect_unconfigured=args.expect_unconfigured)
    except Exception as exc:
        print(f"[FAIL] runtime bootstrap: {exc}")
        return 2

    for check in checks:
        marker = "PASS" if check.ok else "FAIL"
        print(f"[{marker}] {check.name}: {check.detail}")
    failed = [c for c in checks if not c.ok]
    print(f"\nJARVIS runtime smoke: {len(checks) - len(failed)}/{len(checks)} checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
