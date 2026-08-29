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

## Start directly with the tutorial

You can also ask Prism to create a tutorial starting point:

```text
uv run prism create --tutorial
```

Then open the [tutorial learning path](../tutorial/README.md) and work through
the levels using that folder.
