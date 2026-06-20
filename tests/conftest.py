"""Shared fixtures for the test suite.

The HA-based tests need ``enable_custom_integrations`` (from
``pytest-homeassistant-custom-component``) so the ``kontinuum_lite`` custom
component is importable. The pure-Python contract/engine tests run without that
plugin installed, so the fixture degrades to a no-op when it isn't available.
"""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(request):
    """Enable custom integrations for HA tests; no-op without the HA plugin."""
    try:
        request.getfixturevalue("enable_custom_integrations")
    except Exception:  # noqa: BLE001 - fixture absent in HA-free runs
        pass
    yield
