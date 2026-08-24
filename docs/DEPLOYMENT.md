# Prism Deployment

This document explains how to turn a Prism checkout into an installable
command-line tool, how to publish a release, and when to add platform-specific
desktop installers.

Prism is a local desktop application with a Python service, CLI, and
packaged browser UI. Deployment therefore means installing the application on the
musician's or coding agent's machine; it does not currently mean running a
central hosted service.

## Current deployment status

The repository currently has the foundation for a Python package:

- `pyproject.toml` defines the Hatchling build system.
- The `prism` console script is exposed through the package metadata.
- `uv.lock` records the development dependency resolution.
- Python 3.12 is currently required by `requires-python = ">=3.12,<3.13"`.
- Continuous integration runs device-free tests, strict typing, lint, and the
  85% non-native coverage gate on Windows and Linux.
- A dedicated Ubuntu job installs Chromium, runs the marked browser acceptance
  suite, and retains Playwright traces on failure.
- A packaging job installs the exact built wheel into a clean Python 3.12
  environment, runs the synthetic demo and packaged-UI smoke checks, and drives
  the complete Phase 8 browser/CLI acceptance flow against that interpreter.
- No release workflow publishes artifacts yet.

The recommended first distribution is a Python wheel and source archive. A
standalone executable and a polished OS installer should come later, after the
audio engine and browser application have real runtime behavior.

## Distribution choices

| Distribution | User experience | Prism stage |
| --- | --- | --- |
| Wheel and source archive | Install with `uv tool install` or another Python package tool | Recommended now |
| Standalone executable | Run without a separate Python installation | Later POC milestone |
| Native installer | Windows MSI/winget or Linux AppImage/package | Later polish |

The Python package contains Prism's code and Python dependencies. It does
not contain a user's `.prism` projects, audio devices, or third-party VST3
plugin binaries.

## Build a package locally

Install `uv`, then run the same checks used by CI:

```powershell
uv sync --locked --extra dev
uv run pytest -m "not audio_device and not browser"
uv run python -m playwright install chromium
uv run pytest -m browser --browser chromium
uv run ruff check .
uv run mypy src/prism
```

Build the distributions:

```powershell
uv build --no-sources
```

The artifacts are written to `dist/`:

```text
dist/
├── prism-<version>-py3-none-any.whl
└── prism-<version>.tar.gz
```

`--no-sources` makes the build use normal published dependency sources. It is
particularly appropriate for a release build; a normal `uv build` is also
useful for local development.

Test the wheel in an isolated command-line environment. Use the exact wheel
filename produced in `dist/`:

```powershell
uv tool install --python 3.12 .\dist\prism-0.1.0.dev0-py3-none-any.whl
prism version
prism --help
prism demo demo.prism-work --no-serve
```

The installed wheel contains the Phase 7 HTML, CSS, and JavaScript without a
Node build. Start the local foreground service and open its UI with:

```powershell
prism demo demo.prism-work --open
```

For an existing working project, use `prism serve PROJECT --open`. Browser
opening is opt-in and occurs only after the actual loopback port is bound. If
the operating system declines the request, the command prints a warning and
continues serving the URL. This surface is loopback-only and is not suitable as
an authenticated remote deployment.

To reproduce the Phase 8 gate from a checkout after installing Chromium, point
the acceptance driver at the interpreter containing the wheel under test:

```powershell
uv run python examples/12_reproducible_poc.py `
  --app-python .\.wheel-smoke\Scripts\python.exe
```

The driver uses Playwright from the development environment; the selected
application environment contains only the wheel and its runtime dependencies.

On Linux, the equivalent path is:

```bash
uv tool install --python 3.12 ./dist/prism-0.1.0.dev0-py3-none-any.whl
prism version
```

If the `prism` command is not found after installation, run
`uv tool update-shell` and reopen the terminal. `uv tool install` gives the CLI
its own isolated environment and puts its executable in a tool bin directory.

## Install a published release

After a stable release has been published to PyPI, the normal user flow will
be:

```bash
uv tool install --python 3.12 prism
prism --help
```

For a one-off invocation without a persistent installation:

```bash
uvx --python 3.12 prism --help
```

Developers can continue using a checkout with `uv sync`, while coding agents
and end users should consume a tagged package version. This keeps the tool
environment separate from the project being edited.

## Audio and plugin runtime dependencies

The package is Python-first, but the audio boundary uses native libraries.
`sounddevice` uses PortAudio, and Linux installations may need a distribution
package for PortAudio. `soundfile` may likewise need the system `libsndfile`
library on Linux installations where a compatible wheel is unavailable. The
exact package names differ by distribution; for Debian/Ubuntu, a typical
starting point is:

```bash
sudo apt-get install libportaudio2 libsndfile1
```

Verify the packages against the target distribution before putting them in an
installer or deployment image. See the [`sounddevice` installation guide](https://python-sounddevice.readthedocs.io/en/latest/)
and [`soundfile` documentation](https://python-soundfile.readthedocs.io/en/latest/index.html).

Windows playback is exposed by the Python `prism.audio` package and the
Phase 6 `audio devices`, `audio restart`, `transport`, and `session` CLI groups.
Run the normal device-free suite with:

```powershell
uv run pytest -m "not audio_device and not browser"
```

On a Windows machine with a stereo output device, run the opt-in hardware
smoke test:

```powershell
uv run pytest -m audio_device -s
```

The backend uses the OS default output device unless an explicit device index
or name is supplied by the embedding application. It requests the project
sample rate and reports device-open, callback, and underrun failures through
typed backend state. It does not install, bundle, or redistribute PortAudio
device drivers or third-party plugins.

Phase 9 VST3 support uses plugins installed by the user. Prism must not copy,
redistribute, or silently install third-party plugin binaries. The Python host
is also optional: install it with `uv sync --extra plugins` (or install the
published `prism[plugins]` extra). Plugin licensing and binary installation
remain outside the Prism package. Search paths, exact-hash trust, and registry
metadata are machine-local; portable projects contain identity, normalized
controls, and bounded opaque state only. See [Phase 9](PHASE_9.md).

## CI versus CD

These terms describe different responsibilities:

- **Continuous integration (CI):** run tests, lint checks, and smoke checks on
  pushes and pull requests. The repository validates Windows and Linux and runs
  a clean-wheel acceptance job on Windows.
- **Continuous delivery/deployment (CD):** build and publish release artifacts
  after an intentional release event, normally a version tag or GitHub Release.

CD is not required to build a package. The local `uv build` command is enough
for development and manual testing. CD becomes valuable when releases should
be repeatable, auditable, and available to other machines without manually
repeating the build steps.

## Recommended release pipeline

The first release pipeline should publish the Python distributions. It should
run only for version tags such as `v0.1.0`:

1. Update the project version and lockfile.
2. Run the complete test, lint, and CLI smoke suite.
3. Build the wheel and source archive with `uv build --no-sources`.
4. Install the built wheel into a clean environment and run `prism --help`
   and `prism version`.
5. Upload `dist/` as GitHub Actions artifacts and attach them to the GitHub
   Release.
6. Publish the same artifacts to PyPI with `uv publish`.
7. Verify installation from PyPI in a clean Windows environment and, once Linux
   support is in the test matrix, a clean Linux environment.

The package distributions are platform-independent at this stage, so they do
not need to be built once per operating system. The test matrix should still
cover every supported operating system because dependency installation and
audio behavior can differ.

For GitHub Actions, use separate jobs for validation, packaging, and publishing:

```text
tag v0.1.0
  → validate on supported OSes
  → build one package artifact
  → test-install that exact artifact
  → attach artifacts to GitHub Release
  → publish the exact artifacts to PyPI
```

Configure PyPI's trusted publisher for the repository instead of storing a
long-lived PyPI token in GitHub secrets. The `uv publish` documentation covers
both token-based publishing and trusted publishers.

The workflow should pin third-party GitHub Actions to commit SHAs, as the
existing CI workflow does, and should never publish from an ordinary pull
request. A release tag should be the only event that can publish.

## Versioning and release commands

The package version in `pyproject.toml` must match the release tag. `uv` can
update the version and refresh the lockfile:

```powershell
uv version 0.1.0
uv lock
uv build --no-sources
```

Then create and push the release tag through the normal repository review
process:

```powershell
git tag v0.1.0
git push origin v0.1.0
```

The release workflow should reject a tag whose version does not match the
package metadata. Published package files are immutable for a given version,
so a broken release should receive a new version rather than being overwritten.

## Future standalone packages

A standalone package is useful when a user should not need to install Python.
It is a separate build product from the wheel:

- **Windows:** build a Prism executable on `windows-latest`, test it on a
  clean Windows machine, and initially distribute a ZIP or executable. An MSI
  or winget package can follow.
- **Linux:** build on a Linux runner and initially distribute a tarball. An
  AppImage or distribution-specific `.deb`/`.rpm` package can follow.

PyInstaller is one candidate for bundling the Python application, but its
bootloader and bundled dependencies are platform-specific. Build Windows
artifacts on Windows and Linux artifacts on Linux; do not treat one runner's
output as portable to the other operating system. See the
[PyInstaller documentation](https://pyinstaller.org/_/downloads/en/latest/pdf/).

Standalone builds should be added only after there is a stable application
launcher for the CLI and local web service. They also need separate smoke tests
for project creation, project loading, audio import, and clean shutdown.

## Deployment roadmap

1. **Now:** build and test the wheel locally with `uv build`.
2. **First release:** add a tag-triggered workflow that publishes the wheel and
   source archive to GitHub Releases and PyPI.
3. **Linux support:** add Linux CI and document the required audio system
   libraries for supported distributions.
4. **Standalone CLI:** add Windows executable and Linux portable artifacts.
5. **Desktop release:** add signed Windows/Linux installers after the GUI and
   audio engine stabilize.
6. **Plugin-aware release:** validate the optional `plugins` extra and discovery
   diagnostics without bundling third-party plugin binaries.

## Release checklist

- [ ] The version in `pyproject.toml` matches the release tag.
- [ ] `uv sync --locked --extra dev` succeeds from a clean checkout.
- [ ] Tests, lint, and CLI smoke checks pass on every supported OS.
- [ ] `uv build --no-sources` creates the expected wheel and source archive.
- [ ] The wheel installs into a clean Python 3.12 environment.
- [ ] `prism version` and `prism --help` work after installation.
- [ ] The release contains checksums or attestations when that process is added.
- [ ] PyPI publishing uses a trusted publisher or a short-lived token.
- [ ] Audio system dependencies are documented for the target OS.
- [ ] VST3 plugins remain user-installed and are not included in the artifact.

## Related documentation

- [README](../README.md)
- [Implementation plan](IMPLEMENTATION_PLAN.md)
- [Phase 7 browser session](PHASE_7.md)
- [Phase 8 reproducible POC](PHASE_8.md)
- [Phase 9 isolated VST3 worker](PHASE_9.md)
- [uv package guide](https://docs.astral.sh/uv/guides/package/)
- [uv tools guide](https://docs.astral.sh/uv/guides/tools/)
