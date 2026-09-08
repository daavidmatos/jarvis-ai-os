# JARVIS AI OS v0.3

OpenAI-first personal AI orchestration system with autonomous model and tool routing.

## Core behavior

JARVIS now has a fixed cognitive hierarchy:

1. **OpenAI is the primary brain** for planning and general reasoning.
2. JARVIS decomposes the user's request into tasks.
3. The Model Router automatically decides whether a task stays on OpenAI or is delegated to an available specialist (Anthropic/Claude or Google/Gemini).
4. Agents may call allowed LOW/MEDIUM-risk tools autonomously.
5. HIGH-risk side effects remain approval-gated; CRITICAL actions remain blocked.
6. When a specialist is used, OpenAI can synthesize the final user-facing answer.

The user does **not** choose a provider for each prompt.

## First run

```bash
git pull
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn jarvis.api:app --reload --port 8000
```

Open:

```text
http://localhost:8000
```

On the first run, the interface asks for an **OpenAI API key once**. It validates the key and stores it locally in:

```text
~/.config/jarvis/secrets.json
```

with restrictive filesystem permissions. The key is not committed to Git. Environment variables remain supported as an override for servers/containers.

After the one-time setup, OpenAI is used automatically whenever JARVIS starts.

## Optional specialist AIs

Claude and Gemini are optional. Configure them once through the same setup interface. If present, the router may delegate tasks automatically according to capability/fit. If absent, OpenAI handles those tasks itself.

## Current capabilities

- FastAPI API and browser chat UI
- OpenAI Responses API as primary cognition
- autonomous provider routing
- Research, Coding, Creative, Data, Operations and General agents
- safe multi-step tool loop
- web search/fetch
- calculator
- workspace file read/write
- time tool
- persistent conversations, workflows, tasks, memory and audit log
- approval gate for high-risk tools
- SQLite locally; PostgreSQL + Redis in Docker
- GitHub Actions CI

## Docker

```bash
cp .env.example .env
docker compose up --build
```

The Docker setup persists the one-time local credential store in the `jarvis_config` named volume.

## API

- `GET /health`
- `GET /v1/setup/status`
- `POST /v1/setup/providers/{provider}`
- `DELETE /v1/setup/providers/{provider}`
- `POST /v1/chat`
- `GET /v1/models`
- `GET /v1/tools`
- `GET /v1/workflows/{id}`
- `GET /v1/memory`
- `POST /v1/memory`
- `WS /ws/jarvis`

## Security boundary

The current credential store is appropriate for a local, single-user MVP. Before exposing JARVIS publicly, add authentication, TLS, secret-manager integration, CSRF protections, rate limits and a hardened remote setup flow.

Host-level shell/computer control, payments and destructive actions are not enabled by this version.

## Next milestones

1. MCP registry and dynamic tool discovery.
2. pgvector semantic memory.
3. background workers for long-running workflows.
4. Gmail, Calendar, Drive and GitHub OAuth tools.
5. richer approvals dashboard.
6. sandboxed coding/computer-use VM.
7. realtime voice.
8. scheduler and condition-based proactive workflows.
