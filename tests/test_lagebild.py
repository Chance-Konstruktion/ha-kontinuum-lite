"""Stufe 3 (kontinuum-core >= 0.7): Lagebild and Börse through ``LiteEngine``.

HA-free like ``test_engine.py``: the engine module is loaded without the
package ``__init__``. With a core < 0.7 the Lagebild tests skip themselves
with a reason (``-rs``); the first tests pin that everything stays silent then,
and the snapshot tests run on every core.
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
EngineSnapshot = engine_mod.EngineSnapshot

STUFE3 = LiteEngine().supports_lagebild
stufe3 = pytest.mark.skipif(
    not STUFE3, reason="kontinuum-core < 0.7: no Lagebild, no Börse"
)

LOCAL = timezone(timedelta(hours=2))
START = datetime(2026, 10, 5, 0, 0, tzinfo=LOCAL)  # a Monday


def _engine_with_house(trackers: set[str] | None = None) -> LiteEngine:
    engine = LiteEngine()
    engine.set_person_trackers(trackers or set())
    engine.register_entity("light.living", ha_area="Living", domain="light")
    engine.register_entity(
        "media_player.tv", ha_area="Living", domain="media_player"
    )
    engine.register_entity(
        "device_tracker.pc", ha_area="Office", domain="device_tracker"
    )
    return engine


def _four_days(engine: LiteEngine) -> None:
    """Home in the evening and at night (light, PC), away during the day."""
    for day in range(4):
        for hour in range(24):
            t = START + timedelta(days=day, hours=hour)
            home = hour >= 18 or hour < 8
            engine.feed_lagebild("person.a", "home" if home else "not_home", t)
            engine.feed_lagebild("light.living", "on" if home else "off", t)
            engine.feed_lagebild(
                "device_tracker.pc", "home" if home else "not_home", t
            )
            engine.lagebild(now=t + timedelta(minutes=30), associations=False)


# ── Every core ──────────────────────────────────────────────────────────


def test_without_stufe3_everything_stays_silent():
    engine = LiteEngine()
    if engine.supports_lagebild:
        assert engine.association_cortex is not None
        assert engine.boerse is not None
        return
    engine.feed_lagebild("light.x", "on", START)  # no error
    assert engine.lagebild(now=START) == {}
    assert engine.lagebild_data == {}
    assert engine.boerse is None


def test_skipped_observation_keeps_the_reading_but_not_the_decision():
    """With standard tracking most changes are filtered. They used to flicker
    surprise to 0 and the anomaly to off; now the last real reading stays.
    The decision does NOT stay — carried over, it would run again."""
    engine = LiteEngine()
    engine._snapshot = EngineSnapshot(
        surprise=0.4,
        anomaly=True,
        token="living.light.on",
        tick_count=3,
        extra={"anomaly_threshold": 0.3, "decision": {"token": "x", "stage": "EXECUTE"}},
        next_event="living.light.off",
        next_event_probability=0.7,
    )
    snap = engine.observe({"entity_id": "sensor.never_registered", "new_state": "1"})
    assert snap.tick_count == engine.tick_count
    assert snap.surprise == 0.4
    assert snap.anomaly is True
    assert snap.token == "living.light.on"
    assert snap.anomaly_threshold == 0.3
    assert snap.next_event == "living.light.off"
    assert engine.last_decision is None


def test_next_event_comes_from_the_prediction_list():
    engine = LiteEngine()
    engine.register_entity(
        "binary_sensor.m", ha_area="Kitchen", domain="binary_sensor",
        device_class="motion",
    )
    base = datetime.now(timezone.utc)
    for i in range(60):
        engine.observe(
            {
                "entity_id": "binary_sensor.m",
                "new_state": "on" if i % 2 else "off",
                "old_state": "off" if i % 2 else "on",
                "timestamp": base + timedelta(seconds=i * 60),
            }
        )
    snap = engine.snapshot
    # Decoded (room.semantic.state), not the core's integer token id.
    assert isinstance(snap.next_event, str) and snap.next_event.count(".") == 2
    assert 0.0 <= snap.next_event_probability <= 1.0


# ── kontinuum-core >= 0.7 ──────────────────────────────────────────────


@stufe3
def test_targets_are_persons_and_their_own_trackers():
    """The PC's tracker (a router creates one per device) is evidence, not a
    target; the phone that belongs to the person is a target."""
    engine = _engine_with_house({"device_tracker.a_phone"})
    for entity_id, state in (
        ("person.a", "home"),
        ("device_tracker.a_phone", "home"),
        ("device_tracker.pc", "home"),
    ):
        engine.feed_lagebild(entity_id, state, START)
    cortex = engine.association_cortex
    assert cortex.ziele == ["person.a", "device_tracker.a_phone"]
    assert "device_tracker.pc" in cortex.im_blick


@stufe3
def test_unavailable_becomes_gone():
    engine = _engine_with_house()
    engine.feed_lagebild("light.living", "on", START)
    engine.feed_lagebild("light.living", "unavailable", START + timedelta(minutes=1))
    assert engine.association_cortex.zustand["light.living"] == "weg"


@stufe3
def test_local_time_reaches_the_lagebild():
    """The core reads hour and weekday off the timestamp — the offset of a
    local timestamp is what makes "evening" the evening."""
    engine = _engine_with_house()
    engine.feed_lagebild("light.living", "on", START)
    assert engine.association_cortex.versatz == 7200.0


@stufe3
def test_lagebild_reports_presence_with_evidence():
    engine = _engine_with_house()
    _four_days(engine)
    data = engine.lagebild(now=START + timedelta(days=4, hours=20))
    reading = data["presence"]["person.a"]
    assert 0.0 <= reading["home"] <= 1.0
    assert reading["most_likely"] in ("home", "not_home")
    assert reading["reported"] == "home"
    assert reading["evidence"] and all(len(e) == 2 for e in reading["evidence"])
    assert reading["ticks"] > 0
    assert reading["checked"] >= 0
    assert reading["hit_rate"] is None or 0.0 <= reading["hit_rate"] <= 1.0
    assert set(data["learning"]) == {
        "entities_in_view", "targets", "ticks", "pair_features",
    }
    assert data["learning"]["targets"] == ["person.a"]
    for pair in data["associations"]:
        assert set(pair) == {"if", "then", "p", "lift", "ticks"}
    assert engine.lagebild_data is data
    assert engine.lagebild_age < 60


@stufe3
def test_event_path_keeps_the_last_associations():
    """The pair table is read whole (quadratic): the event path skips it and
    keeps the heartbeat's associations."""
    engine = _engine_with_house()
    _four_days(engine)
    full = engine.lagebild(now=START + timedelta(days=4), associations=True)
    quick = engine.lagebild(now=START + timedelta(days=4, minutes=1), associations=False)
    assert quick["associations"] == full["associations"]


@stufe3
def test_restore_keeps_the_presence_targets():
    """The trackers are set before the restore — the core keeps only the
    targets its predicate accepts."""
    engine = _engine_with_house({"device_tracker.a_phone"})
    engine.feed_lagebild("person.a", "home", START)
    engine.feed_lagebild("device_tracker.a_phone", "home", START)
    data = engine.state_dict()

    restored = LiteEngine()
    restored.set_person_trackers({"device_tracker.a_phone"})
    assert restored.restore(data) is True
    assert restored.association_cortex.ziele == ["person.a", "device_tracker.a_phone"]


@stufe3
def test_boerse_reports_its_hit_rate():
    engine = LiteEngine()
    engine.register_entity(
        "binary_sensor.m", ha_area="Kitchen", domain="binary_sensor",
        device_class="motion",
    )
    for i in range(40):
        engine.observe(
            {
                "entity_id": "binary_sensor.m",
                "new_state": "on" if i % 2 else "off",
                "old_state": "off" if i % 2 else "on",
                "timestamp": START + timedelta(minutes=i),
            }
        )
    boerse = engine.boerse
    assert 0.0 <= boerse["hit_rate"] <= 1.0
    assert boerse["events"] > 0
    assert isinstance(boerse["weights"], dict) and boerse["weights"]


@stufe3
def test_associations_age_tracks_only_full_readings():
    """The heartbeat reads the pair table hourly; presence-only readings
    must not reset that clock."""
    engine = _engine_with_house()
    assert engine.associations_age == float("inf")
    engine.lagebild(now=START, associations=False)
    assert engine.associations_age == float("inf")
    engine.lagebild(now=START, associations=True)
    assert engine.associations_age < 60
