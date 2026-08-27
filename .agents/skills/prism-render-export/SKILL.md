---
name: prism-render-export
description: Import audio and preview, submit, monitor, cancel, or verify Prism render and portable-export jobs. Use for WAV/AIFF ingestion, deterministic offline output, job handling, or `.prism` export; do not use for live playback control or general repository development.
---

# Prism Render and Export

Run these workflows through the foreground service that owns the working
project. Render and export are background jobs; audio import is a staged upload
followed by an atomic project transaction.

Read [imports, renders, exports, and jobs](references/import-render-export.md)
before constructing a render schedule, handling an upload, or interpreting a
job result.

## Tool selection

- Use CLI commands for a one-off import, render, export, wait, or cancellation.
  The CLI previews with `--dry-run`, waits by default, and emits a stable final
  envelope with `--json`.
- Use `PrismClient` for composed agent workflows, idempotent submissions, event
  monitoring, or custom polling.
- Use the browser render form only for human/UI testing. It always previews
  first but does not provide a download route.

## Required sequence

### Audio import

1. Verify the source file and intended project.
2. Stage the upload, then preview/commit one `asset.import` transaction.
3. Always discard staging, including on validation or transport failure.
4. Treat the result as an asset only. Create clips and slots explicitly with
   `$prism-project-authoring`.

Prefer the CLI for this sequence because it implements cleanup and stable
retry-derived IDs automatically.

### Render or export

1. Build the exact request and preview the resolved output/revision.
2. Confirm the output stays inside the project's `exports/` tree.
3. Submit once with an idempotency key when using the API.
4. Wait or observe job events until a terminal state.
5. Require `completed`; a returned `failed` or `cancelled` job is not success.
6. Verify output path, SHA-256, and relevant audio/archive metadata.

## Constraints

- Render duration is exactly one of positive `bars` or positive `seconds`.
- Render commands are ordered by nondecreasing frame and use UUIDs.
- Jobs capture the project revision accepted at submission. Do not assume they
  render later edits.
- Output names cannot escape the project export root. Do not work around that
  policy with direct filesystem writes.
- Device-free offline rendering is the normal deterministic path; no physical
  audio device is required.
- Native synth output is an ordinary hashed audio asset. Once a clip references
  it, rendering and artifact verification use the same rules as imported WAV.
- Cancellation is best effort for queued/running work. Re-read the terminal job
  before reporting the outcome.
