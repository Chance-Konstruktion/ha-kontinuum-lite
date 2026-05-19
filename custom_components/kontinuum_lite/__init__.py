"""KONTINUUM Lite integration (Phase 0 skeleton)."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    ANOMALY_THRESHOLD,
    DOMAIN,
    EVENT_ANOMALY,
    SERVICE_EVALUATE,
    SIGNAL_UPDATE,
    STORAGE_DIR,
)
from .engine import LiteEngine
from .ha_scheduler import HAScheduler

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


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

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _handle_evaluate(call: ServiceCall) -> None:
        """Run one engine tick and push updates to entities."""
        payload_raw: Any = call.data.get("payload")
        payload: dict[str, Any] = payload_raw if isinstance(payload_raw, dict) else {}
        previous_surprise = engine.snapshot.surprise
        snap = engine.evaluate(payload)

        # Notify entities.
        async_dispatcher_send(hass, SIGNAL_UPDATE)

        # Fire event when anomaly threshold is crossed.
        crossed_threshold = (
            previous_surprise < ANOMALY_THRESHOLD <= snap.surprise
        )
        if crossed_threshold or snap.anomaly:
            hass.bus.async_fire(
                EVENT_ANOMALY,
                {
                    "surprise": snap.surprise,
                    "learning_state": snap.learning_state,
                    "tick": snap.tick_count,
                    "payload": payload,
                },
            )

    # Register service once (first entry wins; unregister on final unload).
    if not hass.services.has_service(DOMAIN, SERVICE_EVALUATE):
        hass.services.async_register(DOMAIN, SERVICE_EVALUATE, _handle_evaluate)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        bucket = hass.data.get(DOMAIN, {})
        engine: LiteEngine | None = bucket.pop(entry.entry_id, None)
        scheduler: HAScheduler | None = bucket.get("_schedulers", {}).pop(
            entry.entry_id, None
        )
        if engine is not None:
            try:
                await hass.async_add_executor_job(engine.core.metaplasticity.save)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("MetaPlasticity save failed during unload")
        if scheduler is not None:
            scheduler.cancel_all()
        # Drop service + container if no entries remain (ignore bookkeeping keys).
        remaining = {k for k in bucket if not k.startswith("_")}
        if not remaining:
            hass.services.async_remove(DOMAIN, SERVICE_EVALUATE)
            hass.data.pop(DOMAIN, None)
    return unload_ok
