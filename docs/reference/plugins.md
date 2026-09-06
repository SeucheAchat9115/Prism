# Plugins and automation

## Plugin

::: prism.Plugin

## AutomationLane

::: prism.AutomationLane

## AutomationPoint

::: prism.AutomationPoint

## VST3

::: prism.VST3

`VST3("alias")` can be passed to `Track.midi`, `Track.instrument`,
`Track.effect`, `Bus.effect`, or `Project.master_effect`. Parameter values are
normalized from `0.0` to `1.0`. See the
[external VST3 guide](../guides/external-vst3.md) for registry and inspection
commands. Instrument VST3 declarations are owned by their track; equivalent
clips reuse the same stable instance, while timed changes belong in automation.

## VSTRegistry

::: prism.VSTRegistry

Stock-plugin definitions and their code registry are contributor internals. See the
[plugin architecture](../plugins/index.md) when developing a new stock plugin.
