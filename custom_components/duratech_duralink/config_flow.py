"""Config flow for Duratech DuraLink."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_COMMAND_DEBOUNCE_MS,
    CONF_COMMAND_TERMINATOR,
    CONF_INTER_COMMAND_DELAY_MS,
    CONF_LAMP_WAKEUP_DELAY_MS,
    CONF_POWER_ENTITY_ID,
    CONF_POWER_MODE,
    CONF_POWER_OFF_DELAY,
    CONF_POWER_ON_DELAY,
    CONF_PROTOCOL_DEBUG_LOGGING,
    CONF_RGB_JOIN_TIMEOUT_MS,
    CONF_STARTUP_PRESET_COMMAND,
    CONF_STARTUP_PRESET_MODE,
    DEFAULT_COMMAND_DEBOUNCE_MS,
    DEFAULT_COMMAND_TERMINATOR,
    DEFAULT_INTER_COMMAND_DELAY_MS,
    DEFAULT_LAMP_WAKEUP_DELAY_MS,
    DEFAULT_PORT,
    DEFAULT_POWER_OFF_DELAY,
    DEFAULT_POWER_ON_DELAY,
    DEFAULT_PROTOCOL_DEBUG_LOGGING,
    DEFAULT_RGB_JOIN_TIMEOUT_MS,
    DEFAULT_STARTUP_PRESET_COMMAND,
    DEFAULT_STARTUP_PRESET_MODE,
    DEFAULT_TIMEOUT,
    DOMAIN,
    NAME,
    PowerMode,
    StartupPresetMode,
)
from .tcp_client import DuratechDuralinkTcpClient

_STARTUP_PRESET_COMMAND_OPTIONS = (
    {"label": "RGB", "value": "RGB"},
    {"label": "Blau (PS01)", "value": "PS01"},
    {"label": "Türkis (PS02)", "value": "PS02"},
    {"label": "Gelb (PS03)", "value": "PS03"},
    {"label": "Rot (PS04)", "value": "PS04"},
    {"label": "Grün (PS05)", "value": "PS05"},
    {"label": "Lila (PS06)", "value": "PS06"},
    {"label": "Warmweiß (PS07)", "value": "PS07"},
    {"label": "Blau (PS08)", "value": "PS08"},
    {"label": "Orange (PS09)", "value": "PS09"},
    {"label": "Farbwechsel langsam (PS10)", "value": "PS10"},
    {"label": "Farbwechsel schnell (PS11)", "value": "PS11"},
    {"label": "Warmweiß (PS12)", "value": "PS12"},
    {"label": "Neutralweiß (PS13)", "value": "PS13"},
    {"label": "Kaltweiß (PS14)", "value": "PS14"},
)


class DuratechDuralinkConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Duratech DuraLink."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._data: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> DuratechDuralinkOptionsFlow:
        """Create the options flow."""
        return DuratechDuralinkOptionsFlow(config_entry)

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Handle the initial setup step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = str(user_input[CONF_HOST]).strip()
            port = int(user_input[CONF_PORT])
            power_mode = PowerMode(user_input[CONF_POWER_MODE])

            if not _is_valid_host(host) or not _is_valid_port(port):
                errors["base"] = "invalid_host_or_port"
            else:
                self._data = {
                    CONF_HOST: host,
                    CONF_PORT: port,
                    CONF_POWER_MODE: power_mode.value,
                }
                if name := str(user_input.get(CONF_NAME, "")).strip():
                    self._data[CONF_NAME] = name

                if power_mode is PowerMode.HOME_ASSISTANT_ENTITY:
                    return await self.async_step_power_entity()
                return await self._async_test_and_create_entry()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                    vol.Optional(CONF_NAME): str,
                    vol.Required(
                        CONF_POWER_MODE,
                        default=PowerMode.NONE.value,
                    ): _power_mode_selector(),
                }
            ),
            errors=errors,
        )

    async def async_step_power_entity(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Collect the Home Assistant switch entity used for transformer power."""
        errors: dict[str, str] = {}

        if user_input is not None:
            entity_id = str(user_input[CONF_POWER_ENTITY_ID])
            if not entity_id.startswith("switch."):
                errors["base"] = "invalid_power_entity"
            else:
                self._data[CONF_POWER_ENTITY_ID] = entity_id
                return await self._async_test_and_create_entry()

        return self.async_show_form(
            step_id="power_entity",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_POWER_ENTITY_ID): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="switch")
                    )
                }
            ),
            errors=errors,
        )

    async def _async_test_and_create_entry(self) -> config_entries.ConfigFlowResult:
        """Run the TCP reachability test and create the entry."""
        host = self._data[CONF_HOST]
        port = self._data[CONF_PORT]
        unique_id = f"{host}:{port}"

        await self.async_set_unique_id(unique_id)
        self._abort_if_unique_id_configured()

        client = DuratechDuralinkTcpClient(host, port, DEFAULT_TIMEOUT)
        try:
            await client.async_test_connection()
        except (OSError, TimeoutError):
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(CONF_HOST, default=host): str,
                        vol.Required(CONF_PORT, default=port): int,
                        vol.Optional(
                            CONF_NAME,
                            default=self._data.get(CONF_NAME, ""),
                        ): str,
                        vol.Required(
                            CONF_POWER_MODE,
                            default=self._data.get(
                                CONF_POWER_MODE,
                                PowerMode.NONE.value,
                            ),
                        ): _power_mode_selector(),
                    }
                ),
                errors={"base": "cannot_connect"},
            )
        finally:
            await client.async_close()

        return self.async_create_entry(
            title=self._data.get(CONF_NAME, NAME),
            data=self._data,
            options=_default_options(),
        )

class DuratechDuralinkOptionsFlow(config_entries.OptionsFlow):
    """Handle options for Duratech DuraLink."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize the options flow."""
        self._config_entry = config_entry
        self._pending_options: dict[str, Any] = {}

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Manage integration options."""
        if user_input is not None:
            user_input = {**self._config_entry.options, **dict(user_input)}
            valid_option_keys = set(_default_options())
            user_input = {
                key: value
                for key, value in user_input.items()
                if key in valid_option_keys
            }
            user_input[CONF_POWER_ON_DELAY] = _duration_to_seconds(
                user_input[CONF_POWER_ON_DELAY]
            )
            user_input[CONF_POWER_OFF_DELAY] = _duration_to_seconds(
                user_input[CONF_POWER_OFF_DELAY]
            )
            user_input[CONF_COMMAND_TERMINATOR] = _normalize_terminator(
                user_input.get(CONF_COMMAND_TERMINATOR, DEFAULT_COMMAND_TERMINATOR)
            )
            self._pending_options = user_input
            return self.async_create_entry(title="", data=self._pending_options)

        options = {**_default_options(), **self._config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_POWER_ON_DELAY,
                        default=_seconds_to_duration(options[CONF_POWER_ON_DELAY]),
                    ): selector.DurationSelector(),
                    vol.Required(
                        CONF_POWER_OFF_DELAY,
                        default=_seconds_to_duration(options[CONF_POWER_OFF_DELAY]),
                    ): selector.DurationSelector(),
                    vol.Required(
                        CONF_COMMAND_DEBOUNCE_MS,
                        default=options[CONF_COMMAND_DEBOUNCE_MS],
                    ): vol.All(vol.Coerce(int), vol.Range(min=0)),
                    vol.Required(
                        CONF_RGB_JOIN_TIMEOUT_MS,
                        default=options[CONF_RGB_JOIN_TIMEOUT_MS],
                    ): vol.All(vol.Coerce(int), vol.Range(min=0)),
                    vol.Required(
                        CONF_LAMP_WAKEUP_DELAY_MS,
                        default=options[CONF_LAMP_WAKEUP_DELAY_MS],
                    ): vol.All(vol.Coerce(int), vol.Range(min=0)),
                    vol.Required(
                        CONF_INTER_COMMAND_DELAY_MS,
                        default=options[CONF_INTER_COMMAND_DELAY_MS],
                    ): vol.All(vol.Coerce(int), vol.Range(min=0)),
                    vol.Required(
                        CONF_STARTUP_PRESET_MODE,
                        default=options[CONF_STARTUP_PRESET_MODE],
                    ): _startup_preset_mode_selector(),
                    vol.Required(
                        CONF_STARTUP_PRESET_COMMAND,
                        default=options[CONF_STARTUP_PRESET_COMMAND],
                    ): _startup_preset_command_selector(),
                    vol.Optional(
                        CONF_COMMAND_TERMINATOR,
                        default=_normalize_terminator(
                            options[CONF_COMMAND_TERMINATOR]
                        ),
                    ): _terminator_selector(),
                    vol.Required(
                        CONF_PROTOCOL_DEBUG_LOGGING,
                        default=options[CONF_PROTOCOL_DEBUG_LOGGING],
                    ): bool,
                }
            ),
        )

def _default_options() -> dict[str, Any]:
    """Return default options."""
    return {
        CONF_POWER_ON_DELAY: DEFAULT_POWER_ON_DELAY,
        CONF_POWER_OFF_DELAY: DEFAULT_POWER_OFF_DELAY,
        CONF_COMMAND_DEBOUNCE_MS: DEFAULT_COMMAND_DEBOUNCE_MS,
        CONF_RGB_JOIN_TIMEOUT_MS: DEFAULT_RGB_JOIN_TIMEOUT_MS,
        CONF_LAMP_WAKEUP_DELAY_MS: DEFAULT_LAMP_WAKEUP_DELAY_MS,
        CONF_INTER_COMMAND_DELAY_MS: DEFAULT_INTER_COMMAND_DELAY_MS,
        CONF_STARTUP_PRESET_MODE: DEFAULT_STARTUP_PRESET_MODE,
        CONF_STARTUP_PRESET_COMMAND: DEFAULT_STARTUP_PRESET_COMMAND,
        CONF_COMMAND_TERMINATOR: DEFAULT_COMMAND_TERMINATOR,
        CONF_PROTOCOL_DEBUG_LOGGING: DEFAULT_PROTOCOL_DEBUG_LOGGING,
    }


def _seconds_to_duration(value: Any) -> dict[str, int]:
    """Return a duration selector value from stored seconds."""
    seconds = _duration_to_seconds(value)
    return {
        "hours": seconds // 3600,
        "minutes": (seconds % 3600) // 60,
        "seconds": seconds % 60,
    }


def _duration_to_seconds(value: Any) -> int:
    """Normalize duration selector or legacy integer values to seconds."""
    if isinstance(value, dict):
        return (
            int(value.get("hours", 0)) * 3600
            + int(value.get("minutes", 0)) * 60
            + int(value.get("seconds", 0))
        )
    return max(0, int(value))


def _power_mode_selector() -> selector.SelectSelector:
    """Return the power mode selector."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                {"label": "Dauerstrom", "value": PowerMode.NONE.value},
                {
                    "label": "Home Assistant Entität",
                    "value": PowerMode.HOME_ASSISTANT_ENTITY.value,
                },
            ],
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _terminator_selector() -> selector.SelectSelector:
    """Return the command terminator selector."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                {"label": "none", "value": ""},
                {"label": "\\r", "value": "\r"},
                {"label": "\\n", "value": "\n"},
                {"label": "\\r\\n", "value": "\r\n"},
            ],
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _startup_preset_mode_selector() -> selector.SelectSelector:
    """Return the startup preset mode selector."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[
                {
                    "label": "Vorgegebenes Programm",
                    "value": StartupPresetMode.FIXED_PROGRAM.value,
                },
                {
                    "label": "Letzte Einstellung wiederherstellen",
                    "value": StartupPresetMode.RESTORE_LAST_STATE.value,
                },
            ],
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _startup_preset_command_selector() -> selector.SelectSelector:
    """Return the startup preset command selector."""
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=list(_STARTUP_PRESET_COMMAND_OPTIONS),
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )


def _normalize_terminator(value: Any) -> str:
    """Normalize command terminator options from UI or legacy free text."""
    if value in ("", "\r", "\n", "\r\n"):
        return str(value)
    if value == "none":
        return ""
    if value == "\\r":
        return "\r"
    if value == "\\n":
        return "\n"
    if value == "\\r\\n":
        return "\r\n"
    return DEFAULT_COMMAND_TERMINATOR


def _is_valid_host(host: str) -> bool:
    """Return whether a host string is acceptable for the scaffold."""
    return bool(host) and not any(char.isspace() for char in host)


def _is_valid_port(port: int) -> bool:
    """Return whether a TCP port is valid."""
    return 0 < port <= 65535
