#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON="$ROOT/.venv/bin/python"
fi

if ! "$PYTHON" -c 'import fastapi, uvicorn' >/dev/null 2>&1; then
  echo "[FAIL] Dependências do JARVIS não estão instaladas neste Python."
  echo "Ative a .venv e rode: python -m pip install -r requirements.txt"
  exit 2
fi

echo "== JARVIS acceptance test =="
echo "Python: $($PYTHON --version 2>&1)"
echo

echo "[1/3] Testes automatizados"
"$PYTHON" -m pytest

echo
echo "[2/3] Subindo API real em localhost:8000"
LOG="${TMPDIR:-/tmp}/jarvis-acceptance-$$.log"
"$PYTHON" -m uvicorn jarvis.api:app --host 127.0.0.1 --port 8000 >"$LOG" 2>&1 &
PID=$!
cleanup() {
  kill "$PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo
echo "[3/3] Smoke test HTTP"
if ! "$PYTHON" scripts/runtime_smoke.py --base-url http://127.0.0.1:8000 --wait 25; then
  echo
  echo "--- uvicorn log ---"
  cat "$LOG" || true
  exit 1
fi

echo
echo "[PASS] Base local do JARVIS está operacional."
echo "Próximo teste: OpenAI real, Google e Desktop Companion com as credenciais locais já configuradas."
