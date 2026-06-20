"""Diagnostics support for KONTINUUM Lite.

Dumps the integration's runtime state for bug reports — most importantly
whether the installed core actually supports brain persistence (otherwise it
silently no-ops) and how much the engine has learned so far.
"""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_ENTITIES, DOMAIN
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

    data: dict[str, Any] = {
        "core_version": core_version,
        "observed_entities": list(entry.options.get(CONF_ENTITIES, [])),
    }

    if engine is not None:
        snap = engine.snapshot
        data["engine"] = {
            "supports_persistence": engine.supports_persistence,
            "tick_count": engine.tick_count,
            "total_events": engine.total_events,
            "learning_state": snap.learning_state,
            "surprise": snap.surprise,
            "anomaly": snap.anomaly,
        }
    else:
        data["engine"] = None

    return data
