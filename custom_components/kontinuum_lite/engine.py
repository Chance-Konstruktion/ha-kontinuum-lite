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

from kontinuum_core import KontinuumEngine, Scheduler

from .const import STATE_COLD_START


@dataclass
class EngineSnapshot:
    """Minimal observable state exposed to HA entities."""

    surprise: float = 0.0
    anomaly: bool = False
    learning_state: str = STATE_COLD_START
    tick_count: int = 0
    token: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def anomaly_threshold(self) -> float | None:
        """The core's current adaptive anomaly threshold, if exposed."""
        value = self.extra.get("anomaly_threshold")
        return float(value) if isinstance(value, (int, float)) else None

    @property
    def expected_next_room(self) -> str | None:
        """The room the engine currently predicts will activate next."""
        return self.extra.get("expected_next_room")


class LiteEngine:
    """HA-side wrapper around ``KontinuumEngine``.

    Responsibilities:
      * own a single ``KontinuumEngine`` instance
      * translate HA state-change payloads into core observations
      * project the core snapshot into the Lite ``EngineSnapshot`` shape
    """

    def __init__(
        self,
        scheduler: Scheduler | None = None,
        storage_path: str | None = None,
    ) -> None:
        self._core = KontinuumEngine(
            scheduler=scheduler,
            storage_path=storage_path,
        )
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
            # Anomalie-Entscheidung kommt vom Core: dort ist die Schwelle
            # adaptiv (Baseline + 2σ) statt einer fixen Konstante.
            anomaly=bool(core_snap.anomaly),
            learning_state=core_snap.learning_state,
            tick_count=core_snap.tick_count,
            token=getattr(core_snap, "token", None),
            extra=core_snap.extra or {},
        )
        return self._snapshot

    def evaluate(self, payload: dict[str, Any] | None = None) -> EngineSnapshot:
        """Service-entry: run one tick and return the current snapshot."""
        return self.observe(payload)

    def tick(self) -> dict[str, Any] | None:
        """Host heartbeat so idle-only maintenance can run.

        Sleep consolidation in core is only *eligible* during a quiet spell
        (≥30 min since the last event), but core historically only ever
        *checked* it on the event path — the one moment it can never be quiet
        — so a genuinely idle night consolidated zero times. ``kontinuum-core``
        >= 0.6.2 exposes ``KontinuumEngine.tick()``, a cheap, self-gating
        heartbeat meant to be called on a timer; it does nothing unless
        consolidation is due and returns the stats dict when a cycle ran.

        Guarded with ``getattr`` so an older core (which lacks ``tick``) is a
        safe no-op rather than a crash.
        """
        tick = getattr(self._core, "tick", None)
        return tick() if callable(tick) else None

    # ---- Persistence -------------------------------------------------

    @property
    def supports_persistence(self) -> bool:
        """True when the installed core can serialize its state (>= 0.1.2)."""
        return callable(getattr(self._core, "to_dict", None)) and callable(
            getattr(self._core, "from_dict", None)
        )

    def state_dict(self) -> dict[str, Any] | None:
        """Serialize the full learned engine state for persistence.

        Returns ``None`` when the installed ``kontinuum-core`` predates the
        ``to_dict``/``from_dict`` API (< 0.1.2); the caller then keeps only
        the metaplasticity meta-state, exactly as before — no crash, no
        bogus file.
        """
        to_dict = getattr(self._core, "to_dict", None)
        return to_dict() if callable(to_dict) else None

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore engine state produced by :meth:`state_dict`.

        Returns ``True`` when the core accepted the state, ``False`` when
        persistence is unsupported by the installed core or ``data`` is not
        a usable mapping (e.g. a corrupt/empty file).
        """
        from_dict = getattr(self._core, "from_dict", None)
        if not callable(from_dict) or not isinstance(data, dict) or not data:
            return False
        from_dict(data)
        # Reflect the restored tick count *and* learning state so both sensors
        # show continuity immediately. Deriving the learning state from the
        # restored hippocampus stats avoids the old bug where the sensor read
        # ``cold_start`` after restoring a brain with thousands of events, until
        # the next tick. surprise/anomaly still refresh on the next observation.
        derive = getattr(self._core, "_learning_state", None)
        learning_state = derive() if callable(derive) else STATE_COLD_START
        self._snapshot = EngineSnapshot(
            learning_state=learning_state,
            tick_count=int(getattr(self._core, "tick_count", 0)),
        )
        return True

    # ---- Accessors ---------------------------------------------------

    @property
    def snapshot(self) -> EngineSnapshot:
        return self._snapshot

    @property
    def tick_count(self) -> int:
        """Total ticks the core has processed (survives restarts via restore).

        Used as a cheap dirty marker for persistence: if it hasn't advanced
        since the last save, there is nothing new to write.
        """
        return int(getattr(self._core, "tick_count", 0))

    @property
    def total_events(self) -> int:
        """Number of events the hippocampus actually learned from (post-filter)."""
        hippo = getattr(self._core, "hippocampus", None)
        return int(getattr(hippo, "total_events", 0))

    @property
    def core(self) -> KontinuumEngine:
        """Direct access to the underlying core engine (advanced use)."""
        return self._core
