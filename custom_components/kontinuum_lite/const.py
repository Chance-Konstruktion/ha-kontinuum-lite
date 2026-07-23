"""Constants for KONTINUUM Lite."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "kontinuum_lite"

# Config-flow keys
CONF_NAME: Final = "name"
CONF_ENTITIES: Final = "entities"
CONF_PRESET: Final = "preset"
CONF_OPERATION_MODE: Final = "operation_mode"
CONF_TRACK_MODE: Final = "track_mode"
CONF_HOME_ONLY: Final = "home_only_mode"
DEFAULT_NAME: Final = "KONTINUUM Lite"

# ── Operation modes (mirror kontinuum_core.prefrontal_cortex) ──────────
# Governs whether the engine only *observes*, asks before acting, or acts
# on its own. The heavy lifting (the Decision) is computed inside the core;
# these modes only decide what this integration does with an actionable
# Decision.
MODE_SHADOW: Final = "shadow"    # only observe, never act
MODE_CONFIRM: Final = "confirm"  # ask via actionable notification before acting
MODE_ACTIVE: Final = "active"    # act autonomously
VALID_MODES: Final = frozenset({MODE_SHADOW, MODE_CONFIRM, MODE_ACTIVE})
DEFAULT_OPERATION_MODE: Final = MODE_SHADOW

# ── Track modes (mirror kontinuum_core.thalamus.track_mode) ────────────
# Which entities the substrate learns from. The core thalamus does the
# actual filtering; the integration just discovers entities and subscribes
# to state changes.
TRACK_STANDARD: Final = "standard"  # all entities, opt-out via 'ignore_kontinuum' label
TRACK_LABELED: Final = "labeled"    # opt-in: only entities with the 'kontinuum' label
TRACK_AUTO: Final = "auto"          # smart heuristic filter inside the core
VALID_TRACK_MODES: Final = frozenset({TRACK_STANDARD, TRACK_LABELED, TRACK_AUTO})
DEFAULT_TRACK_MODE: Final = TRACK_STANDARD

# ── Presets (learning temperament) ─────────────────────────────────────
# Tune how fast/eager the substrate learns and acts. Same shape as the Pro
# integration so behaviour is comparable; the LLM/cortex layer is absent.
PRESET_BOLD: Final = "mutig"
PRESET_BALANCED: Final = "ausgeglichen"
PRESET_CONSERVATIVE: Final = "konservativ"
DEFAULT_PRESET: Final = PRESET_BALANCED

PRESETS: Final[dict[str, dict]] = {
    PRESET_BOLD: {
        "cerebellum_min_obs": 3,
        "cerebellum_min_conf": 0.60,
        "hippocampus_decay": 0.993,
        "hippocampus_min_obs": 2,
    },
    PRESET_BALANCED: {
        "cerebellum_min_obs": 4,
        "cerebellum_min_conf": 0.65,
        "hippocampus_decay": 0.997,
        "hippocampus_min_obs": 2,
    },
    PRESET_CONSERVATIVE: {
        "cerebellum_min_obs": 7,
        "cerebellum_min_conf": 0.80,
        "hippocampus_decay": 0.998,
        "hippocampus_min_obs": 3,
    },
}

# Entity labels the thalamus understands for opt-in / opt-out tracking.
LABEL_INCLUDE: Final = "kontinuum"
LABEL_IGNORE: Final = "ignore_kontinuum"

# Services & events
SERVICE_EVALUATE: Final = "evaluate"
SERVICE_RESET_BRAIN: Final = "reset_brain"
SERVICE_SAVE_BRAIN: Final = "save_brain"
SERVICE_SET_MODE: Final = "set_mode"
SERVICE_CONFIRM_ACTION: Final = "confirm_action"
SERVICE_REJECT_ACTION: Final = "reject_action"
EVENT_ANOMALY: Final = "kontinuum_lite_anomaly"
EVENT_CONFIRM_REJECTED: Final = "kontinuum_lite_confirm_rejected"
EVENT_ACTION_EXECUTED: Final = "kontinuum_lite_action_executed"

# Actionable-notification wiring. When an action needs confirmation we send a
# mobile_app notification whose buttons fire a `mobile_app_notification_action`
# event carrying this action prefix + the confirm_id.
ACTION_CONFIRM_PREFIX: Final = "KONTINUUM_LITE_CONFIRM_"
ACTION_REJECT_PREFIX: Final = "KONTINUUM_LITE_REJECT_"
NOTIFY_TAG_PREFIX: Final = "kontinuum_lite_confirm_"

# Entity object-ids / unique-id suffixes
ENTITY_SURPRISE: Final = "surprise"
ENTITY_ANOMALY: Final = "anomaly"
ENTITY_LEARNING_STATE: Final = "learning_state"

# Learning-state literals
STATE_COLD_START: Final = "cold_start"
STATE_LEARNING: Final = "learning"
STATE_STABLE: Final = "stable"

# Deprecated: the anomaly threshold is now decided inside kontinuum-core
# (adaptive, baseline + 2σ of recent surprise). Kept only so existing
# imports don't break; no longer used by this integration.
ANOMALY_THRESHOLD: Final = 0.75

# Signal names for intra-integration dispatch
SIGNAL_UPDATE: Final = f"{DOMAIN}_update"

# Sub-directory under hass.config for persistent state
STORAGE_DIR: Final = "kontinuum_lite"

# Full engine-state persistence (hippocampus, predictive, cerebellum,
# basal ganglia, …). Requires kontinuum-core >= 0.1.2 (to_dict/from_dict);
# on older cores brain persistence is a graceful no-op and only the
# metaplasticity meta-state is kept.
BRAIN_FILE: Final = "brain.json.gz"
SAVE_INTERVAL_SECONDS: Final = 600  # snapshot the learned brain every 10 min
# Idle heartbeat: drive core's self-gating tick() so sleep consolidation can
# fire during genuine downtime (needs kontinuum-core >= 0.6.2). Cheap and a
# no-op unless a quiet spell is due, so a short interval is safe.
CONSOLIDATION_INTERVAL_SECONDS: Final = 300  # check for idle consolidation every 5 min
