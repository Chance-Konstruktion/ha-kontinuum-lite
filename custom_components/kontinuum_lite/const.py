"""Constants for KONTINUUM Lite."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "kontinuum_lite"

# Config-flow keys
CONF_NAME: Final = "name"
DEFAULT_NAME: Final = "KONTINUUM Lite"

# Services & events
SERVICE_EVALUATE: Final = "evaluate"
EVENT_ANOMALY: Final = "kontinuum_lite_anomaly"

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
