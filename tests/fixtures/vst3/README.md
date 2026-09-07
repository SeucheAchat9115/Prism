# Reproducible VST3 qualification fixtures

The real-plugin workflow builds four small fixtures for every Windows and Linux
run instead of checking platform binaries into Prism:

- `prism-fixture-instrument.vst3` uses the upstream MDA Piano example for a
  deterministic MIDI-triggered instrument, state round trips, and channel
  layout checks.
- `prism-fixture-delay.vst3` uses the upstream ADelay example for a measurable
  impulse delay, parameter automation, and state round trips.

Both targets are built from the pinned `steinbergmedia/vst3sdk` commit recorded
in `.github/workflows/vst-ci.yml`. The workflow verifies that the checkout is
exactly that commit before configuring CMake; no downloaded plugin is trusted by
an unpinned version or a runtime-discovered checksum. The SDK and the two
upstream examples carry their own upstream license notices; the current SDK
release documents the SDK license in its `LICENSE.txt` and README.

To build locally after obtaining the pinned SDK checkout:

```sh
cmake -S tests/fixtures/vst3 -B build/vst3-fixtures \
  -DPRISM_VST3_SDK_ROOT="$PWD/../vst3sdk"
cmake --build build/vst3-fixtures --config Release \
  --target prism-fixture-delay prism-fixture-instrument
```

The portable Python suite never requires these binaries. The real VST suite is
the qualification record: its diagnostics directory contains a small WAV and
JSON metrics bundle for each executed fixture or Surge test.

The audit follow-up adds `prism-fixture-latency.vst3` and
`prism-fixture-mono.vst3`, built from Prism's `plugin/latency.cpp` (GPL-3.0-only)
against the same pinned SDK. Both delay input by exactly 64 samples, report that
latency, apply a normalized Gain parameter before the delay, and serialize the
gain as a little-endian double component state. The mono variant averages stereo
input and exposes one output channel. They are deliberately small measurement
fixtures, not production effects. Build both additional targets when running the
full qualification suite locally.
