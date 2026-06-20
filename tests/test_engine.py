"""Tests for ``LiteEngine`` — the HA-side projection over ``kontinuum-core``.

Loaded without importing the package ``__init__`` (which pulls in Home
Assistant), so these run in a plain Python environment with just
``kontinuum-core`` installed.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import types
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("kontinuum_core")

_PKG = "kontinuum_lite"
_ROOT = (
    pathlib.Path(__file__).resolve().parents[1]
    / "custom_components"
    / "kontinuum_lite"
)


def _load_engine_module():
    """Import ``kontinuum_lite.engine`` without running the package __init__."""
    if f"{_PKG}.engine" in sys.modules:
        return sys.modules[f"{_PKG}.engine"]
    pkg = types.ModuleType(_PKG)
    pkg.__path__ = [str(_ROOT)]
    sys.modules[_PKG] = pkg
    for name in ("const", "engine"):
        spec = importlib.util.spec_from_file_location(
            f"{_PKG}.{name}", _ROOT / f"{name}.py"
        )
        mod = importlib.util.module_from_spec(spec)
        sys.modules[f"{_PKG}.{name}"] = mod
        spec.loader.exec_module(mod)
    return sys.modules[f"{_PKG}.engine"]


engine_mod = _load_engine_module()
LiteEngine = engine_mod.LiteEngine


def _feed_alternating(engine: LiteEngine, n: int) -> None:
    engine.register_entity(
        "binary_sensor.m", ha_area="Kitchen", domain="binary_sensor",
        device_class="motion",
    )
    base = datetime.now(timezone.utc)
    for i in range(n):
        engine.observe(
            {
                "entity_id": "binary_sensor.m",
                "new_state": "on" if i % 2 else "off",
                "old_state": "off" if i % 2 else "on",
                "timestamp": base + timedelta(seconds=i * 60),
            }
        )


def test_observe_projects_snapshot_fields():
    engine = LiteEngine()
    snap = engine.observe({})
    assert isinstance(snap.surprise, float)
    assert isinstance(snap.anomaly, bool)
    assert snap.tick_count == 1
    # A fresh engine has learned nothing.
    assert snap.learning_state == "cold_start"


def test_supports_persistence_on_modern_core():
    assert LiteEngine().supports_persistence is True


def test_state_dict_restore_roundtrip():
    engine = LiteEngine()
    _feed_alternating(engine, 5)
    data = engine.state_dict()
    assert data is not None

    restored = LiteEngine()
    assert restored.restore(data) is True
    assert restored.tick_count == engine.tick_count


def test_restore_reflects_learning_state_not_cold_start():
    """Regression guard: restoring a trained brain must not read cold_start.

    The old code copied the (default) snapshot's learning_state at load time,
    so a brain with hundreds of events showed ``cold_start`` until the next
    tick. The restore now derives the state from the core's stats.
    """
    engine = LiteEngine()
    _feed_alternating(engine, 140)
    assert engine.snapshot.learning_state == "learning"

    restored = LiteEngine()
    restored.restore(engine.state_dict())
    assert restored.snapshot.learning_state == "learning"
    assert restored.snapshot.tick_count == engine.tick_count


def test_restore_rejects_garbage():
    engine = LiteEngine()
    assert engine.restore({}) is False
    assert engine.restore("not a dict") is False  # type: ignore[arg-type]


def test_snapshot_exposes_threshold_and_token():
    """After real learning the snapshot surfaces the adaptive threshold + token."""
    engine = LiteEngine()
    _feed_alternating(engine, 60)
    snap = engine.snapshot
    # The token reflects the last processed observation (room.semantic.state).
    assert snap.token is None or isinstance(snap.token, str)
    # The adaptive anomaly threshold is exposed once the core reports it.
    threshold = snap.anomaly_threshold
    assert threshold is None or 0.0 <= threshold <= 1.0


def test_anomaly_threshold_handles_missing_extra():
    """A fresh/skipped snapshot has no threshold rather than crashing."""
    snap = engine_mod.EngineSnapshot()
    assert snap.anomaly_threshold is None
    assert snap.expected_next_room is None
