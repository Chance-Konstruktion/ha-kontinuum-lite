"""Config & options flow tests (require Home Assistant)."""
from __future__ import annotations

import pytest

pytest.importorskip("homeassistant")

from homeassistant import config_entries  # noqa: E402
from homeassistant.core import HomeAssistant  # noqa: E402
from homeassistant.data_entry_flow import FlowResultType  # noqa: E402
from pytest_homeassistant_custom_component.common import MockConfigEntry  # noqa: E402

from custom_components.kontinuum_lite.const import (  # noqa: E402
    CONF_HOME_ONLY,
    CONF_OPERATION_MODE,
    CONF_PRESET,
    CONF_TRACK_MODE,
    DEFAULT_OPERATION_MODE,
    DEFAULT_TRACK_MODE,
    DOMAIN,
    MODE_CONFIRM,
    PRESET_BOLD,
    TRACK_LABELED,
)


async def test_user_flow_creates_entry_with_preset(hass: HomeAssistant) -> None:
    """The initial flow only asks for a preset; modes get sensible defaults."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PRESET: PRESET_BOLD}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_PRESET] == PRESET_BOLD
    assert result["data"][CONF_OPERATION_MODE] == DEFAULT_OPERATION_MODE
    assert result["data"][CONF_TRACK_MODE] == DEFAULT_TRACK_MODE
    assert result["data"][CONF_HOME_ONLY] is False


async def test_single_instance_only(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_options_flow_general_updates_settings(hass: HomeAssistant) -> None:
    """The menu-based options flow saves the General step and reloads."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=DOMAIN,
        version=2,
        data={CONF_PRESET: PRESET_BOLD},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "general"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "general"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_PRESET: PRESET_BOLD,
            CONF_OPERATION_MODE: MODE_CONFIRM,
            CONF_TRACK_MODE: TRACK_LABELED,
            CONF_HOME_ONLY: True,
        },
    )
    # Back to the menu; now pick "Finish" to persist.
    assert result["type"] is FlowResultType.MENU

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "finish"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_OPERATION_MODE] == MODE_CONFIRM
    assert entry.options[CONF_TRACK_MODE] == TRACK_LABELED
    assert entry.options[CONF_HOME_ONLY] is True
