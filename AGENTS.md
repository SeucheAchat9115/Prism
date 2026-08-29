# Working on Prism as a coding agent

This file is the repository-specific operating guide for agents that design,
implement, review, or document Prism features. Read it before changing code.
When a user request conflicts with this guide, follow the user request and make
the smallest coherent change needed.

## Product contract

Prism is a script-first Python music package. A music producer describes a song
in one readable `main.py`, keeps samples beside it, and reruns that file to
reproduce WAV and MIDI output.

Protect these product decisions unless the requested feature explicitly changes
them:

- The producer-facing interface is Python, not an HTTP API, GUI, or large CLI.
- The CLI only creates readable, unpacked project starting points.
- `main.py` is the project source of truth; there is no hidden project database.
- Producer scripts must remain approachable to people who are not developers.
- A project is an ordinary folder containing `main.py`, `sounds/`, and `renders/`.
- Commands in documentation run from the repository root on Windows and Linux.
- User-facing `main.py` examples do not use `__file__` and do not require `cd`.
- Every generated project records a literal `prism_version="..."` value.
- Inputs and outputs use safe relative paths inside the project folder.
- Rendering is offline and deterministic. The same project and source files
  must produce the same audio bytes.

Do not reintroduce removed API, web, GUI, archive, manifest, `.prism`, or
project-JSON concepts without an explicit product decision.

## Repository map

```text
src/prism/
├── project/builder.py       producer-facing song, track, clip, section, and bus API
├── render.py                arrangement, audio loading/editing, mixing, and WAV output
├── midi.py                  standard MIDI export
├── music.py                 notes, notation, pitch, gain, and pan helpers
├── plugins.py               plugin definitions, instances, validation, and automation
├── effects.py               effect-chain and automation processing
├── synthesis/               shared deterministic synthesis contracts and engine
├── stock_plugins/           one-file stock instruments and effects plus registry.py
├── cli.py                   timestamped project scaffolding
├── errors.py                producer-facing exception hierarchy
└── __init__.py              deliberately small public import surface

tests/                       unit, integration, render, tutorial, and package tests
docs/tutorial/               complete runnable learning path
docs/guides/                 producer-oriented concept guides
docs/reference/              generated Python reference page declarations
docs/plugins/                stock-plugin contributor documentation
docs/hooks.py                deterministic documentation audio generation
mkdocs.yml                   documentation navigation and build configuration
.github/workflows/ci.yml     Windows and Linux package validation
.github/workflows/docs.yml   strict docs build and GitHub Pages deployment
```

Generated `projects/`, `renders/`, `site/`, documentation audio, caches, and
build artifacts are ignored. Do not treat them as source files.

## Understand the signal flow

Keep behavior consistent with this order:

```text
Song → sections → track clip placements
                    ↓
          MIDI/triggers → instrument
                    ↓
          ordered track effects
                    ↓
             track gain and pan
                    ↓
       main-output buses and parallel sends
                    ↓
              master effects
                    ↓
            normalization and WAV
```

Automation lanes are song-level timeline data. They target one plugin instance
and one registered numeric parameter. Static settings and automated settings
must reach the same DSP path.

## Feature-development workflow

### 1. Start from behavior

Before editing, identify:

- the producer-facing call that should appear in `main.py`;
- where the behavior belongs in the signal flow;
- validation rules, units, defaults, and safe bounds;
- configuration data required to reproduce the result;
- expected WAV, MIDI, or project-scaffolding output;
- which tutorial should teach the feature.

Prefer a small musical vocabulary over a generic software abstraction. Use
explicit units in names such as `_db`, `_hz`, `_ms`, `_seconds`, and `_bars`.

### 2. Trace the complete implementation path

A feature is rarely complete when only its builder method exists. Check every
affected layer:

1. public objects and exports;
2. authoring and validation;
3. immutable clip/plugin data;
4. resolved `configuration()` output;
5. renderer and signal ordering;
6. MIDI export when musical events are involved;
7. deterministic result metadata;
8. tests;
9. tutorial, guide, parameter reference, and API docs.

Search with `rg` before adding a new concept. Extend an existing path when it
already models the behavior correctly.

### 3. Keep authoring readable

Favor fluent calls that read in signal order:

```python
lead = song.track("Lead", gain_db=-7).midi(
    "C4 Eb4 G4 Bb4",
    instrument=Uniwave.lead(),
)
filter_fx = lead.effect("filter", cutoff_hz=4200)
song.automation(
    "Open Lead Filter",
    target=filter_fx,
    parameter="cutoff_hz",
    points=[(0, 700), (4, 4200)],
)
song.section("Loop", bars=4, tracks=[lead])
song.render("renders/song.wav")
```

Avoid requiring users to subclass framework types, write callbacks, calculate
sample frames, or understand internal registry objects for normal production.

### 4. Validate at the boundary

Reject invalid authoring data as early as practical with `ProjectError` and a
specific, readable message. Validate finite numbers as well as numeric ranges.
State units and accepted bounds in the message when useful.

Paths must remain relative, must not contain traversal, and must resolve inside
the project. Preserve Windows and POSIX path handling. Do not weaken this rule
to make a test fixture easier to write.

### 5. Preserve determinism

- Never use process-global random state.
- Give noise and humanization an explicit seed and use a local generator.
- Use `float64` arrays while processing audio.
- Keep frame counts exact and intentional.
- Do not depend on wall-clock time, audio devices, network services, user
  configuration, or unrelated filesystem state during rendering.
- Render twice in tests and compare bytes or hashes for stochastic-looking DSP.
- Keep processing order stable; dictionary or registry iteration must not
  accidentally define an unstable mix order.

The timestamp used to create a new project folder is allowed to vary. Song
rendering and exported musical content are not.

## Public API rules

The supported producer imports are listed in `src/prism/__init__.py` and tested
explicitly in `tests/test_package.py`. Keep this surface small.

When adding a genuinely public type:

1. give it a useful docstring and type annotations;
2. export it from the appropriate module;
3. add it to top-level `prism.__all__` only if producers need it directly;
4. update the exact public-surface test;
5. add or update its generated page under `docs/reference/`;
6. show it in a complete producer-facing example.

Do not expose renderer helpers, registry machinery, or DSP-only dataclasses just
because a feature needs them internally. Do not change the package version
unless the requested work includes a version or release change.

## Clips, arrangement, and MIDI

- One track may contain multiple clips, but all clips on that track must have a
  compatible source kind and instrument.
- Default clips apply across sections; section-specific clips replace the
  defaults for that section.
- `start_bar` is relative to the containing section. Automation point bars are
  absolute song positions.
- `repeat` controls clip-placement repetition. Audio `loop` controls repetition
  inside one audio clip; these are different concepts.
- Individual `Note` positions and durations are in beats relative to the clip.
- MIDI controller and pitch-bend behavior must agree between audio rendering,
  configuration inspection, and standard MIDI export.
- Preserve the 120-second safety limit for generated synth clips unless a
  deliberate design change replaces it.

When adding a timing feature, test boundaries between clips and sections, not
only a one-track one-section loop.

## Stock plugin rules

Read `docs/plugins/adding-stock-plugins.md` before adding a plugin.

A new stock plugin should require:

1. one implementation file under `src/prism/stock_plugins/` containing its
   definition, defaults, parameter schema, and processor or synth callback;
2. one import and registry entry in `src/prism/stock_plugins/registry.py`;
3. focused tests in `tests/test_plugins.py` or a dedicated synthesis test;
4. parameter-reference and tutorial updates.

Effect processors receive stereo samples, per-frame parameter arrays, sample
rate, and tempo. They return `float64` audio with the same frame count. Keep
dry/wet behavior in the plugin when it exposes `mix`.

Numeric effect parameters become automation targets through their registered
`Parameter`. Test defaults, both boundaries, invalid settings, audible change,
effect ordering, automation, and deterministic rerendering.

Instrument processors consume resolved musical events and return the exact
requested frame count. MIDI program or drum-note mappings belong in the plugin
definition. Seed every noise source locally.

## Tests

Tests are part of the feature design. Place focused coverage near the layer
being changed:

- `test_project.py`: builder behavior, validation, paths, and configuration;
- `test_render.py`: audio loading, arrangement, editing, WAV output, and hashes;
- `test_midi.py`: standard MIDI content and arrangement;
- `test_expression.py`: note timing, controllers, swing, and humanization;
- `test_plugins.py`: registry, effects, chains, and automation;
- `test_mixer.py`: buses, sends, routing, and master processing;
- `test_uniwave.py`: Uniwave validation, sound design, and deterministic DSP;
- `test_cli.py`: timestamped project scaffolding;
- `test_package.py`: public surface, tutorial executability, docs, and packaging.

Use small sample rates and short arrangements in unit tests where sound quality
is not the assertion. Assert both metadata/configuration and audible output for
rendering features. Avoid brittle tests based only on implementation details.

On this Windows workspace, the system pytest temporary directory can be
permission-restricted. Use a unique ignored repository-local directory when
needed:

```text
uv run pytest --basetemp .test-tmp-feature-name --cov --cov-report=term-missing
```

Do not commit `.test-tmp-*`, `.coverage`, `site/`, documentation audio, or
rendered test media.

## Documentation and tutorials

The hosted documentation is part of the product, not an afterthought.

- `docs/tutorial/` is the single progressive learning path.
- Every tutorial level contains a complete `main.py`, not a partial diff.
- Keep tutorials understandable to a producer using an ordinary text editor.
- Avoid unnecessary setup commands and internal implementation language.
- Update `docs/tutorial/10-parameter-reference.md` for every public option,
  default, range, and unit.
- Update the tutorial index functionality map when capabilities move or grow.
- Add a new tutorial level when a feature needs a focused listening exercise;
  update `mkdocs.yml` navigation and tutorial tests at the same time.
- Update a guide when a feature changes how producers understand signal flow.
- Generated API pages use public docstrings and signatures; improve docstrings
  when the generated result is unclear.

`docs/hooks.py` renders the homepage audio example during every documentation
build. It must remain fast, deterministic, sample-free, and compatible with the
current package.

Build documentation strictly:

```text
uv run --extra docs mkdocs build --strict
```

Preview it locally:

```text
uv run --extra docs mkdocs serve
```

The live site is deployed from `main` by `.github/workflows/docs.yml`.

## Required checks

Run checks from the repository root. Install the locked environments after
changing dependencies:

```text
uv sync --locked --extra dev --extra docs
```

Before handing off a feature, run:

```text
uv run pytest --cov --cov-report=term-missing
uv run mypy src/prism
uv run ruff check .
uv run --extra docs mkdocs build --strict
uv build --no-sources
git diff --check
```

Coverage must remain at or above the configured 85% threshold. CI runs package
checks on both Windows and Ubuntu. A local pass is not permission to introduce
platform-specific paths, shell syntax, or audio assumptions.

If the full audio suite is slow, run focused tests while iterating, then run the
complete suite before completion.

## Git and workspace hygiene

- Inspect `git status` before editing. Preserve unrelated user changes.
- Make narrow changes that match the requested feature.
- Never edit generated `site/`, `dist/`, caches, renders, or timestamped projects
  as though they were source.
- Update `uv.lock` whenever dependency declarations change.
- Do not use destructive Git commands to clear work you did not create.
- Do not push unless the user requests it.
- Before committing, run `git diff --check` and inspect the complete diff.

## Definition of done

A Prism feature is complete only when:

- its producer-facing Python reads naturally;
- validation fails early with helpful messages;
- configuration captures every value needed to explain and reproduce it;
- audio and MIDI paths agree where both apply;
- rendering remains deterministic and cross-platform;
- focused and regression tests pass;
- the complete tutorial or guide teaches the behavior;
- parameter and generated API documentation are current;
- strict docs, lint, typing, coverage, and package builds pass;
- generated files and local media remain untracked.
