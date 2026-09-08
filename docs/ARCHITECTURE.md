# Architecture decisions

## Control plane first

The language model does not own execution state. JARVIS stores workflows and tasks in the database, selects providers through a router, and executes tools only through explicit policy checks.

## Provider agnostic

Each provider implements the same `LLMProvider.complete()` contract. The router can replace providers without changing agent code.

## Structured planning

The planner asks the selected model for a JSON DAG. Invalid output falls back to a deterministic local planner so the application remains executable.

## Risk model

LOW: read/search/calculate. MEDIUM: controlled workspace writes. HIGH: external side effects and publication. CRITICAL: financial/destructive operations. HIGH requires approval; CRITICAL is blocked.

## Execution boundary

The current MVP intentionally excludes host-level shell/computer control. That layer should run only inside disposable VMs/containers with strict filesystem and network policies.
