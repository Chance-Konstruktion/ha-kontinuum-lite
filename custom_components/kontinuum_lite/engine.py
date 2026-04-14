"""Stub engine for KONTINUUM Lite (Phase 0).

This placeholder mirrors the future ``kontinuum_core.KontinuumEngine``
contract (see ROADMAP.md §4 in ha-kontinuum). It returns deterministic
dummy values so the integration boots end-to-end without depending on
the Pro integration.

Phase 1 replaces the internals with vendored core modules (hippocampus,
predictive_processing, metaplasticity, ...). The public surface
(``observe`` / ``evaluate`` / ``snapshot``) must remain stable.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .const import STATE_COLD_START, STATE_LEARNING, STATE_STABLE


@dataclass
class EngineSnapshot:
    """Minimal observable state exposed to HA entities."""

    surprise: float = 0.0
    anomaly: bool = False
    learning_state: str = STATE_COLD_START
    tick_count: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


class LiteEngine:
    """Tiny placeholder engine.

    Responsibilities in Phase 0:
      * hold a monotonic tick counter
      * expose a stable snapshot shape
      * flip learning_state after N ticks so UI has something to show

    Phase 1 TODO: delegate to ``kontinuum_core.KontinuumEngine``.
    """

    # Phase-0 heuristic: how many observe() calls before we leave cold-start.
    _COLD_START_TICKS = 10
    _STABLE_TICKS = 100

    def __init__(self) -> None:
        self._snapshot = EngineSnapshot()

    # ---- Data flow ---------------------------------------------------

    def observe(self, payload: dict[str, Any] | None = None) -> EngineSnapshot:
        """Ingest one observation and advance internal state."""
        self._snapshot.tick_count += 1
        self._snapshot.learning_state = self._derive_learning_state()
        # Phase-0 stub: surprise stays 0.0, anomaly False.
        # Phase-1 replaces this with predictive_processing output.
        return self._snapshot

    def evaluate(self, payload: dict[str, Any] | None = None) -> EngineSnapshot:
        """Service-entry: run one tick and return the current snapshot."""
        return self.observe(payload)

    # ---- Accessors ---------------------------------------------------

    @property
    def snapshot(self) -> EngineSnapshot:
        return self._snapshot

    # ---- Internals ---------------------------------------------------

    def _derive_learning_state(self) -> str:
        t = self._snapshot.tick_count
        if t < self._COLD_START_TICKS:
            return STATE_COLD_START
        if t < self._STABLE_TICKS:
            return STATE_LEARNING
        return STATE_STABLE
