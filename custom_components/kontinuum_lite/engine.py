"""Lite engine for KONTINUUM Lite (Phase 1).

Thin wrapper around ``kontinuum_core.KontinuumEngine``. The Lite
integration ships only the minimal HA-side glue (config flow, sensors,
services); all neuro-inspired logic lives in the core package.

The public surface (``observe`` / ``evaluate`` / ``snapshot``) is kept
stable so HA entities and automations written against Phase 0 continue
to work.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from kontinuum_core import KontinuumEngine

from .const import ANOMALY_THRESHOLD, STATE_COLD_START


@dataclass
class EngineSnapshot:
    """Minimal observable state exposed to HA entities."""

    surprise: float = 0.0
    anomaly: bool = False
    learning_state: str = STATE_COLD_START
    tick_count: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


class LiteEngine:
    """HA-side wrapper around ``KontinuumEngine``.

    Responsibilities:
      * own a single ``KontinuumEngine`` instance
      * translate HA state-change payloads into core observations
      * project the core snapshot into the Lite ``EngineSnapshot`` shape
    """

    def __init__(self) -> None:
        self._core = KontinuumEngine()
        self._snapshot = EngineSnapshot()

    # ---- Entity wiring ----------------------------------------------

    def register_entity(self, entity_id: str, **kwargs: Any) -> None:
        """Register an HA entity with the core thalamus."""
        self._core.register_entity(entity_id, **kwargs)

    # ---- Data flow ---------------------------------------------------

    def observe(self, payload: dict[str, Any] | None = None) -> EngineSnapshot:
        """Ingest one observation and advance internal state."""
        core_snap = self._core.observe(payload or {})
        self._snapshot = EngineSnapshot(
            surprise=float(core_snap.surprise),
            anomaly=core_snap.surprise >= ANOMALY_THRESHOLD,
            learning_state=core_snap.learning_state,
            tick_count=core_snap.tick_count,
            extra=core_snap.extra or {},
        )
        return self._snapshot

    def evaluate(self, payload: dict[str, Any] | None = None) -> EngineSnapshot:
        """Service-entry: run one tick and return the current snapshot."""
        return self.observe(payload)

    # ---- Accessors ---------------------------------------------------

    @property
    def snapshot(self) -> EngineSnapshot:
        return self._snapshot

    @property
    def core(self) -> KontinuumEngine:
        """Direct access to the underlying core engine (advanced use)."""
        return self._core
