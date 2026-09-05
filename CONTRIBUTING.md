# Contributing to Prism

Prism is an early-development, script-first Python music toolbox. Contributions
are welcome through fork-based pull requests; repository write access is not needed.
Keep readable Python authoring and the lightweight, headless offline path intact.

## Before you start

Read [the governance policy](GOVERNANCE.md), [code of conduct](CODE_OF_CONDUCT.md),
and [implementation status](docs/development/implementation-status.md).
Comment on an existing issue or open one to coordinate work. Discuss large features,
API changes and dependencies with the lead maintainer before implementing them.
The roadmap lists planned work, not promises of shipped functionality.

## Local development

Use Python 3.12 and uv. Fork the repository, create a branch from current main,
and run these commands in your checkout:

```sh
uv sync --locked --extra dev --extra docs
uv run pytest --cov --cov-report=term-missing
uv run mypy src/prism
uv run ruff check .
uv run mkdocs build --strict
uv build
```

Core tests require no paid plugins or audio device. Linux may need libsndfile1.
Optional VST tests use `uv sync --locked --extra dev --extra vst3` and the
Surge XT paths described in `.github/workflows/vst-ci.yml`; they run in CI on
Windows and Linux. Never share commercial installers, accounts or license keys.

## Pull requests

Keep changes focused. Explain the problem, resulting behavior, tests and limitations.
Add regression tests for behavior changes and update documentation and relevant
tutorials. For roadmap work, update its status and link the PR without marking
unmerged work complete. Wait for required checks and maintainer review; address
feedback before merging. AI-assisted contributions follow the same standards:
review and understand generated code and disclose material testing limitations.

## Licensing and assets

Submit contributions under GPL-3.0-only, the project's existing license. You retain
copyright in your contributions; no copyright assignment or CLA is required.
Only submit work you have permission to contribute. Identify the origin and license
of third-party code and assets, and include required notices. Do not commit private
recordings, commercial sample packs, plugin binaries, credentials or personal data.
Report vulnerabilities using [SECURITY.md](SECURITY.md), not a public issue.
