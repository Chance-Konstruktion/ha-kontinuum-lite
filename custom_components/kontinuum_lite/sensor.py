"""Sensor platform for KONTINUUM Lite."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    DOMAIN,
    ENTITY_LEARNING_STATE,
    ENTITY_PRESENCE,
    ENTITY_SITUATION,
    ENTITY_SURPRISE,
    SIGNAL_LAGEBILD,
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
    sensors: list[SensorEntity] = [
        SurpriseSensor(engine, entry),
        LearningStateSensor(engine, entry),
    ]
    # Stufe 3 (kontinuum-core >= 0.7): the Lagebild. Presence sensors per
    # person appear once the Lagebild has learned that person.
    if engine.supports_lagebild:
        sensors.append(SituationSensor(engine, entry, async_add_entities))
    async_add_entities(sensors)


class _LiteEntityBase(SensorEntity):
    """Shared bits for Lite sensors."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _signal = SIGNAL_UPDATE

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
            async_dispatcher_connect(self.hass, self._signal, self._handle_update)
        )

    @callback
    def _handle_update(self, *_data: object) -> None:
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

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        snap = self._engine.snapshot
        return {
            # The adaptive threshold the anomaly decision is compared against —
            # exposing it makes "why did/didn't it flag" answerable.
            "anomaly_threshold": snap.anomaly_threshold,
            "token": snap.token,
        }


class LearningStateSensor(_LiteEntityBase):
    """Categorical learning state (cold_start / learning / stable)."""

    _attr_translation_key = ENTITY_LEARNING_STATE
    _attr_name = "Learning state"
    # Change with every event — not for the recorder.
    _unrecorded_attributes = frozenset(
        {"next_event", "next_event_probability", "hit_rate"}
    )

    def __init__(self, engine: LiteEngine, entry: ConfigEntry) -> None:
        super().__init__(engine, entry, ENTITY_LEARNING_STATE)

    @property
    def native_value(self) -> str:
        return self._engine.snapshot.learning_state

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        snap = self._engine.snapshot
        boerse = self._engine.boerse or {}
        return {
            "tick": snap.tick_count,
            # Events the hippocampus actually learned from (post-filter); the
            # cold_start → learning → stable transitions key off this.
            "total_events": self._engine.total_events,
            # The engine's first guess for the next event — and, from
            # kontinuum-core 0.7 on, how often the Börse's first guess was
            # right so far (None on older cores).
            "next_event": snap.next_event,
            "next_event_probability": snap.next_event_probability,
            "hit_rate": boerse.get("hit_rate"),
        }


class SituationSensor(_LiteEntityBase):
    """The Lagebild (kontinuum-core >= 0.7): how many persons it holds home.

    Inferred from every device state together — the car there or gone (its
    tyre-pressure sensors go ``unavailable`` when it drives off), TV, PC,
    lights, and for how long — stacked with the time-of-day habit. The
    attributes carry presence per target with the strongest evidence and the
    pair table's strongest associations ("if A, then B"). Creates one
    presence sensor per person the Lagebild has learned.
    """

    _attr_translation_key = ENTITY_SITUATION
    _attr_name = "Situation"
    _attr_icon = "mdi:home-search"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _signal = SIGNAL_LAGEBILD
    _unrecorded_attributes = frozenset({"presence", "associations", "learning"})

    def __init__(
        self,
        engine: LiteEngine,
        entry: ConfigEntry,
        add_entities: AddEntitiesCallback,
    ) -> None:
        super().__init__(engine, entry, ENTITY_SITUATION)
        self._entry = entry
        self._add_entities = add_entities
        self._persons: set[str] = set()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._add_presence_sensors()

    @callback
    def _handle_update(self, *_data: object) -> None:
        self._add_presence_sensors()
        self.async_write_ha_state()

    @callback
    def _add_presence_sensors(self) -> None:
        new: list[PresenceSensor] = []
        for target in self._engine.lagebild_data.get("presence") or {}:
            if not target.startswith("person.") or target in self._persons:
                continue
            self._persons.add(target)
            state = self.hass.states.get(target)
            name = (
                state.attributes.get("friendly_name") if state is not None else None
            ) or target.split(".", 1)[1]
            new.append(PresenceSensor(self._engine, self._entry, target, name))
        if new:
            self._add_entities(new)

    @property
    def native_value(self) -> int:
        presence = self._engine.lagebild_data.get("presence") or {}
        return sum(
            1
            for target, reading in presence.items()
            if target.startswith("person.") and reading.get("home", 0.0) >= 0.5
        )

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        data = self._engine.lagebild_data
        return {
            "presence": data.get("presence") or {},
            "associations": data.get("associations") or [],
            "learning": data.get("learning") or {},
        }


class PresenceSensor(_LiteEntityBase):
    """How likely this person is home — inferred from the Lagebild.

    The person's own trackers are NOT evidence: this is a second opinion.
    When the phone goes quiet (``unknown``) it is the only one; when the phone
    lies in the office, it disagrees with it.
    """

    _attr_icon = "mdi:home-account"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _signal = SIGNAL_LAGEBILD
    _unrecorded_attributes = frozenset({"evidence"})

    def __init__(
        self, engine: LiteEngine, entry: ConfigEntry, person: str, name: str
    ) -> None:
        super().__init__(engine, entry, f"{ENTITY_PRESENCE}_{person.split('.', 1)[1]}")
        self._person = person
        self._attr_name = f"Presence {name}"

    @property
    def _reading(self) -> dict[str, object]:
        presence = self._engine.lagebild_data.get("presence") or {}
        return presence.get(self._person) or {}

    @property
    def native_value(self) -> int | None:
        home = self._reading.get("home")
        return None if home is None else round(100 * float(home))

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        reading = self._reading
        return {
            "person": self._person,
            "most_likely": reading.get("most_likely"),
            "reported": reading.get("reported"),
            "evidence": reading.get("evidence") or [],
            "time_of_day": reading.get("time_of_day"),
            "ticks": reading.get("ticks", 0),
            # How often the inference matched what the person's trackers
            # reported: checked every 5 min before learning, with knowledge
            # at least a day old — an honest score (None until checked).
            "checked": reading.get("checked", 0),
            "hit_rate": reading.get("hit_rate"),
        }
