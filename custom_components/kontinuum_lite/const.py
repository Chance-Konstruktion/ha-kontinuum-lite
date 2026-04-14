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

# Anomaly threshold on surprise (0..1)
ANOMALY_THRESHOLD: Final = 0.75

# Signal names for intra-integration dispatch
SIGNAL_UPDATE: Final = f"{DOMAIN}_update"
