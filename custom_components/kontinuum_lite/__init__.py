"""KONTINUUM Lite integration (Phase 0 skeleton)."""
from __future__ import annotations

import gzip
import json
import logging
import os
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    BRAIN_FILE,
    DOMAIN,
    EVENT_ANOMALY,
    SAVE_INTERVAL_SECONDS,
    SERVICE_EVALUATE,
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
    # rebuilt from zero on every reload. No-op on kontinuum-core < 0.1.2.
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
                "persistence (needs >= 0.1.2); only metaplasticity is kept"
            )
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Brain load failed; starting cold")

    # Snapshot the brain periodically so an unclean shutdown (power loss,
    # OS kill) loses at most SAVE_INTERVAL_SECONDS of learning. The unload
    # handler does a final save. cancel_all() (on unload) stops this too.
    scheduler.schedule_interval(
        lambda: _save_brain(engine, brain_path), SAVE_INTERVAL_SECONDS
    )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    async def _handle_evaluate(call: ServiceCall) -> None:
        """Run one engine tick and push updates to entities."""
        payload_raw: Any = call.data.get("payload")
        payload: dict[str, Any] = payload_raw if isinstance(payload_raw, dict) else {}
        previously_anomalous = engine.snapshot.anomaly
        snap = engine.evaluate(payload)

        # Notify entities.
        async_dispatcher_send(hass, SIGNAL_UPDATE)

        # Fire event on the anomaly edge. The threshold itself lives in
        # the core engine (adaptive, baseline + 2σ) — the integration
        # only reacts to the core's decision.
        if snap.anomaly and not previously_anomalous:
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
                brain_path = _brain_path(hass.config.path(STORAGE_DIR))
                await hass.async_add_executor_job(_save_brain, engine, brain_path)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Brain save failed during unload")
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
