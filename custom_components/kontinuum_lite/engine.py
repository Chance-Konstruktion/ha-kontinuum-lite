"""Lite engine for KONTINUUM Lite (Phase 1).

Thin wrapper around ``kontinuum_core.KontinuumEngine``. The Lite
integration ships only the minimal HA-side glue (config flow, sensors,
services); all neuro-inspired logic lives in the core package.

The public surface (``observe`` / ``evaluate`` / ``snapshot``) is kept
stable so HA entities and automations written against Phase 0 continue
to work.
"""
from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from typing import Any

from kontinuum_core import KontinuumEngine, Scheduler

from .const import (
    DEFAULT_OPERATION_MODE,
    DEFAULT_TRACK_MODE,
    STATE_COLD_START,
)

try:  # pragma: no cover - depends on installed core version
    from kontinuum_core.prefrontal_cortex import Decision
except Exception:  # noqa: BLE001 - tolerate older cores
    Decision = None  # type: ignore[assignment]

try:  # pragma: no cover - depends on installed core version
    # kontinuum-core >= 0.7.0 (Stufe 3): the Lagebild's host-neutral entry
    # point — reads a state the way the thalamus reads it.
    from kontinuum_core.association_cortex import lage_setzen
except Exception:  # noqa: BLE001 - cores < 0.7 have no Lagebild
    lage_setzen = None  # type: ignore[assignment]

# How many of the pair table's strongest associations the Lagebild surfaces.
LAGEBILD_ASSOCIATIONS = 10


@dataclass
class EngineSnapshot:
    """Minimal observable state exposed to HA entities."""

    surprise: float = 0.0
    anomaly: bool = False
    learning_state: str = STATE_COLD_START
    tick_count: int = 0
    token: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)
    # The engine's first guess for the next event (decoded token) and its
    # probability. From kontinuum-core 0.7 on, it comes from the Börse.
    next_event: str | None = None
    next_event_probability: float | None = None

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
        # Stufe 3: targets of the presence inference are ``person.*`` and the
        # trackers that belong to a person (kept current by the integration
        # via ``set_person_trackers``). Every other tracker — a router
        # integration creates one per device on the network — stays evidence:
        # the PC's tracker says something about who is home, but it is nobody.
        # Installed before any restore, because the core keeps only the
        # targets its predicate accepts.
        self._person_trackers: frozenset[str] = frozenset()
        self._lagebild: dict[str, Any] = {}
        self._lagebild_at: float | None = None
        self._associations_at: float | None = None
        cortex = self.association_cortex
        if cortex is not None:
            cortex.ziel_pruefer = self._is_presence_target

    # ---- Entity wiring ----------------------------------------------

    def register_entity(self, entity_id: str, **kwargs: Any) -> None:
        """Register an HA entity with the core thalamus."""
        self._core.register_entity(entity_id, **kwargs)

    # ---- Data flow ---------------------------------------------------

    def observe(self, payload: dict[str, Any] | None = None) -> EngineSnapshot:
        """Ingest one observation and advance internal state."""
        core_snap = self._core.observe(payload or {})
        if "skipped" in (core_snap.extra or {}):
            # A filtered observation (unregistered entity, no room, repeat,
            # burst) carries no reading of its own. With standard tracking
            # most changes are filtered, so projecting them flickered the
            # surprise to 0 and the anomaly to off between real events. Keep
            # the last real reading; only the counters move. The decision is
            # NOT kept: it belongs to the event that produced it, and carrying
            # it over would execute it again on every filtered change.
            self._snapshot = replace(
                self._snapshot,
                learning_state=core_snap.learning_state,
                tick_count=core_snap.tick_count,
                extra={k: v for k, v in self._snapshot.extra.items() if k != "decision"},
            )
            return self._snapshot
        next_event, next_p = self._first_prediction(getattr(core_snap, "predictions", None))
        self._snapshot = EngineSnapshot(
            surprise=float(core_snap.surprise),
            # Anomalie-Entscheidung kommt vom Core: dort ist die Schwelle
            # adaptiv (Baseline + 2σ) statt einer fixen Konstante.
            anomaly=bool(core_snap.anomaly),
            learning_state=core_snap.learning_state,
            tick_count=core_snap.tick_count,
            token=getattr(core_snap, "token", None),
            extra=core_snap.extra or {},
            next_event=next_event,
            next_event_probability=next_p,
        )
        return self._snapshot

    def _first_prediction(self, predictions: Any) -> tuple[str | None, float | None]:
        """Decode the head of the core's prediction list ``(token_id, p, …)``
        into ``room.semantic.state`` — ``None`` while the core has no guess
        (cold start)."""
        if not predictions:
            return None, None
        try:
            token_id, probability = predictions[0][0], float(predictions[0][1])
            return self._core.thalamus.decode_token(token_id), round(probability, 3)
        except Exception:  # noqa: BLE001 - a foreign shape is no crash
            return None, None

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

    # ---- Stufe 3: Lagebild + Börse (kontinuum-core >= 0.7) ----------

    @property
    def association_cortex(self):
        """The core's Lagebild (``AssociationCortex``), or ``None`` (core < 0.7)."""
        return getattr(self._core, "association_cortex", None)

    @property
    def supports_lagebild(self) -> bool:
        """True when the installed core keeps a Lagebild (>= 0.7.0)."""
        return self.association_cortex is not None and lage_setzen is not None

    def _is_presence_target(self, entity_id: str) -> bool:
        return entity_id.startswith("person.") or entity_id in self._person_trackers

    def set_person_trackers(self, trackers: Iterable[str]) -> None:
        """The trackers that belong to a person (attribute ``device_trackers``
        of the ``person.*`` entities): presence targets, never evidence."""
        self._person_trackers = frozenset(trackers)

    def feed_lagebild(self, entity_id: str, state: Any, timestamp: Any = None) -> None:
        """Put one state into the Lagebild only — no event for the learners.

        For what the event path holds back although it is part of the
        situation: changes while Home-Only pauses learning, the echo of our own
        actions, and at startup the current state of what the thalamus does
        not track (persons above all). ``observe`` feeds the Lagebild itself,
        so never call both for one change. A no-op on cores < 0.7.
        """
        cortex = self.association_cortex
        if cortex is None or lage_setzen is None or not entity_id:
            return
        lage_setzen(cortex, self._core.thalamus, entity_id, state, timestamp)

    def lagebild(self, now: Any = None, associations: bool = True) -> dict[str, Any]:
        """What the Lagebild sensors show (kept as :attr:`lagebild_data`).

        ``presence`` per target: how likely it is home, inferred from the
        devices alone — the target's own trackers are its label, never
        evidence — with the strongest evidence, what the target itself
        reports, and how often the inference matched that report so far.
        ``associations``: the strongest "if A, then B" of the pair table. They
        read the whole table (quadratic), so callers pass
        ``associations=False`` (keeping the last ones) except now and then
        (see :attr:`associations_age`). ``now`` advances the Lagebild's
        clock — time passes without events, too. ``{}`` on cores < 0.7.
        """
        cortex = self.association_cortex
        if cortex is None:
            return {}
        if now is not None:
            cortex.tick(now)
        stats = cortex.stats
        checks = stats.get("anwesenheit") or {}
        presence: dict[str, Any] = {}
        for target in list(cortex.ziele):
            reading = cortex.anwesenheit(target)
            if reading.get("zuhause") is None:
                continue  # nothing learned yet
            check = checks.get(target) or {}
            presence[target] = {
                "home": round(reading["zuhause"], 3),
                "most_likely": reading["wahrscheinlichster"],
                "reported": cortex.zustand.get(target),
                "evidence": [[feature, round(weight, 1)] for feature, weight in reading["belege"]],
                "time_of_day": reading["uhrzeit"],
                "ticks": reading["takte"],
                "checked": check.get("takte_geprueft", 0),
                "hit_rate": check.get("treffer"),
            }
        if associations:
            pairs = [
                {
                    "if": pair["wenn"],
                    "then": pair["dann"],
                    "p": pair["p"],
                    "lift": pair["lift"],
                    "ticks": pair["takte"],
                }
                for pair in cortex.zusammenhaenge(top=LAGEBILD_ASSOCIATIONS)
            ]
            self._associations_at = time.monotonic()
        else:
            pairs = self._lagebild.get("associations", [])
        self._lagebild = {
            "presence": presence,
            "associations": pairs,
            "learning": {
                "entities_in_view": stats.get("entitaeten_im_blick", 0),
                "targets": stats.get("ziele", []),
                "ticks": stats.get("takte", 0),
                "pair_features": stats.get("paar_merkmale", 0),
            },
        }
        self._lagebild_at = time.monotonic()
        return self._lagebild

    @property
    def lagebild_data(self) -> dict[str, Any]:
        """The last result of :meth:`lagebild` (``{}`` before the first)."""
        return self._lagebild

    @property
    def lagebild_age(self) -> float:
        """Seconds since :meth:`lagebild` last ran (``inf`` before the first)."""
        if self._lagebild_at is None:
            return float("inf")
        return time.monotonic() - self._lagebild_at

    @property
    def associations_age(self) -> float:
        """Seconds since the associations were last recomputed (``inf`` before)."""
        if self._associations_at is None:
            return float("inf")
        return time.monotonic() - self._associations_at

    @property
    def boerse(self) -> dict[str, Any] | None:
        """The Börse's balance (core >= 0.7): how often its first guess for
        the next event was right, and the weight it learned per expert."""
        claustrum = getattr(self._core, "claustrum", None)
        stats = getattr(claustrum, "stats", None) if claustrum is not None else None
        if not isinstance(stats, dict):
            return None
        return {
            "hit_rate": stats.get("trefferquote"),
            "events": stats.get("ereignisse"),
            "weights": stats.get("gewichte"),
        }

    # ---- Configuration: preset / modes ------------------------------

    def apply_preset(self, params: dict[str, Any]) -> None:
        """Tune learning aggressiveness from a preset (same knobs as Pro).

        Every knob is set defensively so a core that renames/drops one of them
        degrades to a no-op instead of raising.
        """
        cerebellum = getattr(self._core, "cerebellum", None)
        hippocampus = getattr(self._core, "hippocampus", None)
        if cerebellum is not None:
            if "cerebellum_min_obs" in params:
                cerebellum.MIN_OBSERVATIONS = params["cerebellum_min_obs"]
            if "cerebellum_min_conf" in params:
                cerebellum.MIN_CONFIDENCE = params["cerebellum_min_conf"]
        if hippocampus is not None:
            if "hippocampus_decay" in params:
                hippocampus.DECAY_RATE = params["hippocampus_decay"]
            if "hippocampus_min_obs" in params:
                hippocampus.MIN_OBSERVATIONS = params["hippocampus_min_obs"]

    def set_operation_mode(self, mode: str) -> bool:
        """Set shadow/confirm/active on the core prefrontal cortex."""
        pfc = self.prefrontal
        setter = getattr(pfc, "set_operation_mode", None) if pfc else None
        if callable(setter):
            return bool(setter(mode))
        return False

    @property
    def operation_mode(self) -> str:
        pfc = self.prefrontal
        return getattr(pfc, "operation_mode", DEFAULT_OPERATION_MODE)

    def set_track_mode(self, mode: str) -> None:
        """Set which entities the thalamus keeps (standard/labeled/auto)."""
        thalamus = self.thalamus
        if thalamus is not None:
            thalamus.track_mode = mode

    @property
    def track_mode(self) -> str:
        thalamus = self.thalamus
        return getattr(thalamus, "track_mode", DEFAULT_TRACK_MODE)

    # ---- Decision / action surface ----------------------------------

    @property
    def prefrontal(self):
        """Core prefrontal cortex (decision instance), or ``None``."""
        return getattr(self._core, "prefrontal_cortex", None)

    @property
    def thalamus(self):
        """Core thalamus (entity registry / tracking), or ``None``."""
        return getattr(self._core, "thalamus", None)

    @property
    def last_decision(self) -> dict[str, Any] | None:
        """The advisory decision the core computed on the last observation.

        Shape: ``{"token", "entity_id", "stage", "confidence", "utility",
        "risk", "source", "n_obs", "reasons"}`` — see kontinuum-core's
        ``_build_extra``. ``None`` when the core produced no decision.
        """
        dec = self._snapshot.extra.get("decision")
        return dec if isinstance(dec, dict) else None

    def _decision_obj(self, decision: dict[str, Any]):
        """Rebuild a core ``Decision`` from the snapshot dict.

        The engine only surfaces the decision as a dict; the core's
        ``get_service_call`` / ``queue_confirm`` want the object. token_id is
        not surfaced (only used for confirm-id uniqueness and best-effort
        reinforcement), so it stays 0.
        """
        if Decision is None:
            return None
        obj = Decision()
        obj.token = decision.get("token", "")
        obj.entity_id = decision.get("entity_id", "")
        obj.confidence = decision.get("confidence", 0.0)
        obj.utility = decision.get("utility", 0.0)
        obj.risk = decision.get("risk", 0.0)
        obj.n_obs = decision.get("n_obs", 0)
        obj.source = decision.get("source", "")
        obj.reasons = list(decision.get("reasons", []) or [])
        obj.stage = decision.get("stage", "")
        return obj

    def service_call_for(self, decision: dict[str, Any]) -> dict[str, Any] | None:
        """Translate a decision into a HA service call spec, or ``None``.

        Returns ``{"domain", "service", "entity_id", "data"}`` exactly like the
        core's ``PrefrontalCortex.get_service_call``.
        """
        pfc = self.prefrontal
        obj = self._decision_obj(decision)
        if pfc is None or obj is None:
            return None
        getter = getattr(pfc, "get_service_call", None)
        return getter(obj) if callable(getter) else None

    def queue_confirm(
        self, decision: dict[str, Any], reasoning: str = "", context: dict | None = None
    ) -> str | None:
        """Park an actionable decision awaiting human confirmation.

        Returns the confirm_id, or ``None`` if the core can't queue.
        """
        pfc = self.prefrontal
        obj = self._decision_obj(decision)
        queue = getattr(pfc, "queue_confirm", None) if pfc else None
        if not callable(queue) or obj is None:
            return None
        return queue(obj, reasoning=reasoning, context=context or {})

    def take_pending(self, confirm_id: str):
        """Pop a pending confirmation, returning its ``Decision`` or ``None``."""
        pfc = self.prefrontal
        getter = getattr(pfc, "get_pending_confirm", None) if pfc else None
        return getter(confirm_id) if callable(getter) else None

    def reject_pending(self, confirm_id: str) -> dict[str, Any] | None:
        """Reject a pending confirmation and feed back negative reinforcement."""
        pfc = self.prefrontal
        rej = getattr(pfc, "reject_pending", None) if pfc else None
        if not callable(rej):
            return None
        return rej(
            confirm_id,
            basal_ganglia=getattr(self._core, "basal_ganglia", None),
            amygdala=getattr(self._core, "amygdala", None),
        )

    def pending_confirms(self) -> list[dict[str, Any]]:
        """List all pending confirmations (rich dicts) for a status sensor."""
        pfc = self.prefrontal
        getter = getattr(pfc, "get_all_pending_confirms", None) if pfc else None
        return getter() if callable(getter) else []

    def get_service_call_obj(self, decision_obj) -> dict[str, Any] | None:
        """Service-call spec for an already-materialised ``Decision`` object."""
        pfc = self.prefrontal
        getter = getattr(pfc, "get_service_call", None) if pfc else None
        return getter(decision_obj) if callable(getter) and decision_obj else None

    # ---- Feedback / own-action bookkeeping --------------------------

    def mark_own_action(self, entity_id: str, token: str = "", semantic: str = "") -> None:
        pfc = self.prefrontal
        marker = getattr(pfc, "mark_own_action", None) if pfc else None
        if callable(marker):
            marker(entity_id, token=token, semantic=semantic)

    def is_own_action(self, entity_id: str) -> bool:
        pfc = self.prefrontal
        checker = getattr(pfc, "is_own_action", None) if pfc else None
        return bool(checker(entity_id)) if callable(checker) else False

    def check_override(self, entity_id: str, new_state: str) -> bool:
        """Detect a quick manual undo of one of our actions (neg. feedback)."""
        pfc = self.prefrontal
        checker = getattr(pfc, "check_override", None) if pfc else None
        if not callable(checker):
            return False
        return bool(checker(entity_id, new_state, getattr(self._core, "amygdala", None)))

    def entity_semantic(self, entity_id: str) -> str | None:
        """The semantic the thalamus assigned to an entity, if tracked."""
        thalamus = self.thalamus
        mapping = getattr(thalamus, "entity_semantic", None) if thalamus else None
        return mapping.get(entity_id) if isinstance(mapping, dict) else None

    @property
    def tracked_count(self) -> int:
        """How many entities the thalamus is actually tracking."""
        thalamus = self.thalamus
        mapping = getattr(thalamus, "entity_semantic", None) if thalamus else None
        return len(mapping) if isinstance(mapping, dict) else 0

    @property
    def core(self) -> KontinuumEngine:
        """Direct access to the underlying core engine (advanced use)."""
        return self._core
