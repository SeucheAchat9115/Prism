# Troubleshooting

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
