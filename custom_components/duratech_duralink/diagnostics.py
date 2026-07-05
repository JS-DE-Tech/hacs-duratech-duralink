"""Diagnostics support for Duratech DuraLink."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import (
    GATEWAY_TARGET,
    INTEGRATION_VERSION,
    MANUFACTURER,
    MODEL_PLP_REM_350,
    PROTOCOL_NAME,
    TRANSPORT_NAME,
)

TO_REDACT: tuple[str, ...] = ()


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime_data = entry.runtime_data
    coordinator_data = runtime_data.coordinator.data
    device: dict[str, Any] = {
        "manufacturer": MANUFACTURER,
        "model": MODEL_PLP_REM_350,
        "firmware": INTEGRATION_VERSION,
        "hardware": GATEWAY_TARGET,
        "protocol": PROTOCOL_NAME,
        "transport": TRANSPORT_NAME,
    }
    runtime: dict[str, Any] = {
        "gateway_connection": coordinator_data.gateway_connection,
        "protocol": PROTOCOL_NAME,
        "transport": TRANSPORT_NAME,
        "transformer_powered": coordinator_data.transformer_powered,
        "lamp_is_on": coordinator_data.lamp_is_on,
        "last_lamp_command": coordinator_data.last_lamp_command,
        "active_light_program": coordinator_data.active_light_program,
        "last_rgb_color": coordinator_data.last_rgb_color,
        "last_color_temperature_kelvin": (
            coordinator_data.last_color_temperature_kelvin
        ),
        "last_brightness": coordinator_data.last_brightness,
        "last_mode": coordinator_data.last_mode,
        "power_state": coordinator_data.power_state,
        "power_state_source": coordinator_data.power_state_source,
        "remaining_power_off_countdown": (
            coordinator_data.remaining_power_off_countdown
        ),
        "last_rs485_command": coordinator_data.last_rs485_command,
        "queue_length": coordinator_data.queue_length,
        "init_phase": coordinator_data.init_phase,
        "init_command": coordinator_data.init_command,
        "init_command_history": coordinator_data.init_command_history,
        "auto_sync_status": coordinator_data.auto_sync_status,
        "power_on_countdown": coordinator_data.power_on_countdown,
    }
    if coordinator_data.last_error:
        runtime["last_error"] = coordinator_data.last_error

    return {
        "entry": {
            "data": async_redact_data(entry.data, TO_REDACT),
            "options": async_redact_data(entry.options, TO_REDACT),
        },
        "device": device,
        "runtime": runtime,
    }
