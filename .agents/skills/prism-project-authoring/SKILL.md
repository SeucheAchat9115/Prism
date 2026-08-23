---
name: prism-project-authoring
description: Create, inspect, validate, migrate, or safely edit Prism projects and their tracks, scenes, clips, slots, transport settings, and mixer state. Use for project authoring through the CLI or typed transaction API; do not use for live playback control or repository implementation work.
---

# Prism Project Authoring

Treat the service as the only writer of a `.prism-work` project. Never patch a
user's manifest, history, internal `.prism/` directory, or portable archive.

## Select the interface

- Use `uv run prism ... --json` for finite shell tasks and reviewable output.
- Use `PrismClient` plus models from `prism.application` for a composed Python
  agent workflow.
- Use raw HTTP only for a non-Python integration; load
  `$prism-api-integration` for protocol details.

Local creation, portable inspection, migration, and server startup can run
offline. Normal inspection and all working-project mutations require the
foreground service that owns that project.

## Safe authoring sequence

1. Create or identify the `.prism-work` project and start `prism serve`.
2. Read readiness and project state. Confirm the service project UUID matches
   the intended local project.
3. Resolve user-facing names to UUIDs; reject missing or ambiguous names.
4. Build a `TransactionRequest` at the current revision. Prefer typed
   operations over the legacy `set` operation.
5. Preview the exact request. Inspect errors, cascade impact, changed paths,
   created/deleted IDs, runtime impact, and `runtime_reset_required`.
6. Obtain user intent before adding destructive `cascade=true` or accepting a
   required runtime reset. Commit with a unique idempotency key.
7. Fetch the project again and run layered validation. Export a portable
   `.prism` only when a snapshot or handoff is requested.

Read [transaction operations](references/transaction-operations.md) before
constructing or changing an operation batch.

## Conflict and retry rules

- A stale revision means the project changed. Re-read it, reconcile the desired
  edit, and preview again; never overwrite blindly.
- After an unknown network outcome, retry the identical operation batch with
  the same idempotency key. A refreshed base revision is allowed, but changing
  the operations under that key is an idempotency conflict.
- Destructive operations with dependants require `cascade=true`; preview is
  where the complete dependent-ID impact must be reviewed.
- If a source archive or manifest changed externally, do not detach it
  automatically. Inspect the conflict and use the explicit detach flow only
  when the user accepts an independent working copy.

The portable `.prism` archive is an interchange artifact. Use `project show
--portable`, `project validate --portable`, and explicit migration/export
commands rather than treating it as ordinary editable storage.
