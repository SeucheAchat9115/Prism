# Python reference

These pages are generated directly from Prism's public Python objects. Method
signatures, defaults, properties, and type annotations therefore stay aligned
with the installed package.

Use the reference when you know what you want to call and need the exact
spelling or accepted type. For musical explanations and complete runnable
files, use the [tutorials](../tutorial/README.md) and [guides](../guides/concepts.md).

## Public imports

Producer scripts normally import from the small top-level package:

```python
from prism import (
    Note,
    Project,
    SynthWave,
    Uniwave,
)
```

The remaining public result, routing, automation, and error types are available
from the same `prism` import. Internal renderer and registry helpers are not part
of the producer-facing compatibility surface.
