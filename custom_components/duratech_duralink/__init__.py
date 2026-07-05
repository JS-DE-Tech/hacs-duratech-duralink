"""Duratech DuraLink Home Assistant integration scaffold."""

from __future__ import annotations

from dataclasses import dataclass
import logging

import homeassistant.config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.storage import Store
import voluptuous as vol

from .command_manager import DuratechDuralinkCommandManager
from .const import (
    ATTR_BRIGHTNESS,
    ATTR_COMMAND,
    ATTR_EFFECT,
    ATTR_ENTRY_ID,
    ATTR_INTENT,
    ATTR_RGB_COLOR,
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
    DEFAULT_COMMAND_TERMINATOR,
    DEFAULT_INTER_COMMAND_DELAY_MS,
    DEFAULT_LAMP_WAKEUP_DELAY_MS,
    DEFAULT_POWER_OFF_DELAY,
    DEFAULT_POWER_ON_DELAY,
    DEFAULT_PROTOCOL_DEBUG_LOGGING,
    DEFAULT_RGB_JOIN_TIMEOUT_MS,
    DEFAULT_STARTUP_PRESET_COMMAND,
    DEFAULT_STARTUP_PRESET_MODE,
    DEFAULT_TIMEOUT,
    DOMAIN,
    PLATFORMS,
    POWER_STATE_SOURCE_HA_SWITCH_STATE,
    PowerMode,
    SERVICE_CANCEL_POWER_TIMER,
    SERVICE_EXECUTE_INTENT,
    SERVICE_LAMPEN_SYNC,
    SERVICE_REFRESH,
    SERVICE_SEND_RAW_COMMAND,
    SERVICE_TURN_TRANSFORMER_OFF,
    SERVICE_TURN_TRANSFORMER_ON,
)
from .coordinator import DuratechDuralinkCoordinator
from .power_controller import DuratechDuralinkPowerController, PowerControllerConfig
from .protocol import DuratechDuralinkProtocol
from .tcp_client import DuratechDuralinkTcpClient

_LOGGER = logging.getLogger(__name__)
STORAGE_VERSION = 1


@dataclass(slots=True)
class DuratechDuralinkRuntimeData:
    """Runtime objects owned by a config entry."""

    tcp_client: DuratechDuralinkTcpClient
    protocol: DuratechDuralinkProtocol
    power_controller: DuratechDuralinkPowerController
    command_manager: DuratechDuralinkCommandManager
    coordinator: DuratechDuralinkCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Duratech DuraLink from a config entry."""
    tcp_client = DuratechDuralinkTcpClient(
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        DEFAULT_TIMEOUT,
        entry.options.get(CONF_COMMAND_TERMINATOR, DEFAULT_COMMAND_TERMINATOR),
        entry.options.get(
            CONF_PROTOCOL_DEBUG_LOGGING,
            DEFAULT_PROTOCOL_DEBUG_LOGGING,
        ),
    )
    protocol = DuratechDuralinkProtocol()
    power_mode = PowerMode(entry.data.get(CONF_POWER_MODE, PowerMode.NONE))
    if power_mode is PowerMode.KNX_GROUP_ADDRESS:
        _LOGGER.warning(
            "Direct KNX power control is deprecated. Please create a Home Assistant switch entity and select it as power actuator."
        )
        power_mode = PowerMode.NONE
    power_controller = DuratechDuralinkPowerController(
        hass,
        PowerControllerConfig(
            mode=power_mode,
            entity_id=entry.data.get(CONF_POWER_ENTITY_ID),
            protocol_debug_logging=entry.options.get(
                CONF_PROTOCOL_DEBUG_LOGGING,
                DEFAULT_PROTOCOL_DEBUG_LOGGING,
            ),
        ),
    )
    store = Store(
        hass,
        STORAGE_VERSION,
        f"{DOMAIN}.{entry.entry_id}.light_state",
    )
    stored_light_state = await store.async_load()

    command_manager = DuratechDuralinkCommandManager(
        tcp_client,
        protocol,
        power_controller,
        entry.options.get(CONF_POWER_ON_DELAY, DEFAULT_POWER_ON_DELAY),
        entry.options.get(CONF_POWER_OFF_DELAY, DEFAULT_POWER_OFF_DELAY),
        entry.options.get(CONF_RGB_JOIN_TIMEOUT_MS, DEFAULT_RGB_JOIN_TIMEOUT_MS),
        entry.options.get(
            CONF_LAMP_WAKEUP_DELAY_MS,
            DEFAULT_LAMP_WAKEUP_DELAY_MS,
        ),
        entry.options.get(
            CONF_INTER_COMMAND_DELAY_MS,
            DEFAULT_INTER_COMMAND_DELAY_MS,
        ),
        entry.options.get(CONF_STARTUP_PRESET_MODE, DEFAULT_STARTUP_PRESET_MODE),
        entry.options.get(
            CONF_STARTUP_PRESET_COMMAND,
            DEFAULT_STARTUP_PRESET_COMMAND,
        ),
        entry.options.get(
            CONF_PROTOCOL_DEBUG_LOGGING,
            DEFAULT_PROTOCOL_DEBUG_LOGGING,
        ),
        stored_light_state if isinstance(stored_light_state, dict) else None,
    )
    command_manager.set_persist_callback(store.async_save)
    coordinator = DuratechDuralinkCoordinator(hass, tcp_client, command_manager)

    entry.runtime_data = DuratechDuralinkRuntimeData(
        tcp_client=tcp_client,
        protocol=protocol,
        power_controller=power_controller,
        command_manager=command_manager,
        coordinator=coordinator,
    )
    command_manager.set_update_callback(coordinator.command_manager_updated)
    await _async_setup_power_state_tracking(
        hass,
        entry,
        command_manager,
        power_controller,
    )
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _async_register_services(hass)

    await coordinator.async_refresh()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


def _entry_value(
    entry: ConfigEntry,
    key: str,
    default: object | None = None,
) -> object | None:
    """Return an option value with config data fallback."""
    if key in entry.options:
        return entry.options[key]
    return entry.data.get(key, default)


async def _async_setup_power_state_tracking(
    hass: HomeAssistant,
    entry: ConfigEntry,
    command_manager: DuratechDuralinkCommandManager,
    power_controller: DuratechDuralinkPowerController,
) -> None:
    """Track actual transformer switch state when a HA switch is configured."""
    if (
        power_controller.config.mode is not PowerMode.HOME_ASSISTANT_ENTITY
        or power_controller.config.entity_id is None
    ):
        return

    entity_id = power_controller.config.entity_id

    @callback
    def _async_power_switch_state_changed(event: object) -> None:
        new_state = event.data.get("new_state")  # type: ignore[attr-defined]
        if new_state is None:
            return
        powered = _ha_switch_powered_state(new_state.state)
        hass.async_create_task(
            command_manager.async_update_transformer_power_state(
                powered,
                POWER_STATE_SOURCE_HA_SWITCH_STATE,
                cancel_power_off_timer=powered is not None,
            )
        )

    entry.async_on_unload(
        async_track_state_change_event(
            hass,
            [entity_id],
            _async_power_switch_state_changed,
        )
    )

    current_state = hass.states.get(entity_id)
    if current_state is not None:
        powered = _ha_switch_powered_state(current_state.state)
        await command_manager.async_update_transformer_power_state(
            powered,
            POWER_STATE_SOURCE_HA_SWITCH_STATE,
            cancel_power_off_timer=powered is False,
        )


def _ha_switch_powered_state(state: str) -> bool | None:
    """Convert a HA switch state string into transformer power state."""
    if state == STATE_ON:
        return True
    if state == STATE_OFF:
        return False
    return None


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.command_manager.async_shutdown()
        await entry.runtime_data.tcp_client.async_close()
    return unload_ok


async def _async_update_listener(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _async_register_services(hass: HomeAssistant) -> None:
    """Register Duratech DuraLink services once."""
    if hass.services.has_service(DOMAIN, SERVICE_REFRESH):
        return

    hass.services.async_register(
        DOMAIN,
        SERVICE_REFRESH,
        _async_handle_refresh,
        schema=vol.Schema({vol.Optional(ATTR_ENTRY_ID): str}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_RAW_COMMAND,
        _async_handle_send_raw_command,
        schema=vol.Schema(
            {
                vol.Optional(ATTR_ENTRY_ID): str,
                vol.Required(ATTR_COMMAND): str,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_CANCEL_POWER_TIMER,
        _async_handle_cancel_power_timer,
        schema=vol.Schema({vol.Optional(ATTR_ENTRY_ID): str}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_TURN_TRANSFORMER_ON,
        _async_handle_turn_transformer_on,
        schema=vol.Schema({vol.Optional(ATTR_ENTRY_ID): str}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_TURN_TRANSFORMER_OFF,
        _async_handle_turn_transformer_off,
        schema=vol.Schema({vol.Optional(ATTR_ENTRY_ID): str}),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_EXECUTE_INTENT,
        _async_handle_execute_intent,
        schema=vol.Schema(
            {
                vol.Optional(ATTR_ENTRY_ID): str,
                vol.Required(ATTR_INTENT): str,
                vol.Optional(ATTR_BRIGHTNESS): vol.Coerce(int),
                vol.Optional(ATTR_RGB_COLOR): object,
                vol.Optional(ATTR_EFFECT): str,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LAMPEN_SYNC,
        _async_handle_lampen_sync,
        schema=vol.Schema({vol.Optional(ATTR_ENTRY_ID): str}),
    )


async def _async_handle_refresh(call: ServiceCall) -> None:
    """Refresh coordinator data."""
    coordinator = _coordinator_from_call(call)
    await coordinator.async_refresh()


async def _async_handle_send_raw_command(call: ServiceCall) -> None:
    """Send an advanced raw command through the CommandManager."""
    command = str(call.data[ATTR_COMMAND]).strip()
    if not command:
        raise HomeAssistantError("Raw DuraLink command must not be empty")
    coordinator = _coordinator_from_call(call)
    await coordinator.async_send_raw_command(command)


async def _async_handle_cancel_power_timer(call: ServiceCall) -> None:
    """Cancel the delayed power-off timer."""
    coordinator = _coordinator_from_call(call)
    await coordinator.async_cancel_power_timer()


async def _async_handle_turn_transformer_on(call: ServiceCall) -> None:
    """Turn the configured transformer power actuator on."""
    coordinator = _coordinator_from_call(call)
    await coordinator.async_turn_transformer_on()


async def _async_handle_turn_transformer_off(call: ServiceCall) -> None:
    """Turn the configured transformer power actuator off."""
    coordinator = _coordinator_from_call(call)
    await coordinator.async_turn_transformer_off()


async def _async_handle_execute_intent(call: ServiceCall) -> None:
    """Execute a semantic intent through the coordinator."""
    coordinator = _coordinator_from_call(call)
    intent = str(call.data[ATTR_INTENT]).strip()

    if intent == "set_brightness":
        if ATTR_BRIGHTNESS not in call.data:
            raise HomeAssistantError(
                "brightness is required for this DuraLink intent"
            )
    if intent == "set_effect":
        if ATTR_EFFECT not in call.data:
            raise HomeAssistantError("effect is required for this DuraLink intent")
    try:
        await coordinator.async_execute_intent(
            intent,
            brightness=call.data.get(ATTR_BRIGHTNESS),
            rgb_color=_parse_rgb_color(call.data.get(ATTR_RGB_COLOR)),
            effect=call.data.get(ATTR_EFFECT),
        )
    except ValueError as err:
        raise HomeAssistantError(str(err)) from err


async def _async_handle_lampen_sync(call: ServiceCall) -> None:
    """Run the Lampen-Sync procedure through the coordinator."""
    coordinator = _coordinator_from_call(call)
    try:
        await coordinator.async_lampen_sync()
    except RuntimeError as err:
        raise HomeAssistantError(str(err)) from err


def _coordinator_from_call(call: ServiceCall) -> DuratechDuralinkCoordinator:
    """Return the coordinator selected by service call data."""
    entry_id = call.data.get(ATTR_ENTRY_ID)
    entries = [
        entry
        for entry in call.hass.config_entries.async_entries(DOMAIN)
        if entry.state is homeassistant.config_entries.ConfigEntryState.LOADED
    ]
    if entry_id is not None:
        entries = [entry for entry in entries if entry.entry_id == entry_id]
    if not entries:
        raise HomeAssistantError("No loaded Duratech DuraLink entry found")
    return entries[0].runtime_data.coordinator


def _parse_rgb_color(value: object) -> tuple[int, int, int] | None:
    """Parse an RGB value from a service call."""
    if value is None:
        return None
    if isinstance(value, str):
        parts: list[object] = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple)):
        parts = list(value)
    else:
        raise HomeAssistantError("rgb_color must be a comma-separated string or list")
    if len(parts) != 3:
        raise HomeAssistantError("rgb_color must contain red, green, and blue")
    red, green, blue = (max(0, min(255, int(part))) for part in parts)
    return red, green, blue
