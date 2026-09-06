# Implementation tasks

This roadmap combines the September 5, 2026 repository audit with the September 6
human-guided agentic music-production direction.
It tracks completed and proposed work. A planned item is not an available feature. The full
[implementation prompts](implementation-prompts.md) explain what to change, why,
how to approach it, and the acceptance criteria for each task.

## How to hand off work

1. Follow the delivery order below (including A01–A05), skip completed tasks,
   and open the next unfinished task's complete prompt.
2. Give the implementation agent the complete text block and the previous agent's
   branch/commit and handoff. Read `AGENTS.md` before making changes.
3. Start from the latest integrated work containing the prerequisites. The audit
   commit in each prompt is historical evidence, not a branch to reset to.
4. Recheck the current implementation and existing pull requests before repeating
   work. A task is complete only when its acceptance criteria are verified.
5. Use the GitHub connector for all remote repository communication, including reads,
   branch/commit publication, review feedback, CI checks, and pull requests. Local
   editing, testing, and local Git operations are allowed; do not contact GitHub
   through shell Git, `gh`, `curl`, or direct HTTP clients. Report unavailable or
   blocked connector operations without silently switching transports.
6. Publish changes through the connector and finally open a PR, or update the
   existing open PR for that task. Target `main` unless prerequisite work requires
   an explicitly documented stacked PR. Include the task number, scope,
   compatibility decisions, exact verification results, and limitations. Check
   the published diff and CI results, fix failures caused by your changes, and
   return the PR URL, branch, final commit SHA, and handoff. Do not auto-merge.
7. Record completed scope, API decisions, verification, limitations, and the
   branch/commit in `docs/development/implementation-status.md`, creating it if
   absent and preserving any existing entries. Pass that record to the next agent.
8. Update this roadmap's task row in the same implementation PR. Keep its status
   and PR/evidence link synchronized with the implementation-status record. Add
   the actual PR URL to both records in a follow-up commit if necessary before
   the final handoff. Preserve other tasks' statuses, numbering, and dependencies.

Each task may take several focused commits. Keep implementation changes scoped to
its prompt and document compatibility decisions. The dependency column names
required predecessors; all earlier integrated changes must also remain present.

## Product goal and delivery order

Prism enables **human-guided agentic music production**. A person describes what
they want; an external agent inspects musical context, makes a targeted proposal,
renders alternatives and applies the person's choice. Readable Python remains the
authoring source, with reproducible projects and a headless offline path.

The first product milestone must support "I like the bassline, but change the notes
to be more euphoric" and "Build a synth lead which fits the bassline." Preserve
requested parts, explain interpretations, audition alternatives and restore the
previous version. Musical taste belongs to the person; diagnostics check technical
properties and explicit constraints.

**Delivery order: 01–14 → A01–A03 → 15–18 → A04–A05 → 19–35.**
There are 40 tasks. Original IDs 01–35 and their audit links are retained; A01–A05
are inserted tasks, not work to defer until after 35. Dependencies below are hard
prerequisites; the delivery order sets the default sequence. Do not execute an old
cached prompt when its dependency or scope has changed.

| Tasks | Outcome |
| --- | --- |
| 01–10 | File safety, musical timing, voice correctness and VST reliability |
| 11–14 | Export contracts, reproducibility and public project build contract |
| A01–A03 | Musical context, agent operations, reversible source edits and reusable composition |
| 15–18 | Short range previews, audible playback, edit-save-hear and visual transport |
| A04–A05 | Candidate comparison, human selection and qualified external-agent production |
| 19–22 | Continuous processing, native DSP and persistent VST hosting |
| 23–30 | Performance MIDI, routing, arrangement, editing, mastering and project tools |
| 31–35 | Recording, takes, listening formats, platform support and production qualification |

A05 is the first qualified agentic production milestone. It requires both example
briefs to complete through an external agent, with preserved constraints, audible
comparisons, an accepted readable project and working undo after reopening.
Scripted CI proves tool behavior; an actual agent run and human listening review
are separate evidence. Missing either leaves the milestone incomplete.

Background-rendered previews are sufficient for this milestone. Continuous live
processing (19–22) and recording/takes (31–32) extend it later. Core musical
transforms move into A03; task 25 extends them with tempo/meter maps. General
revision history moves into A02; task 32 extends it for takes and comping.

OSC/UDP/Link, infinite live patterns, arbitrary DSP graphs and alternative tunings
remain possible follow-on work, with no delivery commitment in these 40 tasks.
They do not block the prompt-guided workflow. A dedicated language or a complete
live-performance ecosystem is not required for the first milestone.

## Revision guidance for implementation agents

Every prompt includes the product goal and connector-only repository workflow.
A01 defines shared identities and schemas; A02 owns source persistence and
history; A03 owns basic musical patterns; A04 owns candidate audition; A05 adds an
optional MCP adapter and qualifies the complete workflow. Later tasks reuse these
contracts. Arbitrary Python must not be silently rewritten or replaced by a
divergent editable state file. Clearly document supported editing constructs.

## Ordered tasks

Use **Planned**, **In progress**, **Blocked**, or **Done**. Mark Done when the task's
acceptance criteria are satisfied, and record pending checks or blockers honestly.
Done describes implementation completion; check the linked PR for merge state.

| Task | Prompt | Required predecessors | Status | PR / evidence |
| --- | --- | --- | --- | --- |
| 01 | [Protect source audio and make stem exports recoverable](implementation-prompts.md#task-01) | None | Done | [PR #13](https://github.com/SeucheAchat9115/Prism/pull/13) |
| 02 | [Unify musical time and correct non-quarter-note meters](implementation-prompts.md#task-02) | 01 | Done | [PR #16](https://github.com/SeucheAchat9115/Prism/pull/16) |
| 03 | [Make VST instrument configuration explicitly track-owned](implementation-prompts.md#task-03) | 02 | Done | [PR #29](https://github.com/SeucheAchat9115/Prism/pull/29) |
| 04 | [Compile arrangement notes and expressive controls once](implementation-prompts.md#task-04) | 02, 03 | Done | [PR #30](https://github.com/SeucheAchat9115/Prism/pull/30) |
| 05 | [Render each VST instrument track through one continuous instance](implementation-prompts.md#task-05) | 03, 04 | Done | [PR #31](https://github.com/SeucheAchat9115/Prism/pull/31) |
| 06 | [Preserve sample and audio releases across arrangement boundaries](implementation-prompts.md#task-06) | 02, 04 | Done | [PR #32](https://github.com/SeucheAchat9115/Prism/pull/32) |
| 07 | [Fix native voice lifetime and remove accidental song-length limits](implementation-prompts.md#task-07) | 02, 04, 06 | Done | [PR #33](https://github.com/SeucheAchat9115/Prism/pull/33) |
| 08 | [Define parameter automation boundaries and canonical targets](implementation-prompts.md#task-08) | 02, 03, 04, 07 | Done | [PR #34](https://github.com/SeucheAchat9115/Prism/pull/34) |
| 09 | [Harden VST workers, cancellation, diagnostics, and state saving](implementation-prompts.md#task-09) | 03, 05, 08 | Done | [PR #35](https://github.com/SeucheAchat9115/Prism/pull/35) |
| 10 | [Strengthen real VST tests and verify latency compensation](implementation-prompts.md#task-10) | 04, 05, 09 | Done | [PR #36](https://github.com/SeucheAchat9115/Prism/pull/36) |
| 11 | [Add explicit export profiles, clipping policy, and dither](implementation-prompts.md#task-11) | 01, 02, 06, 07, 08 | Done | [PR #37](https://github.com/SeucheAchat9115/Prism/pull/37) |
| 12 | [Make stem delivery modes and reconstruction guarantees explicit](implementation-prompts.md#task-12) | 01, 05, 11 | Planned | — |
| 13 | [Add project fingerprints, render manifests, and version compatibility](implementation-prompts.md#task-13) | 03, 09, 11, 12 | Planned | — |
| 14 | [Create a public project build contract and executable CLI tutorials](implementation-prompts.md#task-14) | 02, 03, 11, 13 | Planned | — |
| A01 | [Expose musical context and a versioned agent tool contract](implementation-prompts.md#task-a01) | 04, 08, 13, 14 | Planned | — |
| A02 | [Implement scoped edits, source persistence and recoverable revisions](implementation-prompts.md#task-a02) | A01 | Planned | — |
| A03 | [Add reusable musical patterns and constrained composition helpers](implementation-prompts.md#task-a03) | A02, 04 | Planned | — |
| 15 | [Implement range rendering, bounded caches, and optional automatic tails](implementation-prompts.md#task-15) | 04, 06, 07, 11, 13, 14 | Planned | — |
| 16 | [Add audible playback and transport for rendered audio](implementation-prompts.md#task-16) | 11, 14, 15 | Planned | — |
| 17 | [Reload edited Python while the previous song keeps playing](implementation-prompts.md#task-17) | 13, 14, 15, 16, A02 | Planned | — |
| 18 | [Provide a compact visual transport and live playback inspection](implementation-prompts.md#task-18) | 16, 17, A02 | Planned | — |
| A04 | [Deliver candidate previews, comparison and human selection](implementation-prompts.md#task-a04) | A03, 15, 16, 17, 18 | Planned | — |
| A05 | [Qualify human-guided agentic music production end to end](implementation-prompts.md#task-a05) | A04 | Planned | — |
| 19 | [Introduce stateful processors and a streaming offline renderer](implementation-prompts.md#task-19) | 04, 05, 06, 07, 08, 12, 15 | Planned | — |
| 20 | [Move DSP hot paths behind a native processing boundary](implementation-prompts.md#task-20) | 19 | Planned | — |
| 21 | [Implement a continuous native VST3 host and device proof](implementation-prompts.md#task-21) | 03, 09, 10, 19, 20 | Planned | — |
| 22 | [Integrate the persistent live graph and safe project updates](implementation-prompts.md#task-22) | 17, 18, 19, 20, 21, A04 | Planned | — |
| 23 | [Add live MIDI devices, performance controls, and MIDI recording](implementation-prompts.md#task-23) | 04, 18, 22 | Planned | — |
| 24 | [Expand routing, sidechains, multi-output plugins, and mixer controls](implementation-prompts.md#task-24) | 08, 10, 12, 19, 22 | Planned | — |
| 25 | [Add tempo maps, meter changes, and reusable musical structures](implementation-prompts.md#task-25) | 02, 04, 14, 19, 22, A03 | Planned | — |
| 26 | [Implement MIDI import and reliable larger-session interchange](implementation-prompts.md#task-26) | 04, 13, 23, 25 | Planned | — |
| 27 | [Implement proper time stretching and non-destructive audio edits](implementation-prompts.md#task-27) | 02, 06, 13, 15, 19, 25 | Planned | — |
| 28 | [Add essential mixing processors and trustworthy loudness meters](implementation-prompts.md#task-28) | 11, 19, 20, 22, 24 | Planned | — |
| 29 | [Improve native synthesis quality without silently changing old songs](implementation-prompts.md#task-29) | 07, 19, 20, 22 | Planned | — |
| 30 | [Add sound browsing, asset repair, freeze, and portable project bundles](implementation-prompts.md#task-30) | 13, 15, 18, 24, 27 | Planned | — |
| 31 | [Add audio input, monitoring, and reliable recording](implementation-prompts.md#task-31) | 01, 13, 18, 22, 23, 24 | Planned | — |
| 32 | [Add takes, comping, punch recording, and recoverable edit history](implementation-prompts.md#task-32) | 18, 27, 30, 31, A02 | Planned | — |
| 33 | [Add lossless and compressed listening export formats](implementation-prompts.md#task-33) | 01, 11, 12, 13, 28 | Planned | — |
| 34 | [Expand platform support and simplify clean installation](implementation-prompts.md#task-34) | 09, 10, 14, 20, 21, 22, 30, 33 | Planned | — |
| 35 | [Qualify the complete production workflow and publish an accurate capability map](implementation-prompts.md#task-35) | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, A05 | Planned | — |

## Existing implementation work

Tasks 01 and 02 are **Done** and merged in
[PR #13](https://github.com/SeucheAchat9115/Prism/pull/13) and
[PR #16](https://github.com/SeucheAchat9115/Prism/pull/16).
Continue with task 03 from the latest integrated main branch. The September 6
roadmap revision adds planned work; it does not mark agent features implemented.
Each implementation PR must update its task row and the implementation-status
record with actual verification and merge information.
