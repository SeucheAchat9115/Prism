# Install Prism

## 1. Install uv once

If `uv --version` already works, continue to the next step.

=== "Windows PowerShell"

    ```powershell
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    ```

=== "Linux"

    ```bash
    curl -LsSf https://astral.sh/uv/install.sh | sh
    ```

Close and reopen your terminal if `uv` is not found immediately.

## 2. Prepare Prism once

Open a terminal in the downloaded Prism repository and run:

```text
uv sync --locked
```

uv installs the correct Python version and Prism's audio dependencies. You can
now create and render projects without managing Python yourself.

If a project uses external VST3 instruments or effects, run this instead:

```text
uv sync --extra vst3
```

This is unnecessary for Uniwave, stock plugins, samples, and ordinary audio
projects. Read [Use external VST3 plugins](../guides/external-vst3.md) before
registering a third-party plugin.

!!! tip
    If Prism changes after a pull or download, run `uv sync --locked` again.

## 3. Confirm the installation

```text
uv run prism --help
```

You should see Prism's project creation command. Continue with
[your first song](first-song.md).
