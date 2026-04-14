"""Sensor platform for KONTINUUM Lite."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    ENTITY_LEARNING_STATE,
    ENTITY_SURPRISE,
    SIGNAL_UPDATE,
)
from .engine import LiteEngine


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up KONTINUUM Lite sensors from a config entry."""
    engine: LiteEngine = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            SurpriseSensor(engine, entry),
            LearningStateSensor(engine, entry),
        ]
    )


class _LiteEntityBase(SensorEntity):
    """Shared bits for Lite sensors."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, engine: LiteEngine, entry: ConfigEntry, suffix: str) -> None:
        self._engine = engine
        self._attr_unique_id = f"{entry.entry_id}_{suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="Chance-Konstruktion",
            model="KONTINUUM Lite",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_UPDATE, self._handle_update)
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()


class SurpriseSensor(_LiteEntityBase):
    """Numeric surprise signal (0..1)."""

    _attr_translation_key = ENTITY_SURPRISE
    _attr_name = "Surprise"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = None
    _attr_suggested_display_precision = 3

    def __init__(self, engine: LiteEngine, entry: ConfigEntry) -> None:
        super().__init__(engine, entry, ENTITY_SURPRISE)

    @property
    def native_value(self) -> float:
        return float(self._engine.snapshot.surprise)


class LearningStateSensor(_LiteEntityBase):
    """Categorical learning state (cold_start / learning / stable)."""

    _attr_translation_key = ENTITY_LEARNING_STATE
    _attr_name = "Learning state"

    def __init__(self, engine: LiteEngine, entry: ConfigEntry) -> None:
        super().__init__(engine, entry, ENTITY_LEARNING_STATE)

    @property
    def native_value(self) -> str:
        return self._engine.snapshot.learning_state

    @property
    def extra_state_attributes(self) -> dict[str, int]:
        return {"tick": self._engine.snapshot.tick_count}
