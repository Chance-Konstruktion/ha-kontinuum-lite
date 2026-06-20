"""KONTINUUM Lite integration."""
from __future__ import annotations

import gzip
import json
import logging
import os
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    BRAIN_FILE,
    CONF_ENTITIES,
    DOMAIN,
    EVENT_ANOMALY,
    SAVE_INTERVAL_SECONDS,
    SERVICE_EVALUATE,
    SERVICE_RESET_BRAIN,
    SERVICE_SAVE_BRAIN,
    SIGNAL_UPDATE,
    STORAGE_DIR,
)
from .engine import LiteEngine
from .ha_scheduler import HAScheduler

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


def _brain_path(storage_path: str) -> str:
    return os.path.join(storage_path, BRAIN_FILE)


def _save_brain(engine: LiteEngine, brain_path: str) -> None:
    """Persist the full learned engine state (blocking; run in executor).

    Atomic via a temp file + os.replace so a crash mid-write can never
    corrupt the brain. A no-op when the core is too old to serialize.
    """
    data = engine.state_dict()
    if data is None:
        return
    os.makedirs(os.path.dirname(brain_path), exist_ok=True)
    tmp = f"{brain_path}.tmp"
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        json.dump(data, fh, separators=(",", ":"))
    os.replace(tmp, brain_path)


def _load_brain(engine: LiteEngine, brain_path: str) -> bool:
    """Restore a persisted brain (blocking; run in executor).

    Returns True if a brain was loaded. Missing/corrupt files are tolerated
    (cold start) so a bad file never blocks startup.
    """
    if not os.path.exists(brain_path):
        return False
    with gzip.open(brain_path, "rt", encoding="utf-8") as fh:
        data = json.load(fh)
    return engine.restore(data)


def _delete_file(path: str) -> None:
    """Remove a persisted file if it exists (blocking; run in executor)."""
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def _reset_files(engine: LiteEngine, brain_path: str) -> None:
    """Erase all persisted learning so a reload comes back cold.

    Deletes the brain snapshot and the core's metaplasticity file (its path is
    read from the core itself, so a future rename there doesn't silently leave
    stale state behind).
    """
    _delete_file(brain_path)
    mp = getattr(engine.core, "metaplasticity", None)
    mp_path = getattr(mp, "_path", None)
    if mp_path:
        _delete_file(mp_path)


def _selected_entities(entry: ConfigEntry) -> list[str]:
    """Entities the user picked to feed the engine (options override data)."""
    if CONF_ENTITIES in entry.options:
        return list(entry.options.get(CONF_ENTITIES) or [])
    return list(entry.data.get(CONF_ENTITIES, []) or [])


@callback
def _register_entities(
    hass: HomeAssistant, engine: LiteEngine, entity_ids: list[str]
) -> None:
    """Tell the core about each entity with its area + metadata.

    The core's thalamus drops any observation for an entity it doesn't know
    or can't place in a room, so this registration is what makes auto-learning
    actually work. Metadata is resolved from the entity/device/area registries
    and falls back to live state attributes for registry-less entities.
    """
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    area_reg = ar.async_get(hass)

    for entity_id in entity_ids:
        meta: dict[str, Any] = {"domain": entity_id.split(".")[0]}
        area_id: str | None = None

        entry = ent_reg.async_get(entity_id)
        if entry is not None:
            area_id = entry.area_id
            if area_id is None and entry.device_id:
                device = dev_reg.async_get(entry.device_id)
                if device is not None:
                    area_id = device.area_id
            meta["device_class"] = (
                entry.device_class or entry.original_device_class or ""
            )
            meta["unit"] = entry.unit_of_measurement or ""
            meta["friendly_name"] = entry.name or entry.original_name or ""

        state = hass.states.get(entity_id)
        if state is not None:
            attrs = state.attributes
            meta.setdefault("device_class", attrs.get("device_class") or "")
            if not meta.get("unit"):
                meta["unit"] = attrs.get("unit_of_measurement") or ""
            if not meta.get("friendly_name"):
                meta["friendly_name"] = attrs.get("friendly_name") or ""

        if area_id:
            area = area_reg.async_get_area(area_id)
            if area is not None:
                meta["ha_area"] = area.name

        if not meta.get("ha_area"):
            _LOGGER.debug(
                "KONTINUUM Lite: %s has no resolvable area; the core may skip "
                "it unless it can infer a room",
                entity_id,
            )
        engine.register_entity(entity_id, **meta)


@callback
def _ingest(
    hass: HomeAssistant, engine: LiteEngine, observation: dict[str, Any]
) -> None:
    """Feed one observation to the engine and surface the result.

    Shared by the state-change listener and the ``evaluate`` service so both
    paths fire the anomaly event on the same rising edge.
    """
    previously_anomalous = engine.snapshot.anomaly
    snap = engine.observe(observation)

    async_dispatcher_send(hass, SIGNAL_UPDATE)

    # Fire on the anomaly edge only. The threshold itself is the core's
    # adaptive decision (baseline + 2σ of recent surprise), not a constant.
    if snap.anomaly and not previously_anomalous:
        hass.bus.async_fire(
            EVENT_ANOMALY,
            {
                "surprise": snap.surprise,
                "learning_state": snap.learning_state,
                "tick": snap.tick_count,
                "entity_id": observation.get("entity_id"),
            },
        )


@callback
def _make_state_listener(hass: HomeAssistant, engine: LiteEngine):
    """Build the state-change callback that turns HA events into observations."""

    @callback
    def _on_state_change(event: Event) -> None:
        new_state = event.data.get("new_state")
        if new_state is None:  # entity removed
            return
        old_state = event.data.get("old_state")
        _ingest(
            hass,
            engine,
            {
                "entity_id": event.data["entity_id"],
                "new_state": new_state.state,
                "old_state": old_state.state if old_state else None,
                "timestamp": new_state.last_updated,
            },
        )

    return _on_state_change


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up KONTINUUM Lite from a config entry."""
    scheduler = HAScheduler(hass)
    storage_path = hass.config.path(STORAGE_DIR)
    engine = LiteEngine(scheduler=scheduler, storage_path=storage_path)
    bucket = hass.data.setdefault(DOMAIN, {})
    bucket[entry.entry_id] = engine
    bucket.setdefault("_schedulers", {})[entry.entry_id] = scheduler

    # Best-effort: load persisted metaplasticity state and start its
    # 24 h adaptation loop. Failures are non-fatal — the engine still
    # works without it.
    try:
        await hass.async_add_executor_job(engine.core.metaplasticity.load)
        engine.core.metaplasticity.start(interval_hours=24)
    except Exception:  # noqa: BLE001
        _LOGGER.exception("MetaPlasticity bootstrap failed; continuing without it")

    # Restore the full learned brain so learning survives restarts. Without
    # this the hippocampus/predictive/cerebellum/basal-ganglia state was
    # rebuilt from zero on every reload. No-op on kontinuum-core without
    # to_dict/from_dict.
    brain_path = _brain_path(storage_path)
    try:
        loaded = await hass.async_add_executor_job(_load_brain, engine, brain_path)
        if loaded:
            _LOGGER.info(
                "KONTINUUM Lite: restored brain (%d ticks)",
                engine.snapshot.tick_count,
            )
        elif not engine.supports_persistence:
            _LOGGER.info(
                "KONTINUUM Lite: installed kontinuum-core has no brain "
                "persistence; only metaplasticity is kept"
            )
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Brain load failed; starting cold")

    # Auto-ingestion: register the chosen entities and subscribe to their
    # state changes so the engine learns on its own. Without this the engine
    # only ever sees manual `evaluate` calls and stays at cold_start forever.
    entities = _selected_entities(entry)
    if entities:
        _register_entities(hass, engine, entities)
        # Seed from current state so learning starts now, not on the next change.
        for entity_id in entities:
            state = hass.states.get(entity_id)
            if state is not None:
                _ingest(
                    hass,
                    engine,
                    {
                        "entity_id": entity_id,
                        "new_state": state.state,
                        "old_state": None,
                        "timestamp": state.last_updated,
                    },
                )
        entry.async_on_unload(
            async_track_state_change_event(
                hass, entities, _make_state_listener(hass, engine)
            )
        )
        _LOGGER.debug("KONTINUUM Lite: observing %d entities", len(entities))

    # Snapshot the brain periodically so an unclean shutdown (power loss,
    # OS kill) loses at most SAVE_INTERVAL_SECONDS of learning. Skip the
    # write when no new ticks happened since the last save — headless
    # instances often idle, and HA frequently runs on flash/SD where
    # needless writes cost endurance. The unload handler does a final save.
    save_marker = {"tick": -1}

    def _maybe_save_brain() -> None:
        tick = engine.tick_count
        if tick == save_marker["tick"]:
            return
        _save_brain(engine, brain_path)
        save_marker["tick"] = tick

    scheduler.schedule_interval(_maybe_save_brain, SAVE_INTERVAL_SECONDS)

    # Reload when the user changes the observed-entity list via options.
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    # Belt-and-suspenders durability: flush on HA shutdown too. The unload
    # path normally runs on stop and saves, but this guarantees a final
    # snapshot even if it doesn't. Removed automatically on unload.
    async def _on_ha_stop(_event: Event) -> None:
        await hass.async_add_executor_job(_save_brain, engine, brain_path)
        try:
            await hass.async_add_executor_job(engine.core.metaplasticity.save)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("MetaPlasticity save on stop failed")

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _on_ha_stop)
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _async_register_services(hass)
    return True


@callback
def _resolve_engine(hass: HomeAssistant) -> LiteEngine | None:
    """Return the active engine (single-instance integration).

    Looked up fresh from ``hass.data`` so service handlers never hold a stale
    reference to an engine discarded by a reload.
    """
    for key, value in hass.data.get(DOMAIN, {}).items():
        if not key.startswith("_") and isinstance(value, LiteEngine):
            return value
    return None


@callback
def _async_register_services(hass: HomeAssistant) -> None:
    """Register the domain services once (idempotent across entries)."""
    if hass.services.has_service(DOMAIN, SERVICE_EVALUATE):
        return

    async def _handle_evaluate(call: ServiceCall) -> None:
        """Run one engine tick from a manual payload and push updates."""
        engine = _resolve_engine(hass)
        if engine is None:
            return
        payload_raw: Any = call.data.get("payload")
        payload: dict[str, Any] = payload_raw if isinstance(payload_raw, dict) else {}
        _ingest(hass, engine, payload)

    async def _handle_save_brain(call: ServiceCall) -> None:
        """Force an immediate brain snapshot to disk."""
        engine = _resolve_engine(hass)
        if engine is None:
            return
        brain_path = _brain_path(hass.config.path(STORAGE_DIR))
        await hass.async_add_executor_job(_save_brain, engine, brain_path)
        _LOGGER.info("KONTINUUM Lite: brain saved on request")

    async def _handle_reset_brain(call: ServiceCall) -> None:
        """Erase all learning and reload cold. Cannot be undone."""
        data = hass.data.setdefault(DOMAIN, {})
        entry_ids = [
            key
            for key, value in data.items()
            if not key.startswith("_") and isinstance(value, LiteEngine)
        ]
        reset = data.setdefault("_reset", set())
        for entry_id in entry_ids:
            reset.add(entry_id)
            await hass.config_entries.async_reload(entry_id)

    hass.services.async_register(DOMAIN, SERVICE_EVALUATE, _handle_evaluate)
    hass.services.async_register(DOMAIN, SERVICE_SAVE_BRAIN, _handle_save_brain)
    hass.services.async_register(DOMAIN, SERVICE_RESET_BRAIN, _handle_reset_brain)


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry so a changed entity selection takes effect."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        bucket = hass.data.get(DOMAIN, {})
        reset_set: set[str] = bucket.get("_reset", set())
        resetting = entry.entry_id in reset_set
        reset_set.discard(entry.entry_id)
        engine: LiteEngine | None = bucket.pop(entry.entry_id, None)
        scheduler: HAScheduler | None = bucket.get("_schedulers", {}).pop(
            entry.entry_id, None
        )
        brain_path = _brain_path(hass.config.path(STORAGE_DIR))
        if engine is not None and resetting:
            # reset_brain requested: discard learning instead of persisting it,
            # so the imminent reload comes back cold.
            try:
                await hass.async_add_executor_job(_reset_files, engine, brain_path)
                _LOGGER.info("KONTINUUM Lite: brain reset — learning cleared")
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Brain reset failed")
        elif engine is not None:
            try:
                await hass.async_add_executor_job(_save_brain, engine, brain_path)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Brain save failed during unload")
            try:
                await hass.async_add_executor_job(engine.core.metaplasticity.save)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("MetaPlasticity save failed during unload")
        if scheduler is not None:
            scheduler.cancel_all()
        # Drop services + container if no entries remain (ignore bookkeeping keys).
        remaining = {k for k in bucket if not k.startswith("_")}
        if not remaining:
            for service in (
                SERVICE_EVALUATE,
                SERVICE_SAVE_BRAIN,
                SERVICE_RESET_BRAIN,
            ):
                hass.services.async_remove(DOMAIN, service)
            hass.data.pop(DOMAIN, None)
    return unload_ok
