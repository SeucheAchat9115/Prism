# Errors

Prism raises focused exceptions with producer-readable messages. Catch
`PrismError` when a tool or agent needs to report any expected Prism failure.

## PrismError

::: prism.PrismError

## ProjectError

::: prism.ProjectError

## RenderError

::: prism.RenderError

## AgentError

The public agent API serializes this exception as a stable error object with a
`code`, readable `message`, and structured `details` mapping. See the
[agent contract](agent.md) for operation-level errors.

::: prism.AgentError
