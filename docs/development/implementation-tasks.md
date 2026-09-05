# Implementation tasks

This is the ordered development roadmap from the September 5, 2026 repository audit.
It describes proposed work, not features already available in Prism. The full
[implementation prompts](implementation-prompts.md) explain what to change, why,
how to approach it, and the acceptance criteria for each task.

## How to hand off work

1. Follow the numbered order below and open the linked prompt.
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

Each task may take several focused commits. Keep implementation changes scoped to
its prompt and document compatibility decisions. The dependency column names
required predecessors; all earlier integrated changes must also remain present.

## Delivery stages

| Tasks | Outcome |
| --- | --- |
| 01–10 | File safety, musical timing, voice correctness, and VST reliability |
| 11–15 | Export contracts, reproducibility, and preview preparation |
| 16–18 | Audible playback, Python edit-save-hear, and a visual transport |
| 19–22 | Continuous processing, native DSP, and persistent VST hosting |
| 23–30 | Performance MIDI, routing, arrangement, editing, mastering, and project tools |
| 31–35 | Recording, takes, listening formats, platform support, and production qualification |

Tasks 16–18 deliver background-rendered preview. Tasks 19–22 deliver continuous
live processing. Recording and takes arrive in tasks 31–32. These are distinct
milestones; playback alone does not establish a complete DAW.

## Ordered tasks

| Task | Prompt | Required predecessors |
| --- | --- | --- |
| 01 | [Protect source audio and make stem exports recoverable](implementation-prompts.md#task-01) | None |
| 02 | [Unify musical time and correct non-quarter-note meters](implementation-prompts.md#task-02) | 01 |
| 03 | [Make VST instrument configuration explicitly track-owned](implementation-prompts.md#task-03) | 02 |
| 04 | [Compile arrangement notes and expressive controls once](implementation-prompts.md#task-04) | 02, 03 |
| 05 | [Render each VST instrument track through one continuous instance](implementation-prompts.md#task-05) | 03, 04 |
| 06 | [Preserve sample and audio releases across arrangement boundaries](implementation-prompts.md#task-06) | 02, 04 |
| 07 | [Fix native voice lifetime and remove accidental song-length limits](implementation-prompts.md#task-07) | 02, 04, 06 |
| 08 | [Define parameter automation boundaries and canonical targets](implementation-prompts.md#task-08) | 02, 03, 04, 07 |
| 09 | [Harden VST workers, cancellation, diagnostics, and state saving](implementation-prompts.md#task-09) | 03, 05, 08 |
| 10 | [Strengthen real VST tests and verify latency compensation](implementation-prompts.md#task-10) | 04, 05, 09 |
| 11 | [Add explicit export profiles, clipping policy, and dither](implementation-prompts.md#task-11) | 01, 02, 06, 07, 08 |
| 12 | [Make stem delivery modes and reconstruction guarantees explicit](implementation-prompts.md#task-12) | 01, 05, 11 |
| 13 | [Add project fingerprints, render manifests, and version compatibility](implementation-prompts.md#task-13) | 03, 09, 11, 12 |
| 14 | [Create a public project build contract and executable CLI tutorials](implementation-prompts.md#task-14) | 02, 03, 11, 13 |
| 15 | [Implement range rendering, bounded caches, and optional automatic tails](implementation-prompts.md#task-15) | 04, 06, 07, 11, 13, 14 |
| 16 | [Add audible playback and transport for rendered audio](implementation-prompts.md#task-16) | 11, 14, 15 |
| 17 | [Reload edited Python while the previous song keeps playing](implementation-prompts.md#task-17) | 13, 14, 15, 16 |
| 18 | [Provide a compact visual transport and live playback inspection](implementation-prompts.md#task-18) | 16, 17 |
| 19 | [Introduce stateful processors and a streaming offline renderer](implementation-prompts.md#task-19) | 04, 05, 06, 07, 08, 12, 15 |
| 20 | [Move DSP hot paths behind a native processing boundary](implementation-prompts.md#task-20) | 19 |
| 21 | [Implement a continuous native VST3 host and device proof](implementation-prompts.md#task-21) | 03, 09, 10, 19, 20 |
| 22 | [Integrate the persistent live graph and safe project updates](implementation-prompts.md#task-22) | 17, 18, 19, 20, 21 |
| 23 | [Add live MIDI devices, performance controls, and MIDI recording](implementation-prompts.md#task-23) | 04, 18, 22 |
| 24 | [Expand routing, sidechains, multi-output plugins, and mixer controls](implementation-prompts.md#task-24) | 08, 10, 12, 19, 22 |
| 25 | [Add tempo maps, meter changes, and reusable musical structures](implementation-prompts.md#task-25) | 02, 04, 14, 19, 22 |
| 26 | [Implement MIDI import and reliable larger-session interchange](implementation-prompts.md#task-26) | 04, 13, 23, 25 |
| 27 | [Implement proper time stretching and non-destructive audio edits](implementation-prompts.md#task-27) | 02, 06, 13, 15, 19, 25 |
| 28 | [Add essential mixing processors and trustworthy loudness meters](implementation-prompts.md#task-28) | 11, 19, 20, 22, 24 |
| 29 | [Improve native synthesis quality without silently changing old songs](implementation-prompts.md#task-29) | 07, 19, 20, 22 |
| 30 | [Add sound browsing, asset repair, freeze, and portable project bundles](implementation-prompts.md#task-30) | 13, 15, 18, 24, 27 |
| 31 | [Add audio input, monitoring, and reliable recording](implementation-prompts.md#task-31) | 01, 13, 18, 22, 23, 24 |
| 32 | [Add takes, comping, punch recording, and recoverable edit history](implementation-prompts.md#task-32) | 18, 27, 30, 31 |
| 33 | [Add lossless and compressed listening export formats](implementation-prompts.md#task-33) | 01, 11, 12, 13, 28 |
| 34 | [Expand platform support and simplify clean installation](implementation-prompts.md#task-34) | 09, 10, 14, 20, 21, 22, 30, 33 |
| 35 | [Qualify the complete production workflow and publish an accurate capability map](implementation-prompts.md#task-35) | 01, 02, 03, 04, 05, 06, 07, 08, 09, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34 |

## Existing implementation work

As of September 5, 2026, task 01 has an open implementation
[PR #13: Protect source audio and recover stem exports](https://github.com/SeucheAchat9115/Prism/pull/13).
Check its current merge state and implementation-status record before assigning
or depending on task 01. This is a dated reference, not an assertion that the
change has merged. Later task progress belongs in the implementation-status record
and its linked pull requests.
