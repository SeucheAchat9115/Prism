# Render and MIDI results

Prism returns immutable result objects after validation, WAV rendering, and
MIDI export. Printing one gives a friendly status line; its fields can be used
for reproducibility checks and automation.

`sample_rate`, `channels`, `frames`, and `duration_seconds` describe the
delivered WAV. `bit_depth` is 16, 24, or 32; 32 means floating point.
`tail_seconds` records the requested time added after the arrangement.

`RenderResult.export_profile` and `StemRenderResult.export_profile` contain the
JSON-safe delivery profile used for the export. `diagnostics` reports the
delivery-domain peak before and after normalization plus overload and clipping
counts. `ExportProfile` exposes peak normalization, explicit fixed-point
clipping policy, and seeded integer-only TPDF dither; it does not implement
loudness normalization.

## ExportProfile

::: prism.ExportProfile

## ExportDiagnostics

::: prism.ExportDiagnostics

## RenderResult

::: prism.RenderResult

## StemRenderResult

::: prism.StemRenderResult

Its `tracks` and `buses` fields contain `StemFile` objects in the same order
as the channels in `main.py`. `master` is the final file, and `files` returns
all three groups together. `directory` is the completed versioned generation,
and `generation` is its manifest generation number. Every file has the
result's sample rate, channel count, frame count, bit depth, tail length, and
duration.

`StemRenderResult.delivery` is a `StemDeliveryContract`. In
`master_inputs` mode it names the pre-master reconstruction target, records
that master processing is excluded from that target, and identifies whether
stem dither was requested.

## StemFile

::: prism.StemFile

## StemDeliveryContract

::: prism.StemDeliveryContract

## MidiResult

::: prism.MidiResult
