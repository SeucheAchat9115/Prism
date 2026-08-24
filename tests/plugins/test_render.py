from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import numpy as np
from engine._helpers import make_project

from prism.engine import SessionEngine
from prism.plugins import PluginConfigStore, PluginRegistry, PluginWorkerError
from prism.plugins.render import IsolatedPluginRenderProcessor
from prism.project.models import PluginInstance, Track, new_project
from prism.project.repository import RepositorySnapshot


class _GainWorker:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.loads: list[object] = []
        self.restart_count = 0

    def load(self, instance_id, path, plugin_identifier, **kwargs):
        self.loads.append((instance_id, path, plugin_identifier, kwargs))
        return []

    def process(self, instance_id, samples, sample_rate, *, reset=False):
        del instance_id, sample_rate, reset
        if self.fail:
            raise PluginWorkerError("simulated crash")
        return np.asarray(samples, dtype=np.float32) * 2

    def restart(self):
        self.restart_count += 1

    def close(self):
        return None


def _snapshot_with_effect(
    tmp_path: Path,
    worker: _GainWorker,
) -> tuple[RepositorySnapshot, PluginConfigStore, PluginInstance]:
    root = tmp_path / "plugins"
    root.mkdir()
    binary = root / "Gain.vst3"
    binary.write_bytes(b"gain")
    store = PluginConfigStore(tmp_path / "config" / "plugins.json")
    store.add_search_path(root)
    store.trust_plugin(binary)
    document = PluginRegistry(store.registry_path).scan(
        store.load(),
        lambda _path: [{"plugin_identifier": "gain", "name": "Gain"}],
    )
    record = document.plugins[0]
    effect = PluginInstance(
        registry_id=record.registry_id,
        plugin_identifier=record.plugin_identifier,
        binary_sha256=record.binary_sha256,
        name=record.name,
    )
    project = new_project("Plugin render")
    project.tracks = [Track(name="Track", effects=[effect])]
    snapshot = RepositorySnapshot(project, tmp_path, {}, {})
    del worker
    return snapshot, store, effect


def test_session_engine_applies_track_processor_before_mixer() -> None:
    effect = PluginInstance(
        registry_id=uuid4(),
        plugin_identifier="gain",
        binary_sha256="0" * 64,
        name="Gain",
    )
    samples = np.ones((4, 1), dtype=np.float32)
    project, provider, track, scene, _ = make_project(
        samples,
        track=Track(name="Track", effects=[effect]),
    )

    class Doubler:
        def process(self, track_id, block, sample_rate):
            assert track_id == track.id
            assert sample_rate == project.transport.sample_rate
            return block * 2

    effected = SessionEngine(project, provider, effect_processor=Doubler())
    dry_project = project.model_copy(deep=True)
    dry_project.tracks[0].effects = []
    dry = SessionEngine(dry_project, provider)
    for engine in (effected, dry):
        engine.play()
        engine.launch_slot(track.id, scene.id)

    assert np.allclose(effected.advance(4).samples, dry.advance(4).samples * 2)


def test_explicitly_bypassed_effect_keeps_the_exact_dry_mixer_path() -> None:
    effect = PluginInstance(
        registry_id=uuid4(),
        plugin_identifier="gain",
        binary_sha256="0" * 64,
        name="Gain",
        bypassed=True,
    )
    samples = np.linspace(-1.0, 1.0, 8, dtype=np.float32).reshape(4, 2)
    project, provider, track, scene, _ = make_project(
        samples,
        track=Track(name="Track", effects=[effect]),
    )

    class MustNotRun:
        def process(self, track_id, block, sample_rate):
            raise AssertionError((track_id, block, sample_rate))

    bypassed = SessionEngine(project, provider, effect_processor=MustNotRun())
    dry_project = project.model_copy(deep=True)
    dry_project.tracks[0].effects = []
    dry = SessionEngine(dry_project, provider)
    for engine in (bypassed, dry):
        engine.play()
        engine.launch_slot(track.id, scene.id)

    assert np.array_equal(bypassed.advance(4).samples, dry.advance(4).samples)


def test_render_processor_restarts_once_then_bypasses_dry(tmp_path: Path) -> None:
    worker = _GainWorker(fail=True)
    snapshot, store, effect = _snapshot_with_effect(tmp_path, worker)
    events: list[tuple[str, dict[str, object]]] = []
    processor = IsolatedPluginRenderProcessor(
        snapshot,
        store=store,
        publisher=lambda name, payload: events.append((name, payload)),
        worker=worker,  # type: ignore[arg-type]
    )
    source = np.ones((8, 2), dtype=np.float32)
    try:
        output = processor.process(snapshot.project.tracks[0].id, source, 44100)
    finally:
        processor.close()

    assert np.array_equal(output, source)
    assert worker.restart_count == 1
    assert [name for name, _ in events] == [
        "plugin.worker.failed",
        "plugin.instance.bypassed",
    ]
    assert effect.id in processor._failed


def test_render_processor_uses_dry_audio_when_binary_disappears(tmp_path: Path) -> None:
    worker = _GainWorker()
    snapshot, store, effect = _snapshot_with_effect(tmp_path, worker)
    record = PluginRegistry(store.registry_path).get(effect.registry_id)
    assert record is not None
    Path(record.path).unlink()
    events: list[tuple[str, dict[str, object]]] = []
    processor = IsolatedPluginRenderProcessor(
        snapshot,
        store=store,
        publisher=lambda name, payload: events.append((name, payload)),
        worker=worker,  # type: ignore[arg-type]
    )
    source = np.ones((8, 2), dtype=np.float32)
    try:
        output = processor.process(snapshot.project.tracks[0].id, source, 44100)
    finally:
        processor.close()

    assert np.array_equal(output, source)
    assert events[0][0] == "plugin.instance.bypassed"
    assert effect.id in processor._failed
