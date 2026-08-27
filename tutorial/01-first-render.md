# Level 1 — make your first render

Goal: understand the smallest complete Prism project and hear its result.

## 1. Create the folder

From the Prism repository root:

```powershell
New-Item -ItemType Directory -Force .\tutorial-song | Out-Null
```

## 2. Write the complete `main.py`

Save this as `tutorial-song\main.py`:

```python
from prism import Project


song = Project(
    __file__,
    "My First Beat",
    tempo=120,
)

kick = song.track("Kick", gain_db=-3).drum(
    "kick",
    "x--- x--- x--- x---",
)

song.section(
    "Loop",
    bars=4,
    tracks=[kick],
)

print(song.validate())
result = song.render("renders/song.wav")
print(result)
print("SHA-256:", result.sha256)
```

Read it from top to bottom: create a song, create a track, give the track a
part, arrange a section, then render. There are no IDs, requests, servers, or
configuration files to maintain.

`x` is a kick hit and `-` is a rest. Spaces only make the four beats easier to
see.

## 3. Run it

```powershell
uv run python .\tutorial-song\main.py
```

Expected summary:

```text
My First Beat: 1 tracks, 1 sections, 4 bars, 8.00 seconds
```

## 4. Listen

```powershell
Start-Process .\tutorial-song\renders\song.wav
```

This uses your normal audio player. Prism itself performs device-free offline
rendering.

## 5. Make one musical change

Change the pattern to:

```python
"x--- x-x- x--- x-x-"
```

Run `main.py` again and listen. The script safely replaces the old render.

Checkpoint: you can explain every statement in the project file and reproduce
the WAV by running one ordinary Python command.
