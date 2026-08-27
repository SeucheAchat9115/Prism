# Level 0 — create an editable project folder

Goal: use Prism's only CLI operation to create a starting point, run it, and
listen to the result. The command creates a normal directory, not an archive.

From the Prism repository root:

```powershell
uv sync --locked --extra dev
uv run prism create tutorial-song --name "Tutorial Song" --tempo 112
```

Prism prints the created path and run command. Inspect the result:

```powershell
Get-ChildItem .\tutorial-song
Get-Content .\tutorial-song\main.py
```

You now have:

```text
tutorial-song/
├── main.py      editable song, parameters, arrangement, and render calls
├── sounds/      put project-local WAV or AIFF files here
└── renders/     generated WAV and MIDI files go here
```

Run the generated song and listen:

```powershell
uv run python .\tutorial-song\main.py
Start-Process .\tutorial-song\renders\song.wav
```

After rendering, `.prism/project.json` appears inside the same folder. It is a
generated manifest; `main.py` remains the source of truth.

Prism protects existing work. Running the same create command again reports an
error instead of replacing `main.py`:

```powershell
uv run prism create tutorial-song
```

You can also invoke the same command through Python:

```powershell
uv run python -m prism create another-song --tempo 96
```

Checkpoint: you can edit `tutorial-song\main.py`, rerun it, and hear a changed
render without unpacking, importing, or converting a project file.
