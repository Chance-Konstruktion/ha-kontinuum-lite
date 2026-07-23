"""KONTINUUM Lite integration.

Super-Lite: the same learning + acting brain as the Pro integration
(``ha-kontinuum``) — presets, shadow/confirm/active operation modes and
standard/labeled/auto entity tracking — but without the "ballast": no
dashboard, no Cortex/LLM agents. Everything neuro-inspired lives in
``kontinuum-core``; this module is only the Home Assistant glue.
"""
from __future__ import annotations

import gzip
import json
import logging
import os
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STOP,
    EVENT_STATE_CHANGED,
    Platform,
)
from homeassistant.core import Event, HomeAssistant, ServiceCall, callback
from homeassistant.helpers import (
    area_registry as ar,
    device_registry as dr,
    entity_registry as er,
    issue_registry as ir,
)
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    ACTION_CONFIRM_PREFIX,
    ACTION_REJECT_PREFIX,
    BRAIN_FILE,
    CONF_HOME_ONLY,
    CONF_OPERATION_MODE,
    CONF_PRESET,
    CONF_TRACK_MODE,
    CONSOLIDATION_INTERVAL_SECONDS,
    DEFAULT_OPERATION_MODE,
    DEFAULT_PRESET,
    DEFAULT_TRACK_MODE,
    DOMAIN,
    EVENT_ACTION_EXECUTED,
    EVENT_ANOMALY,
    EVENT_CONFIRM_REJECTED,
    MODE_CONFIRM,
    NOTIFY_TAG_PREFIX,
    PRESETS,
    SAVE_INTERVAL_SECONDS,
    SERVICE_CONFIRM_ACTION,
    SERVICE_EVALUATE,
    SERVICE_REJECT_ACTION,
    SERVICE_RESET_BRAIN,
    SERVICE_SAVE_BRAIN,
    SERVICE_SET_MODE,
    SIGNAL_UPDATE,
    STORAGE_DIR,
    VALID_MODES,
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
    """Erase all persisted learning so a reload comes back cold."""
    _delete_file(brain_path)
    mp = getattr(engine.core, "metaplasticity", None)
    mp_path = getattr(mp, "_path", None)
    if mp_path:
        _delete_file(mp_path)


# ── Config accessors ───────────────────────────────────────────────────


def _config(entry: ConfigEntry) -> dict[str, Any]:
    """Effective config: options override entry data."""
    merged = dict(entry.data)
    merged.update(entry.options)
    return merged


def _no_entities_issue_id(entry: ConfigEntry) -> str:
    return f"no_entities_{entry.entry_id}"


@callback
def _async_update_no_entities_issue(
    hass: HomeAssistant, entry: ConfigEntry, tracked: int
) -> None:
    """Raise a repair when the thalamus ends up tracking nothing.

    With ``track_mode=standard`` this should essentially never happen, but a
    ``labeled`` setup with no labelled entities would silently sit at cold
    start forever — so surface it as a dismissible repair that clears itself.
    """
    issue_id = _no_entities_issue_id(entry)
    if tracked > 0:
        ir.async_delete_issue(hass, DOMAIN, issue_id)
        return
    ir.async_create_issue(
        hass,
        DOMAIN,
        issue_id,
        is_fixable=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="no_entities",
    )


# ── Entity discovery ───────────────────────────────────────────────────


@callback
def _label_names(hass: HomeAssistant) -> dict[str, str]:
    """label_id → label name (empty when the label registry is unavailable)."""
    try:
        from homeassistant.helpers import label_registry as lr

        registry = lr.async_get(hass)
        return {label.label_id: label.name for label in registry.async_list_labels()}
    except (ImportError, AttributeError):  # pragma: no cover - old HA cores
        return {}


@callback
def _discover_and_register(hass: HomeAssistant, engine: LiteEngine) -> int:
    """Register every HA entity with the core thalamus (with area + labels).

    The thalamus then decides — based on ``track_mode`` and the
    ``kontinuum`` / ``ignore_kontinuum`` labels — which entities it actually
    keeps. This mirrors Pro: the integration hands over everything, the core
    filters. Returns the number of entities the thalamus ended up tracking.
    """
    ent_reg = er.async_get(hass)
    dev_reg = dr.async_get(hass)
    area_reg = ar.async_get(hass)
    label_names = _label_names(hass)

    seen: set[str] = set()

    for entry in ent_reg.entities.values():
        entity_id = entry.entity_id
        seen.add(entity_id)
        meta: dict[str, Any] = {"domain": entity_id.split(".")[0]}

        area_id = entry.area_id
        if area_id is None and entry.device_id:
            device = dev_reg.async_get(entry.device_id)
            if device is not None:
                area_id = device.area_id
        if area_id:
            area = area_reg.async_get_area(area_id)
            if area is not None:
                meta["ha_area"] = area.name

        meta["device_class"] = entry.device_class or entry.original_device_class or ""
        meta["unit"] = entry.unit_of_measurement or ""
        meta["friendly_name"] = entry.name or entry.original_name or ""

        labels = [
            label_names[lid]
            for lid in getattr(entry, "labels", set()) or ()
            if lid in label_names
        ]
        if labels:
            meta["labels"] = labels

        engine.register_entity(entity_id, **meta)

    # Registry-less entities (e.g. template/legacy) — resolve from live state.
    for state in hass.states.async_all():
        if state.entity_id in seen:
            continue
        attrs = state.attributes
        engine.register_entity(
            state.entity_id,
            domain=state.entity_id.split(".")[0],
            device_class=attrs.get("device_class") or "",
            unit=attrs.get("unit_of_measurement") or "",
            friendly_name=attrs.get("friendly_name") or "",
        )

    return engine.tracked_count


# ── Home-only helper ───────────────────────────────────────────────────


@callback
def _anyone_home(hass: HomeAssistant) -> bool:
    """True when at least one person is home (or no person entities exist)."""
    persons = hass.states.async_all("person")
    if not persons:
        return True
    return any(state.state == "home" for state in persons)


# ── Observation + action pipeline ──────────────────────────────────────


@callback
def _ingest(
    hass: HomeAssistant, engine: LiteEngine, observation: dict[str, Any]
) -> None:
    """Feed one observation to the engine, surface anomaly, act on decisions."""
    previously_anomalous = engine.snapshot.anomaly
    snap = engine.observe(observation)

    async_dispatcher_send(hass, SIGNAL_UPDATE)

    # Anomaly edge (adaptive threshold decided by the core).
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

    _handle_decision(hass, engine)


@callback
def _handle_decision(hass: HomeAssistant, engine: LiteEngine) -> None:
    """Execute or queue-for-confirmation the core's advisory decision.

    The *stage* is decided by the core from the operation mode: SHADOW keeps
    it at OBSERVE (nothing to do here), CONFIRM yields stage CONFIRM, ACTIVE
    (or an activated semantic) yields EXECUTE. We just carry it out.
    """
    decision = engine.last_decision
    if not decision:
        return
    stage = decision.get("stage")
    entity_id = decision.get("entity_id")
    token = decision.get("token", "")
    if not entity_id:
        return
    semantic = token.split(".")[1] if token.count(".") == 2 else ""

    if stage == "EXECUTE":
        call = engine.service_call_for(decision)
        if not call:
            return
        _async_call(hass, call["domain"], call["service"], call["data"])
        engine.mark_own_action(entity_id, token=token, semantic=semantic)
        hass.bus.async_fire(
            EVENT_ACTION_EXECUTED,
            {"entity_id": entity_id, "token": token, "confirmed": False},
        )
        _LOGGER.info("KONTINUUM Lite: executed %s → %s", token, entity_id)

    elif stage == "CONFIRM":
        confirm_id = engine.queue_confirm(
            decision,
            reasoning=f"conf={decision.get('confidence')}, util={decision.get('utility')}",
            context={"mode": MODE_CONFIRM},
        )
        if confirm_id:
            _send_confirm_notification(hass, decision, confirm_id)
            _LOGGER.info(
                "KONTINUUM Lite: awaiting confirm %s → %s (id=%s)",
                token,
                entity_id,
                confirm_id,
            )


@callback
def _async_call(
    hass: HomeAssistant, domain: str, service: str, data: dict[str, Any]
) -> None:
    """Fire-and-forget service call."""
    hass.async_create_task(hass.services.async_call(domain, service, data))


@callback
def _send_confirm_notification(
    hass: HomeAssistant, decision: dict[str, Any], confirm_id: str
) -> None:
    """Ask the user to confirm/reject via an actionable mobile notification.

    Falls back to a persistent notification that documents the two services,
    so confirmation works even without the companion app.
    """
    token = decision.get("token", "")
    entity_id = decision.get("entity_id", "")
    action_label = token.split(".")[2] if token.count(".") == 2 else token
    title = "KONTINUUM Lite – Aktion bestätigen?"
    message = (
        f"**{entity_id}** → {action_label}\n"
        f"Konfidenz: {decision.get('confidence')} · "
        f"Nutzen: {decision.get('utility')} · Risiko: {decision.get('risk')}"
    )

    # Actionable mobile notification (companion app renders the buttons).
    if hass.services.has_service("notify", "notify"):
        _async_call(
            hass,
            "notify",
            "notify",
            {
                "title": title,
                "message": message,
                "data": {
                    "tag": f"{NOTIFY_TAG_PREFIX}{confirm_id}",
                    "actions": [
                        {
                            "action": f"{ACTION_CONFIRM_PREFIX}{confirm_id}",
                            "title": "✅ Bestätigen",
                        },
                        {
                            "action": f"{ACTION_REJECT_PREFIX}{confirm_id}",
                            "title": "❌ Ablehnen",
                        },
                    ],
                },
            },
        )

    # Fallback / audit trail as a persistent notification.
    _async_call(
        hass,
        "persistent_notification",
        "create",
        {
            "title": title,
            "message": (
                f"{message}\n\n"
                f"Bestätigen: Service `kontinuum_lite.confirm_action` mit "
                f"`confirm_id: {confirm_id}`\n"
                f"Ablehnen: `kontinuum_lite.reject_action` mit "
                f"`confirm_id: {confirm_id}`"
            ),
            "notification_id": f"{NOTIFY_TAG_PREFIX}{confirm_id}",
        },
    )


@callback
def _execute_pending(hass: HomeAssistant, engine: LiteEngine, confirm_id: str) -> bool:
    """Run a previously queued confirmation. Returns True if it fired."""
    decision_obj = engine.take_pending(confirm_id)
    if decision_obj is None:
        return False
    call = engine.get_service_call_obj(decision_obj)
    if not call:
        return False
    _async_call(hass, call["domain"], call["service"], call["data"])
    token = getattr(decision_obj, "token", "")
    semantic = token.split(".")[1] if token.count(".") == 2 else ""
    engine.mark_own_action(call["entity_id"], token=token, semantic=semantic)
    hass.bus.async_fire(
        EVENT_ACTION_EXECUTED,
        {"entity_id": call["entity_id"], "token": token, "confirmed": True},
    )
    # Clear the persistent fallback notification.
    _async_call(
        hass,
        "persistent_notification",
        "dismiss",
        {"notification_id": f"{NOTIFY_TAG_PREFIX}{confirm_id}"},
    )
    return True


@callback
def _make_state_listener(hass: HomeAssistant, engine: LiteEngine, entry: ConfigEntry):
    """Global EVENT_STATE_CHANGED handler — the thalamus does the filtering."""

    @callback
    def _on_state_change(event: Event) -> None:
        entity_id = event.data.get("entity_id", "")
        new_state = event.data.get("new_state")
        if new_state is None:  # entity removed
            return
        old_state = event.data.get("old_state")

        # Never learn from our own entities — otherwise every observation
        # writes the surprise/anomaly sensors, whose state change would be
        # re-observed, looping forever. Our sensor entity_ids depend on the
        # entry title, so match on the registry platform, not a name prefix.
        own = er.async_get(hass).async_get(entity_id)
        if own is not None and own.platform == DOMAIN:
            return

        # Ignore no-op state repeats.
        if old_state is not None and old_state.state == new_state.state:
            return

        # Home-only: pause entirely while nobody is home (mirrors Pro).
        cfg = _config(entry)
        if cfg.get(CONF_HOME_ONLY, False) and not _anyone_home(hass):
            return

        # Suppress the echo of our own actions (~10 s window).
        if engine.is_own_action(entity_id):
            return

        # Quick manual undo of one of our actions → negative feedback.
        if engine.check_override(entity_id, new_state.state):
            _LOGGER.debug("KONTINUUM Lite: override on %s", entity_id)

        _ingest(
            hass,
            engine,
            {
                "entity_id": entity_id,
                "new_state": new_state.state,
                "old_state": old_state.state if old_state else None,
                "timestamp": new_state.last_updated,
            },
        )

    return _on_state_change


# ── Setup / teardown ───────────────────────────────────────────────────


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up KONTINUUM Lite from a config entry."""
    scheduler = HAScheduler(hass)
    storage_path = hass.config.path(STORAGE_DIR)
    engine = LiteEngine(scheduler=scheduler, storage_path=storage_path)
    bucket = hass.data.setdefault(DOMAIN, {})
    bucket[entry.entry_id] = engine
    bucket.setdefault("_schedulers", {})[entry.entry_id] = scheduler

    cfg = _config(entry)

    # Metaplasticity bootstrap (best effort).
    try:
        await hass.async_add_executor_job(engine.core.metaplasticity.load)
        engine.core.metaplasticity.start(interval_hours=24)
    except Exception:  # noqa: BLE001
        _LOGGER.exception("MetaPlasticity bootstrap failed; continuing without it")

    # Restore the learned brain so learning survives restarts.
    brain_path = _brain_path(storage_path)
    try:
        loaded = await hass.async_add_executor_job(_load_brain, engine, brain_path)
        if loaded:
            _LOGGER.info(
                "KONTINUUM Lite: restored brain (%d ticks)", engine.snapshot.tick_count
            )
        elif not engine.supports_persistence:
            _LOGGER.info(
                "KONTINUUM Lite: installed kontinuum-core has no brain "
                "persistence; only metaplasticity is kept"
            )
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Brain load failed; starting cold")

    # ── Apply preset + operation mode + track mode ──────────────────
    preset_key = cfg.get(CONF_PRESET, DEFAULT_PRESET)
    engine.apply_preset(PRESETS.get(preset_key, PRESETS[DEFAULT_PRESET]))
    engine.set_track_mode(cfg.get(CONF_TRACK_MODE, DEFAULT_TRACK_MODE))
    engine.set_operation_mode(cfg.get(CONF_OPERATION_MODE, DEFAULT_OPERATION_MODE))
    _LOGGER.info(
        "KONTINUUM Lite: preset=%s, mode=%s, track=%s, home_only=%s",
        preset_key,
        engine.operation_mode,
        engine.track_mode,
        cfg.get(CONF_HOME_ONLY, False),
    )

    # ── Discover entities (thalamus filters via track_mode + labels) ─
    tracked = _discover_and_register(hass, engine)
    _async_update_no_entities_issue(hass, entry, tracked)
    _LOGGER.debug("KONTINUUM Lite: thalamus tracking %d entities", tracked)

    # Seed from current state so learning starts now, not on the next change.
    for state in hass.states.async_all():
        if engine.entity_semantic(state.entity_id) is None:
            continue
        _ingest(
            hass,
            engine,
            {
                "entity_id": state.entity_id,
                "new_state": state.state,
                "old_state": None,
                "timestamp": state.last_updated,
            },
        )

    # ── Subscribe to all state changes (Pro-style global listener) ──
    entry.async_on_unload(
        hass.bus.async_listen(
            EVENT_STATE_CHANGED, _make_state_listener(hass, engine, entry)
        )
    )

    # ── Actionable-notification button handler ──────────────────────
    @callback
    def _on_mobile_action(event: Event) -> None:
        action = event.data.get("action", "")
        if action.startswith(ACTION_CONFIRM_PREFIX):
            _execute_pending(hass, engine, action[len(ACTION_CONFIRM_PREFIX):])
        elif action.startswith(ACTION_REJECT_PREFIX):
            confirm_id = action[len(ACTION_REJECT_PREFIX):]
            result = engine.reject_pending(confirm_id)
            _async_call(
                hass,
                "persistent_notification",
                "dismiss",
                {"notification_id": f"{NOTIFY_TAG_PREFIX}{confirm_id}"},
            )
            if result:
                hass.bus.async_fire(EVENT_CONFIRM_REJECTED, result)

    entry.async_on_unload(
        hass.bus.async_listen("mobile_app_notification_action", _on_mobile_action)
    )

    # ── Periodic brain snapshot (skip when nothing changed) ─────────
    save_marker = {"tick": -1}

    def _maybe_save_brain() -> None:
        tick = engine.tick_count
        if tick == save_marker["tick"]:
            return
        _save_brain(engine, brain_path)
        save_marker["tick"] = tick

    scheduler.schedule_interval(_maybe_save_brain, SAVE_INTERVAL_SECONDS)

    # ── Idle heartbeat for sleep consolidation ──────────────────────
    def _idle_consolidate() -> None:
        stats = engine.tick()
        if stats:
            _LOGGER.info("KONTINUUM Lite: idle sleep consolidation ran: %s", stats)

    scheduler.schedule_interval(_idle_consolidate, CONSOLIDATION_INTERVAL_SECONDS)

    # Reload when options change.
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    # Final save on HA shutdown.
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


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate a v1 entry (manual entity list) to the v2 preset/mode schema."""
    if entry.version >= 2:
        return True
    new_data = {
        CONF_PRESET: DEFAULT_PRESET,
        CONF_OPERATION_MODE: DEFAULT_OPERATION_MODE,
        CONF_TRACK_MODE: DEFAULT_TRACK_MODE,
        CONF_HOME_ONLY: False,
    }
    hass.config_entries.async_update_entry(
        entry, data=new_data, options={}, version=2
    )
    _LOGGER.info(
        "KONTINUUM Lite: migrated entry to v2 (preset/mode/track). The old "
        "manual entity list is superseded by track_mode='standard' (all "
        "entities, opt-out via the 'ignore_kontinuum' label)."
    )
    return True


@callback
def _resolve_engine(hass: HomeAssistant) -> LiteEngine | None:
    """Return the active engine (single-instance integration)."""
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
        engine = _resolve_engine(hass)
        if engine is None:
            return
        payload_raw: Any = call.data.get("payload")
        payload: dict[str, Any] = payload_raw if isinstance(payload_raw, dict) else {}
        _ingest(hass, engine, payload)

    async def _handle_save_brain(call: ServiceCall) -> None:
        engine = _resolve_engine(hass)
        if engine is None:
            return
        brain_path = _brain_path(hass.config.path(STORAGE_DIR))
        await hass.async_add_executor_job(_save_brain, engine, brain_path)
        _LOGGER.info("KONTINUUM Lite: brain saved on request")

    async def _handle_reset_brain(call: ServiceCall) -> None:
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

    async def _handle_set_mode(call: ServiceCall) -> None:
        engine = _resolve_engine(hass)
        if engine is None:
            return
        mode = str(call.data.get("mode", "")).strip().lower()
        if mode not in VALID_MODES:
            _LOGGER.warning(
                "KONTINUUM Lite: invalid mode '%s' (allowed: %s)",
                mode,
                ", ".join(sorted(VALID_MODES)),
            )
            return
        if engine.set_operation_mode(mode):
            async_dispatcher_send(hass, SIGNAL_UPDATE)
            _LOGGER.info("KONTINUUM Lite: operation mode → %s", mode)

    async def _handle_confirm_action(call: ServiceCall) -> None:
        engine = _resolve_engine(hass)
        if engine is None:
            return
        if call.data.get("confirm_all", False):
            for pending in list(engine.pending_confirms()):
                _execute_pending(hass, engine, pending.get("id", ""))
            return
        confirm_id = str(call.data.get("confirm_id", ""))
        if not _execute_pending(hass, engine, confirm_id):
            _LOGGER.warning(
                "KONTINUUM Lite: confirm_id '%s' not found or expired", confirm_id
            )

    async def _handle_reject_action(call: ServiceCall) -> None:
        engine = _resolve_engine(hass)
        if engine is None:
            return
        confirm_id = str(call.data.get("confirm_id", ""))
        result = engine.reject_pending(confirm_id)
        _async_call(
            hass,
            "persistent_notification",
            "dismiss",
            {"notification_id": f"{NOTIFY_TAG_PREFIX}{confirm_id}"},
        )
        if result:
            hass.bus.async_fire(EVENT_CONFIRM_REJECTED, result)
        else:
            _LOGGER.warning("KONTINUUM Lite: confirm_id '%s' not found", confirm_id)

    hass.services.async_register(DOMAIN, SERVICE_EVALUATE, _handle_evaluate)
    hass.services.async_register(DOMAIN, SERVICE_SAVE_BRAIN, _handle_save_brain)
    hass.services.async_register(DOMAIN, SERVICE_RESET_BRAIN, _handle_reset_brain)
    hass.services.async_register(DOMAIN, SERVICE_SET_MODE, _handle_set_mode)
    hass.services.async_register(DOMAIN, SERVICE_CONFIRM_ACTION, _handle_confirm_action)
    hass.services.async_register(DOMAIN, SERVICE_REJECT_ACTION, _handle_reject_action)


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry so changed settings take effect."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        ir.async_delete_issue(hass, DOMAIN, _no_entities_issue_id(entry))
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
        remaining = {k for k in bucket if not k.startswith("_")}
        if not remaining:
            for service in (
                SERVICE_EVALUATE,
                SERVICE_SAVE_BRAIN,
                SERVICE_RESET_BRAIN,
                SERVICE_SET_MODE,
                SERVICE_CONFIRM_ACTION,
                SERVICE_REJECT_ACTION,
            ):
                hass.services.async_remove(DOMAIN, service)
            hass.data.pop(DOMAIN, None)
    return unload_ok
