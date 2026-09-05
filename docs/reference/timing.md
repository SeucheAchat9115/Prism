# Musical timing

Prism uses one quarter note as its canonical internal musical beat. The
`MusicalTiming` object converts absolute bars or quarter-note positions to
seconds, integer sample-frame boundaries, and explicitly quantized MIDI ticks.
Its interface is deliberately small so a future tempo-map implementation can
replace the constant-tempo conversion without changing producer-facing
coordinates.

## MusicalTiming

::: prism.timing.MusicalTiming

## TimeSignature

::: prism.timing.TimeSignature

## TimingMap

::: prism.timing.TimingMap
