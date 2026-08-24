from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from prism.plugins import (
    PluginConfigStore,
    PluginManager,
    PluginRegistry,
    PluginTrustError,
    PluginUnavailableError,
    discover_vst3,
)
from prism.project.models import PluginInstance, Track, new_project


def test_discovery_requires_exact_trust_before_probe(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    root.mkdir()
    binary = root / "Gain.vst3"
    binary.write_bytes(b"v1")
    store = PluginConfigStore(tmp_path / "config" / "plugins.json")
    store.add_search_path(root)
    registry = PluginRegistry(store.registry_path)
    probes: list[Path] = []

    def probe(path: Path) -> list[dict[str, str]]:
        probes.append(path)
        return [
            {
                "plugin_identifier": "com.example.gain",
                "name": "Example Gain",
                "manufacturer": "Prism Tests",
                "version": "1.0",
                "category": "Fx",
            }
        ]

    untrusted = registry.scan(store.load(), probe)
    assert not probes
    assert not untrusted.plugins[0].trusted
    assert not untrusted.plugins[0].available

    trust = store.trust_plugin(binary)
    trusted = registry.scan(store.load(), probe)
    assert probes == [binary.resolve()]
    assert trusted.plugins[0].available
    assert trusted.plugins[0].binary_sha256 == trust.binary_sha256
    assert registry.load() == trusted

    binary.write_bytes(b"v2")
    changed = registry.scan(store.load(), probe)
    assert probes == [binary.resolve()]
    assert not changed.plugins[0].available
    assert "changed" in (changed.plugins[0].error or "").lower()


def test_discovery_does_not_descend_into_vst3_bundles(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    bundle = root / "Outer.vst3"
    nested = bundle / "Contents" / "Nested.vst3"
    nested.mkdir(parents=True)
    (nested / "binary").write_bytes(b"nested")

    assert discover_vst3([str(root)]) == (bundle.resolve(),)


def test_manager_reports_ready_changed_untrusted_and_missing_instances(
    tmp_path: Path,
) -> None:
    root = tmp_path / "plugins"
    root.mkdir()
    binary = root / "Gain.vst3"
    binary.write_bytes(b"gain")
    store = PluginConfigStore(tmp_path / "config" / "plugins.json")
    store.add_search_path(root)
    store.trust_plugin(binary)
    registry = PluginRegistry(store.registry_path)
    record = registry.scan(
        store.load(),
        lambda _path: [{"plugin_identifier": "gain", "name": "Gain"}],
    ).plugins[0]

    class QuietWorker:
        def close(self) -> None:
            return None

    manager = PluginManager(store, QuietWorker())  # type: ignore[arg-type]
    effect = PluginInstance(
        registry_id=record.registry_id,
        plugin_identifier=record.plugin_identifier,
        binary_sha256=record.binary_sha256,
        name=record.name,
    )
    project = new_project("Compatibility")
    project.tracks = [Track(name="Track", effects=[effect])]

    assert manager.compatibility(project)[0].status == "ready"
    effect.binary_sha256 = "b" * 64
    assert manager.compatibility(project)[0].status == "changed"
    with pytest.raises(PluginTrustError, match="project instance"):
        manager.load_instance(effect, sample_rate=48000, state=None)

    effect.binary_sha256 = record.binary_sha256
    effect.bypassed = True
    assert manager.compatibility(project)[0].status == "bypassed"
    effect.bypassed = False
    store.revoke_plugin(binary)
    assert manager.compatibility(project)[0].status == "untrusted"

    binary.unlink()
    assert manager.compatibility(project)[0].status == "missing"
    with pytest.raises(PluginUnavailableError, match="scan first"):
        manager.require_record(uuid4())
    with pytest.raises(PluginUnavailableError, match="not loaded"):
        manager.parameters(effect.id)
    manager.close()


def test_registry_keeps_plugin_instruments_unavailable(tmp_path: Path) -> None:
    root = tmp_path / "plugins"
    root.mkdir()
    binary = root / "Synth.vst3"
    binary.write_bytes(b"synth")
    store = PluginConfigStore(tmp_path / "config" / "plugins.json")
    store.add_search_path(root)
    store.trust_plugin(binary)

    record = PluginRegistry(store.registry_path).scan(
        store.load(),
        lambda _path: [
            {
                "plugin_identifier": "com.example.synth",
                "name": "Synth",
                "category": "Instrument|Synth",
            }
        ],
    ).plugins[0]

    assert record.trusted
    assert not record.available
    assert record.error == "Plugin instruments are not supported in Phase 9."
