"""Config flow for KONTINUUM Lite."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import CONF_NAME, DEFAULT_NAME, DOMAIN


class KontinuumLiteConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single-instance config flow for KONTINUUM Lite."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        # Only one instance allowed in Phase 0.
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(
                title=user_input.get(CONF_NAME, DEFAULT_NAME),
                data=user_input,
            )

        schema = vol.Schema(
            {vol.Optional(CONF_NAME, default=DEFAULT_NAME): str}
        )
        return self.async_show_form(step_id="user", data_schema=schema)
