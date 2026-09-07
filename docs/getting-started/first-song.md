# Create your first song

From the Prism repository root, run:

```text
uv run prism create my-song
```

Prism creates a timestamped folder under `projects/` and prints its exact run
command. It will look similar to:

```text
uv run "projects/my-song-20260828-143500/main.py"
```

Copy and run the command Prism printed. It creates:

- `renders/song.wav`, which you can open in your normal music player;
- `renders/song.mid`, which you can import into music software.

Open the new `main.py` in any text editor. Change the tempo, notes, or rhythm,
save it, and run the same command again. Prism replaces the generated files
with the new version.

## Build and render separately

New projects expose a build() -> Project function. It only constructs the
song, so agents and tools can inspect or validate it without creating output:

~~~text
uv run prism doctor projects/your-project
uv run prism doctor projects/your-project --build --json
~~~

Render is explicit and lets you choose the output path and delivery profile:

~~~text
uv run prism render projects/your-project --profile listening
uv run prism render projects/your-project --output renders/master.wav --profile master
~~~

The render command executes build(), validates the returned Project, and writes
only the requested delivery file. Build validation executes project Python in
the current interpreter; it is not a security sandbox.

## Start directly with the tutorial

You can also ask Prism to create a tutorial starting point:

```text
uv run prism create --tutorial
```

Then open the [tutorial learning path](../tutorial/README.md) and work through
the levels using that folder.
