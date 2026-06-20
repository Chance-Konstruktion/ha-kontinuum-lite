"""Contract tests against the real ``kontinuum-core`` data flow.

These don't touch Home Assistant — they pin down *why* the integration must
register entities (with an area) before feeding observations. If the core ever
changes this contract, the auto-ingestion wiring in ``__init__.py`` breaks, so
we want a fast, HA-free test guarding it.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

kontinuum_core = pytest.importorskip("kontinuum_core")
from kontinuum_core import KontinuumEngine  # noqa: E402


def _observe(engine, entity_id, new_state, old_state=None):
    return engine.observe(
        {
            "entity_id": entity_id,
            "new_state": new_state,
            "old_state": old_state,
            "timestamp": datetime.now(timezone.utc),
        }
    )


def test_unregistered_entity_is_not_learned():
    """An entity the core was never told about is filtered out (no learning)."""
    engine = KontinuumEngine()
    snap = _observe(engine, "sensor.unknown", "5", "4")
    assert snap.extra.get("skipped") == "filtered"
    assert engine.hippocampus.total_events == 0


def test_registration_without_area_is_dropped():
    """Without a resolvable room the core refuses to track the entity."""
    engine = KontinuumEngine()
    engine.register_entity(
        "binary_sensor.no_area", domain="binary_sensor", device_class="motion"
    )
    assert "binary_sensor.no_area" not in engine.thalamus.entity_semantic


def test_registered_entity_with_area_learns():
    """The happy path the integration relies on: register w/ area, then learn."""
    engine = KontinuumEngine()
    engine.register_entity(
        "binary_sensor.motion_kitchen",
        ha_area="Kitchen",
        domain="binary_sensor",
        device_class="motion",
        friendly_name="Kitchen Motion",
    )
    assert engine.hippocampus.total_events == 0
    snap = _observe(engine, "binary_sensor.motion_kitchen", "on", "off")
    assert "skipped" not in snap.extra
    assert snap.token == "kitchen.motion.on"
    assert engine.hippocampus.total_events == 1


def test_persistence_roundtrip_preserves_learning():
    """to_dict/from_dict carry tick count + learned events across a restart."""
    engine = KontinuumEngine()
    engine.register_entity(
        "binary_sensor.motion_kitchen", ha_area="Kitchen", domain="binary_sensor"
    )
    _observe(engine, "binary_sensor.motion_kitchen", "on", "off")

    restored = KontinuumEngine()
    restored.from_dict(engine.to_dict())

    assert restored.tick_count == engine.tick_count
    assert restored.hippocampus.total_events == engine.hippocampus.total_events
