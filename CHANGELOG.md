# Changelog

All notable changes to **KONTINUUM Lite** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added
- **Stufe 3 from `kontinuum-core` 0.7: Lagebild and Börse** (lead ticket
  kontinuum-core#2). Active as soon as the installed core has them; with an
  older core nothing changes. The manifest rule stays `>=0.6.3,<0.7` until
  0.7.0 is released, then a small bump to `>=0.7.0,<0.8` switches it on.
  - **Presence per person** — `sensor.<entry>_presence_<person>` (0–100 %):
    inferred from the devices alone; the person's own trackers (`person`
    attribute `device_trackers`) are the label, never evidence, so the sensor
    is a second opinion next to the phone. Attributes: strongest evidence,
    what the trackers report, and the online hit rate (checked with
    knowledge at least a day old). Appears once the Lagebild has learned the
    person (after the first day).
  - **`sensor.<entry>_situation`** — how many persons the Lagebild holds home,
    plus the pair table's strongest associations ("if A, then B"). Presence
    is re-read at most once a minute, the associations (they read the whole
    table) once an hour — on a Pi that is a quarter second, not every event.
  - **Learning state** attributes `next_event` / `next_event_probability` (the
    engine's first guess for the next event) and `hit_rate` (how often the
    Börse's first guess was right so far).
  - Diagnostics report the Lagebild and Börse — persons numbered, not named.
- **GitLab CI** (`.gitlab-ci.yml`): the standard template (pytest with the
  Home Assistant test harness, hassfest, HACS metadata, secret scan); the
  GitHub release job stays off (Lite is private). A pipeline run with
  `KERN_VORSCHAU` tests against an unreleased core.
- **Pro-parity config & options flow (no more manual per-entity picking).**
  Lite now mirrors the Pro integration as closely as possible so switching
  Lite → Pro feels familiar. The initial flow asks for a **preset**
  (Mutig / Ausgeglichen / Konservativ); the menu-based options flow's
  **General** step exposes the same fields as Pro (minus the dashboard):
  - **Operation mode** — `shadow` (only observe), `confirm` (ask before every
    action via an actionable mobile notification) or `active` (act on its own).
  - **Entity tracking mode** — `standard` (all entities, opt-out via the
    `ignore_kontinuum` label), `labeled` (opt-in: only entities with the
    `kontinuum` label) or `auto` (smart heuristic filter). This replaces the
    old requirement to hand-pick every entity: by default the engine now sees
    **everything**, exactly like Pro.
  - **Home-Only mode** — pause while nobody is home.
- **Acting brain wired up.** The core's prefrontal cortex + cerebellum (already
  shipped in `kontinuum-core`) now drive real Home Assistant service calls.
  In `active` mode the engine acts autonomously; in `confirm` mode it queues
  the action and asks via an actionable notification (buttons **Bestätigen** /
  **Ablehnen**), with `kontinuum_lite.confirm_action` / `reject_action` as a
  dashboard-free fallback. Manual undo within 60 s feeds negative
  reinforcement back into the brain, just like Pro. No LLM/Cortex layer.
- **New services**: `set_mode`, `confirm_action`, `reject_action`.
- **New events**: `kontinuum_lite_action_executed`, `kontinuum_lite_confirm_rejected`.

### Changed
- **Local time for the core.** Home Assistant's timestamps are UTC, and the
  core reads hour and weekday straight off the timestamp — every time-of-day
  pattern sat one or two hours late (CET/CEST), and Saturday began at 1 or
  2 am. Events now reach the core in Home Assistant's local time. A brain
  learned before shifts its hour patterns once and relearns them.
- **Home-Only pauses learning, not the Lagebild.** While nobody is home the
  event learners still pause (as in Pro), but every change keeps reaching the
  Lagebild — the empty house is exactly what it learns "away" from. The echo
  of our own actions likewise reaches the Lagebild (the device *is* in that
  state now), just not the learners.
- **Heartbeat on the event loop.** The 5-minute heartbeat advances the
  Lagebild on the loop, where every state change touches it too, and only
  then hands the idle-consolidation check to the executor as before. The
  core's tick there finds the Lagebild current instead of moving it in a
  second thread while an event arrives.
- **Startup seed in time order**, oldest state first, so the brain's clock
  only moves forward; states the thalamus doesn't track (persons above all)
  go to the Lagebild only.
- **Global state-change ingestion.** Instead of subscribing to a hand-picked
  entity list, Lite now discovers all entities (with area + labels) and
  subscribes to every state change; the core thalamus does the filtering via
  `track_mode`. Config entries migrate automatically to the new v2 schema; the
  old manual entity list is superseded by `track_mode='standard'`.

### Fixed
- **Sensors no longer flicker on filtered changes.** With standard tracking
  most state changes are filtered by the core (no room, unregistered,
  repeats, bursts), and each one reset the surprise sensor to 0 and the
  anomaly to off until the next real event. A filtered observation now keeps
  the last real reading; only the counters move. Its decision is not kept, so
  nothing is executed twice.
- **Our own sensors are never registered as input.** After a restart they sit
  in the entity registry, and discovery handed them to the thalamus like any
  entity. With the Lite device in an area they were tracked, and the startup
  seed fed their states back into the brain; without one, the anomaly sensor
  still carried a semantic the Lagebild would have accepted.
- **Sleep consolidation now runs during idle.** Consolidation is only eligible
  during a quiet spell (≥30 min since the last event), but it was only ever
  *checked* on a state change — never during the downtime it needs — so an idle
  night consolidated nothing. `LiteEngine` gained a `tick()` heartbeat that
  drives core's self-gating `KontinuumEngine.tick()`, scheduled every
  `CONSOLIDATION_INTERVAL_SECONDS` (5 min). No-op unless a quiet spell is due;
  guarded so an older core is a safe no-op.

### Added
- **README status badges.** A row of real, clickable shields at the top of the
  README — Tests / hassfest / HACS-Validate workflow status, HACS custom-repo,
  minimum Home Assistant version, pinned `kontinuum-core`, and the AGPL-3.0
  licence — each linking to the live source it reports on.

### Changed
- Require **kontinuum-core >= 0.6.3** (manifest + test deps), the current
  release of the family; the `tick()` idle heartbeat (>= 0.6.2) stays a safe
  no-op on older cores.

## 0.5.0 (2026-06-20)

### Added
- **Observability attributes.** The engine's decision is now legible from the
  entities themselves:
  - `binary_sensor.*_anomaly` exposes `surprise`, `threshold` (the *adaptive*
    anomaly threshold) and `expected_next_room` — so "why did/didn't it flag?"
    is answerable at a glance.
  - `sensor.*_surprise` exposes `anomaly_threshold` and `token` (the current
    `room.semantic.state` the engine is reasoning over).
  - `sensor.*_learning_state` gains `total_events` (the post-filter event count
    the cold_start → learning → stable transitions key off).
- **Repair issue for the most common misconfiguration.** An instance with no
  observed entities silently sits at `cold_start` forever; it now raises a
  dismissible repair (Settings → Repairs) that points to the options flow and
  clears itself once entities are selected.
- Diagnostics now include `anomaly_threshold`, `token` and `expected_next_room`.
- `EngineSnapshot` gains a `token` field plus `anomaly_threshold` /
  `expected_next_room` convenience properties (read from the core `extra`,
  `None` when the core hasn't reported them yet).
- Tests for the new attributes and the repair issue (raised with no entities,
  cleared when entities are chosen). Integration version bumped to `0.5.0`.

## 0.4.0 (2026-06-20)

### Added
- **`save_brain` service** — force an immediate brain snapshot to disk (handy
  before a planned restart).
- **`reset_brain` service** — erase all learning (the full brain *and* the
  metaplasticity meta-state) and reload cold. The reset path skips the usual
  save-on-unload and deletes both persisted files (the metaplasticity path is
  read from the core, so a rename there won't leave stale state behind), then
  reloads so the engine comes back at `cold_start`.
- **Shutdown durability** — a `homeassistant_stop` listener flushes the brain
  (and metaplasticity) on HA shutdown, in addition to the existing
  save-on-unload, so a clean stop never loses learning.
- **German translations** (`translations/de.json`) plus the canonical
  `translations/en.json`, covering the config/options flow, entities and all
  three services.
- Tests for the new services (save writes the file; reset clears it and comes
  back cold).

### Changed
- Service handlers now resolve the active engine from `hass.data` on each call
  instead of closing over it at setup time. This fixes a latent bug where,
  after a reload (e.g. an options change), `evaluate` would have fed the stale,
  discarded engine. Integration version bumped to `0.4.0`.

## 0.3.0 (2026-06-20)

### Added
- **Automatic data ingestion.** The integration now actually learns on its
  own. You pick the entities to observe (in the config flow *and* a new
  **options flow**); each one is registered with the core (area + device_class
  + unit + friendly_name resolved from the entity/device/area registries) and
  its state changes are streamed into the engine via
  `async_track_state_change_event`. Current states are seeded at setup so
  learning starts immediately, not on the next change. Previously the only
  way in was a manual `evaluate` service call — and because the core drops
  observations for unregistered/area-less entities, Lite in practice never
  learned anything out of the box.
- **Options flow** to change the observed-entity list after setup; changing
  it reloads the entry so additions start contributing and removals stop.
- **Diagnostics platform** (`diagnostics.py`): dumps core version, whether the
  installed core supports brain persistence, tick/event counts and the current
  learning state — surfacing the previously invisible "old core silently
  no-ops persistence" case.
- **Test suite + CI.** HA-free contract tests pin the core data flow
  (register-with-area → learn; unregistered/area-less → skipped; persistence
  roundtrip) and `LiteEngine` projection/restore; HA-based tests cover the
  config/options flow and setup/teardown. New `Tests` workflow runs them on
  push/PR. Adds `requirements_test.txt` and `pyproject.toml` (pytest config).

### Changed
- **`manifest.json` now pins `kontinuum-core>=0.6.0,<0.7`** (was `>=0.1.2`
  with no upper bound — which contradicted the README's "latest 0.x" claim and
  would have happily installed a breaking 1.x). The ingestion path is verified
  against the 0.6.x API. Integration version bumped to `0.3.0`.
- Added `"loggers": ["kontinuum_core"]` to the manifest.
- The anomaly event now carries `entity_id` (the trigger) instead of echoing
  the raw service `payload`.
- The `evaluate` service and the new state listener share one ingestion helper,
  so both fire `kontinuum_lite_anomaly` on the same rising edge.

### Fixed
- **`learning_state` after a restart no longer shows `cold_start`** for a
  trained brain. `LiteEngine.restore()` now derives the state from the restored
  hippocampus stats instead of copying the stale default snapshot, so the
  sensor reflects continuity immediately rather than after the next tick.
- **Brain snapshots are skipped when nothing changed.** The periodic save now
  checks the tick count and writes only when the engine actually advanced —
  headless instances often idle, and HA frequently runs on flash/SD where
  needless writes cost endurance.

## 0.2.1 (2026-06-13)

### Added
- **Brain persistence across restarts.** The full learned engine state
  (hippocampus n-grams, predictive surprise history + adaptive anomaly
  threshold, cerebellum reflex rules, basal-ganglia Q-values, …) is now
  saved and restored, not just the MetaPlasticity meta-state. Previously
  every reload/restart rebuilt the brain from zero, so Lite never actually
  accumulated learning across HA restarts.
  - `LiteEngine.state_dict()` / `restore()` wrap the core
    `to_dict`/`from_dict`. They degrade gracefully: on `kontinuum-core`
    < 0.1.2 (no such API) `state_dict()` returns `None` and persistence is a
    silent no-op — exactly the old behaviour, no crash.
  - `_save_brain()` writes `brain.json.gz` atomically (temp file +
    `os.replace`) so a crash mid-write cannot corrupt the brain; `_load_brain()`
    tolerates a missing/corrupt file and cold-starts instead of failing setup.
  - The brain is snapshotted every `SAVE_INTERVAL_SECONDS` (10 min) via the
    `HAScheduler` and once more on unload, so an unclean shutdown loses at
    most ~10 min of learning.
- `.github/workflows/validate.yaml` — HACS validation on push/PR + daily cron.
- `.github/workflows/hassfest.yaml` — Home Assistant integration linter.
- `custom_components/kontinuum_lite/brand/icon.png` (256×256) and
  `icon@2x.png` (512×512). Required by HACS validation. The artwork is
  shared with the ha-kontinuum Pro integration since both belong to the
  same product family.
- `custom_components/kontinuum_lite/ha_scheduler.py` — `HAScheduler`
  adapter bridging `kontinuum_core.Scheduler` to
  `homeassistant.helpers.event.async_track_time_interval`. Sync callbacks
  run in HA's executor so blocking I/O (gzip writes) does not stall the
  event loop.
- `LiteEngine` constructor now accepts `scheduler` and `storage_path`,
  forwarded to the underlying `KontinuumEngine`.
- `async_setup_entry` instantiates the `HAScheduler`, loads persisted
  MetaPlasticity state, and starts the 24 h adaptation loop. Bootstrap
  failures are caught and logged so the engine works even without
  MetaPlasticity.
- `async_unload_entry` persists MetaPlasticity state and cancels the
  scheduler before tearing the integration down.
- `const.STORAGE_DIR = "kontinuum_lite"` for the per-instance sub-
  directory under `hass.config.path`.

### Changed
- `manifest.json` now pins **`kontinuum-core>=0.1.2`** (published to PyPI) —
  the release that adds the `to_dict`/`from_dict` API the brain persistence
  above relies on. Integration version bumped to `0.2.1`. No vendored copies.
- README banner cross-links the two sibling repos (`kontinuum-core`,
  `ha-kontinuum`).
- README "Status" section rewritten from "Phase 0 — stub" to "Phase 1+"
  with the real delegation story (engine pipeline lives in
  `kontinuum-core`; learning state derived from hippocampus stats).

## 0.2.0 (2026-04-13)

### Added
- `LiteEngine` thin wrapper around `kontinuum_core.KontinuumEngine`.
  Phase-1 wiring — all neuro-inspired logic now lives in the core
  package; Lite ships only the minimal HA-side glue (config flow,
  sensors, services).

## 0.1.0 (2026-04-10)

Initial Phase-0 skeleton: domain `kontinuum_lite`, config flow, three
sensors (`surprise`, `anomaly`, `learning_state`), `evaluate` service,
`kontinuum_lite_anomaly` event. Stub engine with deterministic
placeholder values for automation tests.
