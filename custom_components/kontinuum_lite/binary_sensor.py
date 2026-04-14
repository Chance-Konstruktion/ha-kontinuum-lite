"""Binary sensor platform for KONTINUUM Lite."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, ENTITY_ANOMALY, SIGNAL_UPDATE
from .engine import LiteEngine


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up KONTINUUM Lite binary sensors."""
    engine: LiteEngine = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([AnomalyBinarySensor(engine, entry)])


class AnomalyBinarySensor(BinarySensorEntity):
    """On when the current snapshot flags an anomaly."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_translation_key = ENTITY_ANOMALY
    _attr_name = "Anomaly"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, engine: LiteEngine, entry: ConfigEntry) -> None:
        self._engine = engine
        self._attr_unique_id = f"{entry.entry_id}_{ENTITY_ANOMALY}"
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

    @property
    def is_on(self) -> bool:
        return bool(self._engine.snapshot.anomaly)
