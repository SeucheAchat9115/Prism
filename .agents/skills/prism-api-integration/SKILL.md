---
name: prism-api-integration
description: Build, extend, or troubleshoot an agent or client integration against Prism's local v1 HTTP/WebSocket API and typed Python client. Use for interface selection, discovery, request models, errors, retries, and events; do not use merely to run a documented one-off Prism command or to implement Prism internals.
---

# Prism API Integration

Prism exposes one local service for one project. The API is versioned `/api/v1`,
loopback-only, and unauthenticated; it is not a remote service boundary.

## Pick the agent tool

| Need | Use |
| --- | --- |
| One finite operation from a shell/tool runner | `uv run prism ... --json` |
| Multi-step Python agent workflow | `prism.api.PrismClient` |
| Non-Python or protocol-level integration | Raw HTTP `/api/v1` |
| Realtime notifications | `PrismClient.events()` or project WebSocket |
| Human session or UI acceptance | Packaged browser at `/` |

Prefer the CLI when it already composes a fragile workflow such as staged audio
import, native synth generation/import, selector resolution, waiting for a job,
or dry-run cleanup. Prefer the typed client when state and UUIDs must be retained
across several calls.

Read [the v1 client and protocol contract](references/v1-client-and-protocol.md)
before implementing raw calls, exposing new agent tools, or handling retries.
Load the relevant domain skill as well for transaction, session, or job meaning.

## Integration lifecycle

1. Ensure the user or orchestrator explicitly starts `prism serve PROJECT`.
   Never create a hidden long-lived daemon.
2. Call health, readiness, version, capabilities, and schemas rather than
   assuming a feature or request shape.
3. Take the project UUID and revision from readiness. Confirm they refer to the
   intended project before any project-scoped call.
4. Use strict models from `prism.application` for Python requests. Use
   `model_dump(mode="json")` only at the HTTP boundary.
5. Preview mutations and jobs. Supply bounded timeouts and stable idempotency
   keys to retryable submissions.
6. Handle common error envelopes and transaction results explicitly. After a
   disconnect or unknown mutation outcome, resync before deciding to retry.
7. Close `PrismClient` and event streams with context managers and stop any
   service process the workflow started.

## Tool-definition design

When wrapping Prism as tools for another agent, expose intent-level operations
such as `preview_project_transaction`, `launch_session_slot`, or
`submit_render`; do not expose unrestricted manifest writes or arbitrary local
URLs. Make project ID, revision, dry-run/preview status, job ID, and structured
errors visible in tool results. Keep potentially destructive cascade/reset,
real-device audio, and source-detach decisions explicit.

Do not parse human CLI output. Finite `--json` commands produce a versioned
envelope; event watching intentionally produces JSONL. Do not treat HTTP success
alone as transaction or job success—inspect the typed result state.
