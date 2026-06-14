# Changelog

All notable changes to **KONTINUUM Lite** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
