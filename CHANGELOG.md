# Changelog

All notable changes to **KONTINUUM Lite** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
