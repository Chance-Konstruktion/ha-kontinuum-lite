"""Config & options flow for KONTINUUM Lite.

Deliberately kept as close to the Pro integration (``ha-kontinuum``) as
possible: the same field keys, the same dropdown labels and the same
menu-based options flow — so a user upgrading Lite → Pro finds an identical
UI and keeps their settings. Lite simply omits the Pro-only "ballast":
the dashboard step and the Cortex/LLM agent steps.
"""
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
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .const import (
    CONF_HOME_ONLY,
    CONF_OPERATION_MODE,
    CONF_PRESET,
    CONF_TRACK_MODE,
    DEFAULT_OPERATION_MODE,
    DEFAULT_PRESET,
    DEFAULT_TRACK_MODE,
    DOMAIN,
    MODE_ACTIVE,
    MODE_CONFIRM,
    MODE_SHADOW,
    PRESET_BALANCED,
    PRESET_BOLD,
    PRESET_CONSERVATIVE,
    TRACK_AUTO,
    TRACK_LABELED,
    TRACK_STANDARD,
)

# ── Display labels (kept identical to the Pro integration) ─────────────
PRESET_LABELS: dict[str, str] = {
    PRESET_BOLD: "🔥 Mutig – Lernt schnell, macht anfangs Fehler",
    PRESET_BALANCED: "⚖️ Ausgeglichen – Guter Kompromiss (empfohlen)",
    PRESET_CONSERVATIVE: "🛡️ Konservativ – Beobachtet lange, handelt selten",
}

OPERATION_MODE_LABELS: dict[str, str] = {
    MODE_SHADOW: "👁️ Shadow – Nur beobachten, keine Aktionen",
    MODE_CONFIRM: "✋ Confirm – Fragt vor jeder Aktion",
    MODE_ACTIVE: "⚡ Active – Handelt selbstständig",
}

TRACK_MODE_LABELS: dict[str, str] = {
    TRACK_STANDARD: "Standard (all entities, opt-out)",
    TRACK_LABELED: "Labeled only (opt-in: only 'kontinuum' label)",
    TRACK_AUTO: "Automatic (smart heuristic filter)",
}


def _dropdown(options: dict[str, str]) -> SelectSelector:
    """Render a ``{value: label}`` mapping as a polished dropdown.

    Identical helper to the Pro integration so both flows look the same.
    """
    return SelectSelector(
        SelectSelectorConfig(
            options=[
                SelectOptionDict(value=str(value), label=str(label))
                for value, label in options.items()
            ],
            mode=SelectSelectorMode.DROPDOWN,
        )
    )


class KontinuumLiteConfigFlow(ConfigFlow, domain=DOMAIN):
    """Single-instance config flow for KONTINUUM Lite."""

    VERSION = 2

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """First step: choose the learning temperament (preset)."""
        # Only one instance allowed.
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(
                title="KONTINUUM Lite",
                data={
                    CONF_PRESET: user_input.get(CONF_PRESET, DEFAULT_PRESET),
                    # Sensible, safe defaults; refined later in the options flow.
                    CONF_OPERATION_MODE: DEFAULT_OPERATION_MODE,
                    CONF_TRACK_MODE: DEFAULT_TRACK_MODE,
                    CONF_HOME_ONLY: False,
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PRESET, default=DEFAULT_PRESET): _dropdown(
                        PRESET_LABELS
                    ),
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> KontinuumLiteOptionsFlow:
        return KontinuumLiteOptionsFlow()


class KontinuumLiteOptionsFlow(OptionsFlow):
    """Menu-based options flow — mirrors Pro's ``Allgemein | Fertig`` menu.

    Pro's menu is ``Allgemein | Cortex Agents | Fertig``; Lite drops the
    Cortex entry (no LLM layer) but keeps the identical "Allgemein" step and
    the same save-and-reload "Fertig" behaviour.
    """

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    def _current(self) -> dict[str, Any]:
        """Effective config: options override the entry data."""
        merged = dict(self.config_entry.data)
        merged.update(self.config_entry.options)
        merged.update(self._data)
        return merged

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Main menu: General | Finish."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["general", "finish"],
        )

    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """General: preset, operation mode, tracking, home-only."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_init()

        current = self._current()
        return self.async_show_form(
            step_id="general",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_PRESET,
                        default=current.get(CONF_PRESET, DEFAULT_PRESET),
                    ): _dropdown(PRESET_LABELS),
                    vol.Required(
                        CONF_OPERATION_MODE,
                        default=current.get(
                            CONF_OPERATION_MODE, DEFAULT_OPERATION_MODE
                        ),
                    ): _dropdown(OPERATION_MODE_LABELS),
                    vol.Required(
                        CONF_TRACK_MODE,
                        default=current.get(CONF_TRACK_MODE, DEFAULT_TRACK_MODE),
                    ): _dropdown(TRACK_MODE_LABELS),
                    vol.Required(
                        CONF_HOME_ONLY,
                        default=current.get(CONF_HOME_ONLY, False),
                    ): bool,
                }
            ),
        )

    async def async_step_finish(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Persist all collected settings; __init__ reloads on the update."""
        current = self._current()
        return self.async_create_entry(
            data={
                CONF_PRESET: current.get(CONF_PRESET, DEFAULT_PRESET),
                CONF_OPERATION_MODE: current.get(
                    CONF_OPERATION_MODE, DEFAULT_OPERATION_MODE
                ),
                CONF_TRACK_MODE: current.get(CONF_TRACK_MODE, DEFAULT_TRACK_MODE),
                CONF_HOME_ONLY: current.get(CONF_HOME_ONLY, False),
            }
        )
