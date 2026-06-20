"""Setup / teardown tests (require Home Assistant + kontinuum-core)."""
from __future__ import annotations

import pytest

pytest.importorskip("homeassistant")
pytest.importorskip("kontinuum_core")

from homeassistant.core import HomeAssistant  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.kontinuum_lite.const import (  # noqa: E402
    CONF_ENTITIES,
    CONF_NAME,
    DOMAIN,
    SERVICE_EVALUATE,
)


async def _setup(hass: HomeAssistant, entities: list[str] | None = None):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        data={CONF_NAME: "Test"},
        options={CONF_ENTITIES: entities or []},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_setup_creates_entities_and_service(hass: HomeAssistant) -> None:
    await _setup(hass)
    assert hass.states.get("sensor.test_surprise") is not None
    assert hass.states.get("sensor.test_learning_state") is not None
    assert hass.states.get("binary_sensor.test_anomaly") is not None
    assert hass.services.has_service(DOMAIN, SERVICE_EVALUATE)


async def test_unload_removes_service(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not hass.services.has_service(DOMAIN, SERVICE_EVALUATE)
    assert DOMAIN not in hass.data


async def test_observed_entity_feeds_engine(hass: HomeAssistant) -> None:
    """A state change on an observed entity advances the engine tick count."""
    hass.states.async_set("binary_sensor.motion_kitchen", "off")
    await hass.async_block_till_done()

    entry = await _setup(hass, entities=["binary_sensor.motion_kitchen"])
    engine = hass.data[DOMAIN][entry.entry_id]
    before = engine.tick_count

    hass.states.async_set("binary_sensor.motion_kitchen", "on")
    await hass.async_block_till_done()

    assert engine.tick_count > before
