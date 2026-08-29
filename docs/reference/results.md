# Render and MIDI results

Prism returns immutable result objects after validation, WAV rendering, and
MIDI export. Printing one gives a friendly status line; its fields can be used
for reproducibility checks and automation.

## RenderResult

::: prism.RenderResult

## StemRenderResult

::: prism.StemRenderResult

Its `tracks` and `buses` fields contain `StemFile` objects in the same order
as the channels in `main.py`. `master` is the final file, and `files` returns
all three groups together. Every file has the result's sample rate, channel
count, frame count, and duration.

## StemFile

::: prism.StemFile

## MidiResult

::: prism.MidiResult
