# Troubleshooting

## VST3 support is not installed

Run `uv sync --extra vst3` from the Prism repository root, then rerun the
project.

## A registered VST3 has changed

Prism's checksum no longer matches the file. If you intentionally updated the
plugin, register the new binary with `prism plugins add ... --replace`. Do not
replace the checksum until you know why it changed.

## A VST parameter does not exist or is ambiguous

Run `prism plugins inspect PROJECT ALIAS --search TEXT`. Copy the exact name,
or the `#INDEX: Name` selector if names are duplicated. Plugin versions can
expose different parameter lists.

## A VST project renders differently elsewhere

Confirm the other computer has the same plugin build and that its SHA-256
matches `vst.json`. Third-party plugins can depend on their own content,
licenses, CPU behavior, and private state. Keep relevant files in
`plugin-states/` and use the same plugin version.

## `uv` is not recognized

Close and reopen the terminal after installing uv. If it still fails, repeat
the command for your operating system in [Install Prism](../getting-started/installation.md).

## Prism cannot find a sample

Check that the audio file is inside the same timestamped project folder as
`main.py` and that the spelling and extension match exactly:

```python
song.track("Kick").sample("sounds/kick.wav", "x--- x--- x--- x---")
```

Linux filenames are case-sensitive, so `Kick.wav` and `kick.wav` differ.

## Prism rejects a path

Use a relative path inside the project. Absolute paths and paths containing
`..` are intentionally rejected so copied projects remain self-contained.

## The WAV is silent or unexpectedly quiet

Check that the project has a section, the intended track is included in it,
the track and its bus are not muted, and gains are not close to `-60 dB`.
Also check that note or clip positions fall inside the section.

## An automation parameter is rejected

Only registered numeric parameters can be automated. Check the effect or
Uniwave parameter name in the [parameter reference](../tutorial/10-parameter-reference.md).
Automation points must have increasing, non-negative bar positions and values
inside the documented range.

## A render differs between computers

Keep `prism_version` in `main.py`, use the locked environment, retain explicit
humanization and noise seeds, and keep every source sample with the project.
`RenderResult.sha256` identifies exact WAV bytes after rendering.

## Documentation does not build locally

From the repository root, run:

```text
uv run --extra docs mkdocs build --strict
```

The error names the page containing an invalid reference or generated API
entry. Use `uv run --extra docs mkdocs serve` for a live local preview.
