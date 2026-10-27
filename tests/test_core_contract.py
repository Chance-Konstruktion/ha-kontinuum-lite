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
from custom_components.kontinuum_lite.engine import LiteEngine  # noqa: E402


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



def test_lite_reconstructed_decision_preserves_core_token_id():
    engine = LiteEngine()
    decision = engine._decision_obj(
        {
            "token": "kitchen.light.on",
            "token_id": 17,
            "entity_id": "light.kitchen",
            "stage": "CONFIRM",
            "confidence": 0.8,
        }
    )

    assert decision.token_id == 17


def test_lite_reconstructed_decision_tolerates_older_core_snapshots():
    engine = LiteEngine()
    decision = engine._decision_obj(
        {
            "token": "kitchen.light.on",
            "entity_id": "light.kitchen",
            "stage": "CONFIRM",
        }
    )

    assert decision.token_id == 0


def test_lite_reconstructed_decision_defaults_invalid_token_id_safely():
    engine = LiteEngine()
    for invalid in ("not-an-integer", float("inf"), float("nan")):
        decision = engine._decision_obj(
            {
                "token": "kitchen.light.on",
                "token_id": invalid,
                "entity_id": "light.kitchen",
                "stage": "CONFIRM",
            }
        )
        assert decision.token_id == 0



def test_lite_service_call_normalizes_legacy_media_domain(monkeypatch):
    engine = LiteEngine()
    monkeypatch.setattr(
        engine.prefrontal,
        "get_service_call",
        lambda _decision: {
            "domain": "media",
            "service": "media_play",
            "entity_id": "media_player.tv",
            "data": {"entity_id": "media_player.tv"},
        },
    )

    call = engine.service_call_for(
        {
            "token": "living_room.media.playing",
            "entity_id": "media_player.tv",
        }
    )

    assert call["domain"] == "media_player"
    assert call["service"] == "media_play"


def test_lite_service_call_fills_missing_legacy_climate_mapping(monkeypatch):
    engine = LiteEngine()
    monkeypatch.setattr(engine.prefrontal, "get_service_call", lambda _decision: None)

    call = engine.service_call_for(
        {
            "token": "living_room.climate.heat",
            "entity_id": "climate.living_room",
        }
    )

    assert call == {
        "domain": "climate",
        "service": "set_hvac_mode",
        "entity_id": "climate.living_room",
        "data": {"entity_id": "climate.living_room", "hvac_mode": "heat"},
    }


def test_lite_service_call_normalizes_legacy_climate_alias(monkeypatch):
    engine = LiteEngine()
    monkeypatch.setattr(
        engine.prefrontal,
        "get_service_call",
        lambda _decision: {
            "domain": "climate",
            "service": "set_hvac_mode",
            "entity_id": "climate.living_room",
            "data": {"entity_id": "climate.living_room", "hvac_mode": "cooling"},
        },
    )
    decision = engine._decision_obj(
        {
            "token": "living_room.climate.cooling",
            "entity_id": "climate.living_room",
            "stage": "CONFIRM",
        }
    )

    call = engine.get_service_call_obj(decision)

    assert call["data"]["hvac_mode"] == "cool"
