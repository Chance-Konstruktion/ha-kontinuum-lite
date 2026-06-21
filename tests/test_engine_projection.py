"""LiteEngine projection tests with a small fake ``kontinuum_core``.

These tests stay HA-free and do not require the external core package. They pin
integration behavior at the wrapper boundary: payload normalization, snapshot
projection, and the legacy no-persistence path.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
from dataclasses import dataclass
from typing import Any

_ROOT = (
    pathlib.Path(__file__).resolve().parents[1]
    / "custom_components"
    / "kontinuum_lite"
)


@dataclass
class _CoreSnapshot:
    surprise: float = 0.25
    anomaly: bool = True
    learning_state: str = "learning"
    tick_count: int = 7
    token: str | None = "kitchen.motion.on"
    extra: dict[str, Any] | None = None


class _ProjectingCore:
    """Fake modern core that records exactly what the wrapper passes in."""

    def __init__(self, scheduler=None, storage_path=None) -> None:
        self.scheduler = scheduler
        self.storage_path = storage_path
        self.payloads: list[dict[str, Any]] = []
        self.tick_count = 7
        self.hippocampus = types.SimpleNamespace(total_events=3)

    def register_entity(self, entity_id: str, **kwargs: Any) -> None:
        self.registered = (entity_id, kwargs)

    def observe(self, payload: dict[str, Any]) -> _CoreSnapshot:
        self.payloads.append(payload)
        return _CoreSnapshot(extra=None)

    def to_dict(self) -> dict[str, Any]:
        return {"tick_count": self.tick_count}

    def from_dict(self, data: dict[str, Any]) -> None:
        self.tick_count = int(data["tick_count"])

    def _learning_state(self) -> str:
        return "stable"


class _LegacyCore(_ProjectingCore):
    """Fake old core with no persistence API."""

    to_dict = None
    from_dict = None


def _load_engine_module(monkeypatch, core_cls):
    pkg_name = f"kontinuum_lite_projection_{core_cls.__name__}"
    for name in list(sys.modules):
        if name == pkg_name or name.startswith(f"{pkg_name}."):
            del sys.modules[name]

    fake_core = types.ModuleType("kontinuum_core")
    fake_core.KontinuumEngine = core_cls
    fake_core.Scheduler = object
    monkeypatch.setitem(sys.modules, "kontinuum_core", fake_core)

    pkg = types.ModuleType(pkg_name)
    pkg.__path__ = [str(_ROOT)]
    monkeypatch.setitem(sys.modules, pkg_name, pkg)

    for name in ("const", "engine"):
        spec = importlib.util.spec_from_file_location(
            f"{pkg_name}.{name}", _ROOT / f"{name}.py"
        )
        mod = importlib.util.module_from_spec(spec)
        monkeypatch.setitem(sys.modules, f"{pkg_name}.{name}", mod)
        spec.loader.exec_module(mod)

    return sys.modules[f"{pkg_name}.engine"]


def test_observe_normalizes_none_payload_and_projects_missing_extra(monkeypatch):
    engine_mod = _load_engine_module(monkeypatch, _ProjectingCore)
    engine = engine_mod.LiteEngine(scheduler="scheduler", storage_path="/tmp/brain")

    snap = engine.observe(None)

    assert engine.core.scheduler == "scheduler"
    assert engine.core.storage_path == "/tmp/brain"
    assert engine.core.payloads == [{}]
    assert snap.surprise == 0.25
    assert snap.anomaly is True
    assert snap.learning_state == "learning"
    assert snap.tick_count == 7
    assert snap.token == "kitchen.motion.on"
    assert snap.extra == {}
    assert snap.anomaly_threshold is None
    assert snap.expected_next_room is None


def test_restore_uses_core_learning_state_immediately(monkeypatch):
    engine_mod = _load_engine_module(monkeypatch, _ProjectingCore)
    engine = engine_mod.LiteEngine()

    assert engine.restore({"tick_count": 42}) is True

    assert engine.snapshot.tick_count == 42
    assert engine.snapshot.learning_state == "stable"
    assert engine.tick_count == 42
    assert engine.total_events == 3


def test_legacy_core_disables_persistence_without_writing_state(monkeypatch):
    engine_mod = _load_engine_module(monkeypatch, _LegacyCore)
    engine = engine_mod.LiteEngine()

    assert engine.supports_persistence is False
    assert engine.state_dict() is None
    assert engine.restore({"tick_count": 42}) is False
    assert engine.snapshot.tick_count == 0
    assert engine.snapshot.learning_state == "cold_start"
