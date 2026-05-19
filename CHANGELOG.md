# Changelog

All notable changes to **KONTINUUM Lite** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Unreleased

### Added
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
- `manifest.json` pins `kontinuum-core>=0.1.1` so the engine is pulled
  from PyPI on install. No more vendored copies.
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
