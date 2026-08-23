# ADR 0001: Working-project storage

Status: Accepted

VibeSound opens a portable `demo.vibesound` archive into an adjacent,
inspectable `demo.vibesound-work/` directory. The portable archive remains
unchanged until an explicit export. Working-format metadata, locks, staging,
caches, and job state live below `.vibesound/`; project metadata, immutable
audio assets, revision records, and exports remain ordinary files.

The working representation is disposable without modifying its source archive.
It is versioned independently from the portable project schema and uses atomic
metadata replacement plus immutable asset files for recovery.
