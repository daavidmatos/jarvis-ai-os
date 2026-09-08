# JARVIS AI OS v0.2

Executable MVP of a provider-agnostic personal AI orchestration system.

## Current capabilities

- Web chat UI and FastAPI API
- Persistent conversations, workflows, tasks, memory and audit log
- Planner that creates structured task plans
- Model Router with OpenAI, Anthropic, Google and deterministic local fallback
- Research, Coding, Creative, Data, Operations and General agents
- Tools: safe calculator, file read/write sandbox, public web fetch, optional live web search, time
- Policy engine with LOW / MEDIUM / HIGH / CRITICAL risk levels
- Workflow retries, dependency resolution and verification
- WebSocket endpoint
- SQLite for zero-setup local execution; PostgreSQL + Redis in Docker
- GitHub Actions CI

## Important scope boundary

This is a real executable foundation, not a finished Iron-Man-level autonomous agent. High-impact integrations such as sending email, production changes, payments, full computer control, voice wake word and long-running distributed workers must be added behind approval and sandbox layers.

## Run locally

```bash
cp .env.example .env
pip install -r requirements.txt
uvicorn jarvis.api:app --reload --port 8000
```

Then open http://localhost:8000.

It will run even without an AI API key using the deterministic local fallback. For real model responses, set at least one of:

```env
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
GOOGLE_API_KEY=...
```

For live research, set either:

```env
TAVILY_API_KEY=...
# or
SERPER_API_KEY=...
```

## Docker

```bash
cp .env.example .env
docker compose up --build
```

Docker switches the database to PostgreSQL automatically and also starts Redis.

## API

- `GET /health`
- `POST /v1/chat`
- `GET /v1/models`
- `GET /v1/tools`
- `GET /v1/workflows/{id}`
- `GET /v1/memory`
- `POST /v1/memory`
- `WS /ws/jarvis`

Example:

```bash
curl -X POST http://localhost:8000/v1/chat \
  -H 'content-type: application/json' \
  -d '{"message":"Pesquise o mercado de barras energéticas e resuma oportunidades."}'
```

## Architecture

```text
Web / API / WebSocket
        ↓
   Orchestrator
   ├─ Memory
   ├─ Planner
   ├─ Model Router
   ├─ Agent Manager
   └─ Workflow Engine
        ├─ Policy
        ├─ Tools
        └─ Verification
             ↓
OpenAI / Anthropic / Gemini / local fallback
```

## Next engineering milestones

1. Add real MCP client/server registry.
2. Add pgvector embeddings and semantic retrieval.
3. Add queue workers for long-running workflows.
4. Add OAuth connectors for Gmail/Calendar/GitHub/Drive.
5. Add approval dashboard and signed action tokens.
6. Add code execution and computer-use VM sandbox.
7. Add realtime voice/STT/TTS.
8. Add scheduler and condition-based autonomous workflows.
9. Add evaluation harness for model routing.

## Security defaults

- Secrets stay in environment variables, never model prompts.
- Files are restricted to `workspace/`.
- Web fetch blocks local/private-network targets.
- HIGH-risk tools require approval by policy.
- CRITICAL tools are blocked.
- Autonomy is disabled by default.
