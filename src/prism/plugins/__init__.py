"""Opt-in, isolated VST3 hosting for Prism."""

from prism.plugins.client import PluginWorkerClient
from prism.plugins.config import PluginConfigStore, default_config_path, matching_trust
from prism.plugins.errors import (
    PluginConfigError,
    PluginError,
    PluginTrustError,
    PluginUnavailableError,
    PluginWorkerError,
    PluginWorkerTimeoutError,
)
from prism.plugins.manager import PluginManager
from prism.plugins.registry import (
    PluginRegistry,
    discover_vst3,
    fingerprint_plugin_binary,
    registry_id_for,
)
from prism.plugins.render import IsolatedPluginRenderProcessor
from prism.plugins.types import (
    PluginCompatibility,
    PluginConfig,
    PluginParameter,
    PluginRecord,
    PluginRegistryDocument,
    PluginTrustRecord,
    PluginWorkerStatus,
)

__all__ = [
    "PluginCompatibility",
    "PluginConfig",
    "PluginConfigError",
    "PluginConfigStore",
    "PluginError",
    "PluginManager",
    "PluginParameter",
    "PluginRecord",
    "PluginRegistry",
    "PluginRegistryDocument",
    "PluginTrustError",
    "PluginTrustRecord",
    "PluginUnavailableError",
    "PluginWorkerClient",
    "PluginWorkerError",
    "PluginWorkerStatus",
    "PluginWorkerTimeoutError",
    "IsolatedPluginRenderProcessor",
    "default_config_path",
    "discover_vst3",
    "fingerprint_plugin_binary",
    "matching_trust",
    "registry_id_for",
]
