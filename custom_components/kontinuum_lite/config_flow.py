"""Config & options flow for KONTINUUM Lite."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import CONF_ENTITIES, CONF_NAME, DEFAULT_NAME, DOMAIN

_ENTITY_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(multiple=True)
)


class KontinuumLiteConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single-instance config flow for KONTINUUM Lite."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        # Only one instance allowed.
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(
                title=user_input.get(CONF_NAME, DEFAULT_NAME),
                data={CONF_NAME: user_input.get(CONF_NAME, DEFAULT_NAME)},
                options={CONF_ENTITIES: user_input.get(CONF_ENTITIES, [])},
            )

        schema = vol.Schema(
            {
                vol.Optional(CONF_NAME, default=DEFAULT_NAME): str,
                vol.Optional(CONF_ENTITIES, default=[]): _ENTITY_SELECTOR,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> KontinuumLiteOptionsFlow:
        return KontinuumLiteOptionsFlow()


class KontinuumLiteOptionsFlow(OptionsFlow):
    """Reconfigure which entities feed the learning substrate."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                data={CONF_ENTITIES: user_input.get(CONF_ENTITIES, [])}
            )

        current = self.config_entry.options.get(CONF_ENTITIES, [])
        schema = vol.Schema(
            {
                vol.Optional(CONF_ENTITIES, default=current): _ENTITY_SELECTOR,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
