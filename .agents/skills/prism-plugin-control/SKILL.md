---
name: prism-plugin-control
description: Discover, explicitly trust, attach, inspect, control, persist, validate, and offline-render user-installed VST3 effects through Prism. Use for plugin registry, compatibility, parameters, bypass, opaque state, or worker recovery; do not claim live VST3 processing or trust binaries automatically.
---

# Prism Plugin Control

Prism Phase 9 hosts one VST3 effect per track in an isolated subprocess for
offline rendering. Live transport remains dry. Third-party binaries stay
user-installed and require approval for their exact SHA-256 before Prism probes
or loads them.

Read [plugin trust, project, API, and recovery contracts](references/plugin-control.md)
before attaching an effect, saving state, handling a compatibility failure, or
building an agent tool around the plugin API.

## Choose the interface

- Use `uv run prism plugin ... --json` for auditable discovery, trust, scan,
  attachment, parameter, bypass, state, compatibility, and worker commands.
- Use `PrismClient` for a multi-step agent workflow against an existing
  foreground service. Use request models from `prism.application`.
- Use raw `/api/v1` only for non-Python clients or protocol tests. Discover
  capabilities and schemas first.
- Use the browser Track effects panel for human control or visible UI testing,
  not as the source of project truth.

## Required workflow

1. Add only the intended plugin directory as a search path.
2. Discover candidates; do not infer trust from their location.
3. Obtain explicit user intent before `plugin trust`, which binds approval to
   the current binary hash.
4. Scan again so the worker can probe trusted candidates and persist registry
   metadata.
5. Check project compatibility before loading, editing, or rendering.
6. Preview attachment or project mutations, then commit at the current
   `base_revision` with an idempotency key for retryable agent work.
7. Treat parameter values as normalized raw values from `0.0` through `1.0`.
8. Capture opaque state after parameter or editor changes that must travel with
   the project.
9. Submit an offline render and observe job/plugin events to a terminal state.

## Safety boundaries

- Never trust a candidate merely to make a workflow pass. Report `untrusted`,
  `changed`, or `missing` and request explicit authority.
- A modified binary invalidates its prior trust and project compatibility.
- Never copy or redistribute a VST3 binary into a project or Prism package.
- Use plugin instance UUIDs and registry UUIDs from discovery; do not guess
  identifiers or forge registry metadata in a raw transaction.
- Opaque state belongs at `assets/plugin-state/<instance-id>.bin`; mutate it
  through state capture, never direct archive edits.
- Worker timeout/crash recovery retries once, then returns dry audio for the
  failed instance and emits failure/bypass events. Report the bypass; do not
  describe the affected render as fully processed.
- `bypassed` is persisted project intent. A failure-induced render bypass does
  not silently rewrite that field.
- Do not describe Phase 9 as real-time plugin support. Live playback, plugin
  editors, instruments, MIDI, automation, and multi-effect chains remain later
  work.
