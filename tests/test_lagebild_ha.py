"""Stufe 3 in a real (empty) test Home Assistant (require HA + kontinuum-core >= 0.7).

Skips itself with a reason on a core < 0.7: the manifest allows 0.7 only with
the deliberate bump to ``>=0.7.0,<0.8``. Until then a pipeline with the CI
variable ``KERN_VORSCHAU`` runs these tests against the coming core.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

pytest.importorskip("homeassistant")
pytest.importorskip("kontinuum_core")

from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.helpers import entity_registry as er  # noqa: E402
from homeassistant.helpers.dispatcher import async_dispatcher_send  # noqa: E402
from homeassistant.util import dt as dt_util  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.kontinuum_lite.const import (  # noqa: E402
    CONF_HOME_ONLY,
    CONF_OPERATION_MODE,
    CONF_PRESET,
    CONF_TRACK_MODE,
    DEFAULT_OPERATION_MODE,
    DEFAULT_PRESET,
    DOMAIN,
    SIGNAL_LAGEBILD,
    TRACK_STANDARD,
)


def _stufe3() -> bool:
    try:
        import kontinuum_core.association_cortex  # noqa: F401
    except ImportError:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _stufe3(), reason="kontinuum-core < 0.7: no Lagebild, no Börse"
)


async def _setup(hass: HomeAssistant, home_only: bool = False) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        title="Test",
        version=2,
        data={
            CONF_PRESET: DEFAULT_PRESET,
            CONF_OPERATION_MODE: DEFAULT_OPERATION_MODE,
            CONF_TRACK_MODE: TRACK_STANDARD,
            CONF_HOME_ONLY: home_only,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_situation_sensor_and_local_time(hass: HomeAssistant) -> None:
    """The seed puts the person into the Lagebild — in local time: the core
    reads hour and weekday off the timestamp, HA's own timestamps are UTC."""
    hass.states.async_set("person.a", "home", {"friendly_name": "A"})
    await hass.async_block_till_done()
    entry = await _setup(hass)
    engine = hass.data[DOMAIN][entry.entry_id]

    assert hass.states.get("sensor.test_situation") is not None
    cortex = engine.association_cortex
    assert cortex.zustand.get("person.a") == "home"
    assert "person.a" in cortex.ziele
    assert cortex.versatz == dt_util.now().utcoffset().total_seconds()


async def test_home_only_still_feeds_the_lagebild(hass: HomeAssistant) -> None:
    """Nobody home: learning pauses, the Lagebild does not — the empty house
    is exactly what it learns "away" from."""
    hass.states.async_set("person.a", "not_home")
    hass.states.async_set("person.b", "not_home")
    await hass.async_block_till_done()
    entry = await _setup(hass, home_only=True)
    engine = hass.data[DOMAIN][entry.entry_id]
    ticks = engine.tick_count

    hass.states.async_set("person.b", "unavailable")
    await hass.async_block_till_done()

    assert engine.tick_count == ticks
    assert engine.association_cortex.zustand.get("person.b") == "weg"


async def test_own_sensors_are_never_learned(hass: HomeAssistant) -> None:
    """After a reload our sensors are in the registry and the state machine;
    neither the thalamus nor the Lagebild may take them in."""
    hass.states.async_set("person.a", "home")
    await hass.async_block_till_done()
    entry = await _setup(hass)
    hass.states.async_set("person.a", "not_home")
    await hass.async_block_till_done()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()

    engine = hass.data[DOMAIN][entry.entry_id]
    registry = er.async_get(hass)
    own = {e.entity_id for e in registry.entities.values() if e.platform == DOMAIN}
    assert own
    assert not own & set(engine.association_cortex.zustand)
    assert all(engine.entity_semantic(entity_id) is None for entity_id in own)


async def test_presence_sensor_appears_once_learned(hass: HomeAssistant) -> None:
    hass.states.async_set("person.a", "home", {"friendly_name": "A"})
    await hass.async_block_till_done()
    entry = await _setup(hass)
    engine = hass.data[DOMAIN][entry.entry_id]
    assert hass.states.get("sensor.test_presence_a") is None  # nothing learned yet

    # Two days ahead, straight into the Lagebild: presence is counted a day
    # behind, so only then is there something to show.
    start = dt_util.now() + timedelta(minutes=5)
    for hour in range(48):
        t = start + timedelta(hours=hour)
        home = t.hour >= 18 or t.hour < 8
        engine.feed_lagebild("person.a", "home" if home else "not_home", t)
    async_dispatcher_send(
        hass, SIGNAL_LAGEBILD, engine.lagebild(now=start + timedelta(hours=48))
    )
    await hass.async_block_till_done()

    state = hass.states.get("sensor.test_presence_a")
    assert state is not None
    assert 0 <= float(state.state) <= 100
    assert state.attributes["person"] == "person.a"
    assert "evidence" in state.attributes
    assert hass.states.get("sensor.test_situation").attributes["presence"]


async def test_learning_state_shows_the_boerse(hass: HomeAssistant) -> None:
    await _setup(hass)
    attributes = hass.states.get("sensor.test_learning_state").attributes
    assert "hit_rate" in attributes
    assert "next_event" in attributes
