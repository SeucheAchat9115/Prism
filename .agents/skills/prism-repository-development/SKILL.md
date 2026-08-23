---
name: prism-repository-development
description: Implement, debug, review, test, or document changes inside the Prism repository, including choosing the owning architecture layer and the required validation. Use for source and repository maintenance; do not use merely to operate an existing Prism project through its public CLI or API.
---

# Prism Repository Development

Work from the repository root and follow `AGENTS.md`. Inspect the current tree
and tests before proposing a layer or public contract.

## Workflow

1. Classify the change by owning layer. Read
   [architecture and validation](references/architecture-and-validation.md)
   when the ownership, cross-layer impact, or test gate is not obvious.
2. Trace the current behavior from its public entry point into
   `ApplicationService` and the underlying domain module. Do not duplicate
   state or validation in the CLI or browser.
3. Change the narrowest owner first, then propagate intentional public changes
   outward through API, CLI/UI, tests, examples, and documentation.
4. Use Pydantic application contracts for API-visible data. Preserve strict
   unknown-field rejection, stable error codes, revisions, and deterministic
   persistence/rendering.
5. Run focused tests while iterating and the appropriate final gate from the
   reference. A public workflow is incomplete until its example and docs still
   match the implementation.

## Repository tools

- Use `rg`/`rg --files` to locate behavior and `apply_patch` for edits.
- Use `uv sync --locked --extra dev` for the environment and `uv run ...` for
  checks; do not substitute an unrelated global environment.
- Keep tests device-free unless the task explicitly concerns real hardware.
- For visible browser behavior, run the marked Chromium suite and inspect the
  rendered UI, not only static strings.
- Build and test the exact wheel for packaging, entry-point, or packaged-asset
  changes.

Do not commit generated projects, WAV files, Playwright output, caches, virtual
environments, or build artifacts.
