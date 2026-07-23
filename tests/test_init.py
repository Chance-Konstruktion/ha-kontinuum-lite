"""Setup / teardown tests (require Home Assistant + kontinuum-core)."""
from __future__ import annotations

import os
import shutil

import pytest

pytest.importorskip("homeassistant")
pytest.importorskip("kontinuum_core")

from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.helpers import issue_registry as ir  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.kontinuum_lite.const import (  # noqa: E402
    BRAIN_FILE,
    CONF_HOME_ONLY,
    CONF_OPERATION_MODE,
    CONF_PRESET,
    CONF_TRACK_MODE,
    DEFAULT_OPERATION_MODE,
    DEFAULT_PRESET,
    DOMAIN,
    SERVICE_CONFIRM_ACTION,
    SERVICE_EVALUATE,
    SERVICE_REJECT_ACTION,
    SERVICE_RESET_BRAIN,
    SERVICE_SAVE_BRAIN,
    SERVICE_SET_MODE,
    STORAGE_DIR,
    TRACK_LABELED,
    TRACK_STANDARD,
)


def _brain_file(hass: HomeAssistant) -> str:
    return os.path.join(hass.config.path(STORAGE_DIR), BRAIN_FILE)


@pytest.fixture(autouse=True)
def _isolate_storage(hass: HomeAssistant):
    """Wipe the persistent storage dir around each test.

    pytest-homeassistant-custom-component shares one on-disk ``testing_config``
    directory across the whole session, so a brain saved by one test would leak
    into the next. Clear it before and after each test for true isolation.
    """
    path = hass.config.path(STORAGE_DIR)
    shutil.rmtree(path, ignore_errors=True)
    yield
    shutil.rmtree(path, ignore_errors=True)


async def _setup(
    hass: HomeAssistant,
    *,
    track_mode: str = TRACK_STANDARD,
    operation_mode: str = DEFAULT_OPERATION_MODE,
    home_only: bool = False,
):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        title="Test",
        version=2,
        data={
            CONF_PRESET: DEFAULT_PRESET,
            CONF_OPERATION_MODE: operation_mode,
            CONF_TRACK_MODE: track_mode,
            CONF_HOME_ONLY: home_only,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_setup_creates_entities_and_services(hass: HomeAssistant) -> None:
    await _setup(hass)
    assert hass.states.get("sensor.test_surprise") is not None
    assert hass.states.get("sensor.test_learning_state") is not None
    assert hass.states.get("binary_sensor.test_anomaly") is not None
    for service in (
        SERVICE_EVALUATE,
        SERVICE_SAVE_BRAIN,
        SERVICE_RESET_BRAIN,
        SERVICE_SET_MODE,
        SERVICE_CONFIRM_ACTION,
        SERVICE_REJECT_ACTION,
    ):
        assert hass.services.has_service(DOMAIN, service)


async def test_unload_removes_services(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    for service in (
        SERVICE_EVALUATE,
        SERVICE_SAVE_BRAIN,
        SERVICE_RESET_BRAIN,
        SERVICE_SET_MODE,
        SERVICE_CONFIRM_ACTION,
        SERVICE_REJECT_ACTION,
    ):
        assert not hass.services.has_service(DOMAIN, service)
    assert DOMAIN not in hass.data


async def test_save_brain_service_writes_file(hass: HomeAssistant) -> None:
    await _setup(hass)
    assert not os.path.exists(_brain_file(hass))
    await hass.services.async_call(DOMAIN, SERVICE_SAVE_BRAIN, {}, blocking=True)
    assert os.path.exists(_brain_file(hass))


async def test_reset_brain_service_clears_learning(hass: HomeAssistant) -> None:
    hass.states.async_set("binary_sensor.motion_kitchen", "off")
    await hass.async_block_till_done()
    entry = await _setup(hass)

    # Accumulate a little learning, then snapshot it to disk.
    hass.states.async_set("binary_sensor.motion_kitchen", "on")
    await hass.async_block_till_done()
    await hass.services.async_call(DOMAIN, SERVICE_SAVE_BRAIN, {}, blocking=True)
    assert os.path.exists(_brain_file(hass))
    original_engine = hass.data[DOMAIN][entry.entry_id]

    await hass.services.async_call(DOMAIN, SERVICE_RESET_BRAIN, {}, blocking=True)
    await hass.async_block_till_done()

    # The snapshot is deleted and the entry reloaded a fresh, cold engine.
    # (It may immediately re-observe the entity's current state, so the proof
    # of a reset is the erased file + a new engine instance, not a zero count.)
    assert not os.path.exists(_brain_file(hass))
    assert hass.data[DOMAIN][entry.entry_id] is not original_engine


async def test_observed_entity_feeds_engine(hass: HomeAssistant) -> None:
    """A state change on an observed entity advances the engine tick count."""
    hass.states.async_set("binary_sensor.motion_kitchen", "off")
    await hass.async_block_till_done()

    entry = await _setup(hass)
    engine = hass.data[DOMAIN][entry.entry_id]
    before = engine.tick_count

    hass.states.async_set("binary_sensor.motion_kitchen", "on")
    await hass.async_block_till_done()

    assert engine.tick_count > before


async def test_no_tracked_entities_raises_repair_issue(hass: HomeAssistant) -> None:
    """Labeled tracking with no labelled entity tracks nothing → repair issue."""
    entry = await _setup(hass, track_mode=TRACK_LABELED)
    registry = ir.async_get(hass)
    assert (
        registry.async_get_issue(DOMAIN, f"no_entities_{entry.entry_id}") is not None
    )


async def test_standard_tracking_clears_repair_issue(hass: HomeAssistant) -> None:
    """Standard tracking discovers entities → no repair issue."""
    hass.states.async_set("binary_sensor.motion_kitchen", "off")
    await hass.async_block_till_done()
    entry = await _setup(hass, track_mode=TRACK_STANDARD)
    registry = ir.async_get(hass)
    assert registry.async_get_issue(DOMAIN, f"no_entities_{entry.entry_id}") is None


async def test_entities_expose_observability_attributes(hass: HomeAssistant) -> None:
    hass.states.async_set("binary_sensor.motion_kitchen", "off")
    await hass.async_block_till_done()
    await _setup(hass)
    hass.states.async_set("binary_sensor.motion_kitchen", "on")
    await hass.async_block_till_done()

    anomaly = hass.states.get("binary_sensor.test_anomaly")
    assert "threshold" in anomaly.attributes
    assert "surprise" in anomaly.attributes

    surprise = hass.states.get("sensor.test_surprise")
    assert "anomaly_threshold" in surprise.attributes
    assert "token" in surprise.attributes

    learning = hass.states.get("sensor.test_learning_state")
    assert "total_events" in learning.attributes


async def test_set_mode_service_changes_operation_mode(hass: HomeAssistant) -> None:
    entry = await _setup(hass, operation_mode=DEFAULT_OPERATION_MODE)
    engine = hass.data[DOMAIN][entry.entry_id]
    assert engine.operation_mode == DEFAULT_OPERATION_MODE

    await hass.services.async_call(
        DOMAIN, SERVICE_SET_MODE, {"mode": "confirm"}, blocking=True
    )
    await hass.async_block_till_done()
    assert engine.operation_mode == "confirm"
