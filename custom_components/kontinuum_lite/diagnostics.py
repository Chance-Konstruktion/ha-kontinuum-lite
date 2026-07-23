"""Diagnostics support for KONTINUUM Lite.

Dumps the integration's runtime state for bug reports — most importantly
whether the installed core actually supports brain persistence (otherwise it
silently no-ops) and how much the engine has learned so far.
"""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    CONF_HOME_ONLY,
    CONF_OPERATION_MODE,
    CONF_PRESET,
    CONF_TRACK_MODE,
    DEFAULT_OPERATION_MODE,
    DEFAULT_PRESET,
    DEFAULT_TRACK_MODE,
    DOMAIN,
)
from .engine import LiteEngine


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    engine: LiteEngine | None = hass.data.get(DOMAIN, {}).get(entry.entry_id)

    try:
        import kontinuum_core

        core_version = getattr(kontinuum_core, "__version__", "unknown")
    except Exception:  # noqa: BLE001
        core_version = "unavailable"

    merged = {**entry.data, **entry.options}
    data: dict[str, Any] = {
        "core_version": core_version,
        "config": {
            "preset": merged.get(CONF_PRESET, DEFAULT_PRESET),
            "operation_mode": merged.get(CONF_OPERATION_MODE, DEFAULT_OPERATION_MODE),
            "track_mode": merged.get(CONF_TRACK_MODE, DEFAULT_TRACK_MODE),
            "home_only_mode": merged.get(CONF_HOME_ONLY, False),
        },
    }

    if engine is not None:
        snap = engine.snapshot
        data["engine"] = {
            "supports_persistence": engine.supports_persistence,
            "tick_count": engine.tick_count,
            "total_events": engine.total_events,
            "tracked_entities": engine.tracked_count,
            "operation_mode": engine.operation_mode,
            "track_mode": engine.track_mode,
            "pending_confirms": len(engine.pending_confirms()),
            "learning_state": snap.learning_state,
            "surprise": snap.surprise,
            "anomaly": snap.anomaly,
            "anomaly_threshold": snap.anomaly_threshold,
            "token": snap.token,
            "expected_next_room": snap.expected_next_room,
        }
    else:
        data["engine"] = None

    return data
