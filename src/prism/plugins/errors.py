"""Plugin subsystem errors that remain safe across the process boundary."""


class PluginError(Exception):
    """Base class for expected plugin failures."""


class PluginConfigError(PluginError):
    """Machine-local configuration is invalid or cannot be persisted."""


class PluginTrustError(PluginError):
    """A plugin was not approved for its current bytes."""


class PluginUnavailableError(PluginError):
    """The optional host or requested plugin is unavailable."""


class PluginWorkerError(PluginError):
    """The isolated worker rejected a request or exited unexpectedly."""


class PluginWorkerTimeoutError(PluginWorkerError):
    """The isolated worker exceeded a bounded request deadline."""
