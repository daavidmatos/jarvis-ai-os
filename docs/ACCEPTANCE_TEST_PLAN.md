# JARVIS acceptance test plan

This plan separates code/runtime validation from tests that require a physical computer, real external accounts, or desktop applications.

## Gate 0 — repository/runtime (can run in GitHub Actions)

Pass criteria:
- Python dependencies install.
- `pytest` passes.
- FastAPI/Uvicorn boots as a real HTTP server.
- `/`, `/health`, `/v1/setup/status`, `/v1/integrations/status`, `/v1/desktop/status`, and `/v1/workspaces` respond with the expected shapes.
- Without an OpenAI credential, `/v1/chat` returns structured `setup_required`; it must not fabricate a local AI answer.

Automated by CI and `scripts/runtime_smoke.py`.

## Gate 1 — local computer baseline

Run from the repository:

```bash
bash scripts/local_acceptance_test.sh
```

Pass criteria:
- Existing virtual environment works.
- Unit/integration tests pass on the user's machine.
- Uvicorn boots locally.
- HTTP runtime smoke checks pass.
- Web UI opens at `http://localhost:8000`.

## Gate 2 — OpenAI Core real inference

Pass criteria:
- First-run OpenAI setup validates the key without exposing it.
- `/v1/setup/status` reports OpenAI primary available.
- A simple chat request returns a real OpenAI answer.
- Planner can create a structured task/workflow.
- No mock/local response is used.
- Provider/model metadata is shown correctly.

Suggested prompts:
- `JARVIS, o que você consegue fazer atualmente?`
- `Pesquise uma informação atual na internet e cite a fonte.`
- `Calcule 27 * 43 e explique em uma frase.`

## Gate 3 — Google Workspace

Pass criteria:
- OAuth completes once and persists offline access.
- Gmail search/read works.
- Gmail draft works; send remains approval/permission controlled.
- Calendar list/free-busy works.
- Creating an event respects the configured approval scope.
- Gmail/Calendar monitoring can be started after the server has a public HTTPS callback.

Never paste OAuth secrets or refresh tokens into chat/logs.

## Gate 4 — local assistant / Places

Pass criteria:
- Mobile/browser location permission works.
- Nearby-place search returns real Google Places data.
- Ranking considers rating confidence/review volume rather than rating alone.
- Google Maps route action opens the selected destination.

## Gate 5 — Mission mode

Pass criteria:
- `Crie uma campanha...` proposes a mission before execution.
- Strategic Advisor can recommend changing or rejecting a weak strategy.
- `OK` approves only the mission envelope.
- Spend/publish/message/computer-control limits are enforced.
- Audit trail records actual tool use.

## Gate 6 — Universal Workbench

Pass criteria:
- `Vamos trabalhar...` enters collaborative mode rather than autonomous mission mode.
- Docs/Sheets/Trello can be inspected.
- A concrete edit authorizes only that edit.
- `Vamos mudar...` without a concrete mutation does not silently change data.

## Gate 7 — Desktop Companion

Pass criteria:
- Companion connects over authenticated WebSocket.
- `/v1/desktop/status` shows the local machine.
- App detection reports the real active application.
- Screenshots remain OFF until explicitly enabled.
- When enabled, a visual snapshot can be analyzed without a public image URL.
- Reconnection works after stopping/restarting the companion.

## Gate 8 — Blender

Pass criteria:
- JARVIS add-on is loaded.
- Scene/object/camera state reaches the Workbench.
- `crie um cubo` creates a real cube.
- `mova o cubo` changes the actual object.
- `desfazer` restores the previous state.
- No arbitrary Python/shell command can be injected through a JARVIS desktop action.

## Gate 9 — Figma / creative editors

Test each editor independently. Code/CI passing is not equivalent to a successful editor integration.

Figma target test:
- Load the JARVIS plugin in a real editable Figma file.
- Ask: `crie uma landing page simples para uma marca de creme`.
- Verify that real Figma nodes are created.
- Ask for one specific edit and verify only that requested change.

Photoshop / Illustrator / After Effects:
- Test only on a supported computer with the real application installed and the appropriate JARVIS plugin/bridge loaded.
- Verify document/project state, one bounded edit, undo, and refusal of unsupported/arbitrary code.

## Gate 10 — proactive/autonomous behavior

Requires hosted JARVIS and real connected services.

Pass criteria:
- Events can arrive while the user's computer is offline.
- Important Gmail/Calendar/Fuel/Instagram events enter the proactive event queue.
- JARVIS applies user-defined relevance rules.
- It contacts the user only when required by the mission/monitoring rules.
- Standing permissions allow bounded autonomous actions without repeated confirmation.

## Release rule

A feature is called **implemented** when code exists and automated tests pass.
A feature is called **verified** only after its corresponding acceptance gate has passed against the real provider/application/device.
