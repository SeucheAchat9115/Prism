# Plugin architecture

Prism stock plugins are deterministic offline instruments and effects shipped
inside the package. Producers use them from `main.py`; contributors can add one
by creating a single implementation file and registering it.

```text
MIDI notes or triggers
        ↓
instrument plugin
        ↓
effect 1 → effect 2 → effect 3
        ↓
track mixer → buses and sends → master effects
        ↓
WAV render
```

Each plugin file owns its public parameter schema, defaults, validation ranges,
and DSP callback. The central registry makes that definition available to
authoring, rendering, configuration inspection, MIDI export, and automation.

## Instrument plugins

An instrument turns note or trigger events into audio. Prism includes generated
drums, simple melodic presets, sample/audio players, and the multi-oscillator
Uniwave synthesizer.

## Effect plugins

An effect receives stereo audio plus one value per frame for each numeric
parameter. Static settings and automated settings therefore use the same DSP
path. Effects preserve the input length and run in the order the producer adds
them.

## Automation

Every suitable numeric parameter declared by an effect becomes an automation
target. Instruments expose supported controls in the same way. An automation
lane belongs to the song, points to one plugin instance, and changes exactly one
parameter.

Read [Add a stock plugin](adding-stock-plugins.md) for the complete contributor
workflow, design rules, registry change, and required tests.
