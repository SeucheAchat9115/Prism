---
name: prism-session-control
description: Inspect and control a live Prism service, transport, clip session, mixer, audio backend, browser UI, and realtime events. Use for playback/session operations and UI synchronization; do not use for offline project structure edits, render/export workflows, or repository implementation by itself.
---

# Prism Session Control

Operate one explicit foreground service for one `.prism-work` project. Do not
start an invisible daemon, bind beyond loopback, or send a command until
readiness confirms the intended project UUID.

## Choose the control surface

- Use CLI commands for one-off or shell-orchestrated control. Add `--json` for
  finite machine-readable commands and `--dry-run` before a mutation when
  available.
- Use `PrismClient` for coordinated Python control, state polling, and event
  handling.
- Use the packaged browser at `/` for human interaction and browser acceptance,
  not as the authoritative state store.
- Use the WebSocket event stream to observe scheduled versus actual runtime
  transitions; do not infer audibility from an accepted request alone.

Read [runtime controls and events](references/runtime-controls-and-events.md)
before implementing a multi-step session controller or debugging synchronization.

## Operating sequence

1. Start `prism serve PROJECT` or `prism demo PROJECT` and wait for the printed
   bound URL/readiness.
2. Read readiness, project, runtime snapshot, and validation together.
3. Resolve track/scene names to UUIDs before API calls.
4. Open the event stream before sending actions whose actual transition must be
   observed.
5. Send transport or session actions. Treat `accepted` and `target_frame` as
   scheduling acknowledgement.
6. Re-read state after disconnects, reconnects, or `project.changed`.
7. Stop the foreground service cleanly when the task ends.

## Safety and state rules

- Transport play/pause/stop/reset changes runtime state; `transport.update`
  changes persisted tempo, sample rate, meter, or quantization through a
  transaction.
- Mixer changes are persisted `mixer.update` transactions and update the live
  engine. Preview/revision/idempotency rules still apply; load
  `$prism-project-authoring` for complex edits.
- Device-free fallback is a valid ready state. Do not restart real audio or play
  sound unless the user requested hardware interaction.
- Built-in synth material is pre-generated audio and is live-playable through
  ordinary clips. This does not imply live VST3 or MIDI instrument support.
- Quantized actions can be scheduled for a future frame. Observe
  `clip.scheduled`, then `clip.launched`, `clip.stopped`, or `clip.completed`.
- On unknown network outcomes, resync state before retrying. Never repeatedly
  fire clip or mixer mutations blindly.

For UI changes or verification, test keyboard-accessible controls, connection
status, conflict handling, activity updates, and actual visible layout in
Chromium. The page must remain a client of `/api/v1` and the local WebSocket.
