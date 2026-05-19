"""HAScheduler – Scheduler Protocol adapter for Home Assistant.

Bridges the HA-free ``kontinuum_core`` Scheduler Protocol with
``homeassistant.helpers.event.async_track_time_interval``.

Usage::

    scheduler = HAScheduler(hass)
    scheduler.schedule_interval(callback, interval_seconds=86400)
    # later on unload:
    scheduler.cancel_all()

The callback must be a plain synchronous callable (no ``async``).
HAScheduler runs it in a thread-pool executor so it does not block the
HA event loop.
"""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Callable

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval

_LOGGER = logging.getLogger(__name__)


class HAScheduler:
    """Wraps async_track_time_interval to satisfy the Scheduler Protocol.

    Sync callbacks are run in HA's executor so they may perform
    blocking I/O (e.g. gzip file writes from MetaPlasticity.save()).
    """

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._unsubs: list[Callable] = []

    def schedule_interval(
        self, callback: Callable, interval_seconds: float
    ) -> Callable[[], None]:
        """Register a recurring sync callback.

        Args:
            callback: Synchronous callable. Called with no arguments.
            interval_seconds: Interval between calls.

        Returns:
            A zero-arg cancel-handle that unregisters this specific callback.
        """
        async def _async_wrapper(_now) -> None:
            try:
                await self._hass.async_add_executor_job(callback)
            except Exception:
                _LOGGER.exception("HAScheduler: callback %s raised", callback)

        unsub = async_track_time_interval(
            self._hass,
            _async_wrapper,
            timedelta(seconds=interval_seconds),
        )
        self._unsubs.append(unsub)
        _LOGGER.debug(
            "HAScheduler: registered %s every %.0fs", callback, interval_seconds
        )

        def _cancel() -> None:
            try:
                unsub()
            except Exception:  # noqa: BLE001
                pass
            try:
                self._unsubs.remove(unsub)
            except ValueError:
                pass

        return _cancel

    def cancel_all(self) -> None:
        """Cancel all registered intervals."""
        for unsub in self._unsubs:
            try:
                unsub()
            except Exception:  # noqa: BLE001
                pass
        self._unsubs.clear()
