
# Level 23 — Build explicitly and inspect safely

Earlier levels export as soon as Python reaches the end of the file. The public
build contract separates describing a song from delivering files:

- build() -> Project constructs the song and returns it;
- prism render builds, validates, and writes one selected WAV;
- prism doctor inspects the source and project files without executing them;
- prism doctor --build opts into executing and validating the build.

The build function should have no rendering or file-export side effects:

~~~python
from prism import Project, Uniwave


def build() -> Project:
    song = Project(
        "Contract Song",
        prism_version="0.2.0.dev0",
        tempo=112,
    )

    kick = song.track("Kick", gain_db=-3).drum(
        "kick",
        "x--- x--- x--- x---",
    )
    bass = song.track("Bass", gain_db=-6).midi(
        "C2 - C2 Eb2 | G1 - Bb1 -",
        instrument=Uniwave.bass(),
        bars=2,
    )
    song.section("Loop", bars=4, tracks=[kick, bass])
    return song


if __name__ == "__main__":
    song = build()
    print(song.validate())
    print(song.render("renders/song.wav"))
~~~

Run the build through the CLI from the repository root:

~~~text
uv run prism render projects/your-project/main.py --profile listening
uv run prism render projects/your-project --output renders/master.wav --profile master
uv run prism doctor projects/your-project
uv run prism doctor projects/your-project --build --json
~~~

The render command skips the main guard, so a clean build does not create
output files until the render operation is requested. The named profiles are
delivery presets; a JSON file can also describe an ExportProfile.

Notebook and agent code can resolve a project without relying on the process
location:

~~~python
from pathlib import Path
from prism import Project, resolve_project_root

project_root = resolve_project_root(Path("/work/projects/contract-song"))
song = Project(
    "Notebook Song",
    prism_version="0.2.0.dev0",
    project_root=project_root,
)
~~~

Running build() executes the project's Python in the current interpreter. It
is not a security sandbox, so only build sources you trust. The default doctor
path is metadata-only: it parses source, checks dependencies and registered
plugins, and lists audio files without running main.py.

Older top-level-export scripts remain runnable directly with their printed
command. When the CLI sees one, it reports the migration: move construction
into build(), return the Project, and put validation and exports under the
Python main guard. Prism does not rewrite arbitrary Python source for you.
