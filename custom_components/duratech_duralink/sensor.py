"""Diagnostic sensors for Duratech DuraLink."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    GATEWAY_TARGET,
    INTEGRATION_VERSION,
    MANUFACTURER,
    MODEL_PLP_REM_350,
    NAME,
    PROTOCOL_NAME,
    TRANSPORT_NAME,
)
from .coordinator import DuratechDuralinkCoordinator, DuratechDuralinkData


@dataclass(frozen=True, kw_only=True)
class DuratechDuralinkSensorDescription(SensorEntityDescription):
    """Description for a Duratech DuraLink diagnostic sensor."""

    value_fn: Callable[[DuratechDuralinkData], Any]


SENSORS: tuple[DuratechDuralinkSensorDescription, ...] = (
    DuratechDuralinkSensorDescription(
        key="gateway_connection",
        translation_key="gateway_connection",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.gateway_connection,
    ),
    DuratechDuralinkSensorDescription(
        key="protocol",
        translation_key="protocol",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: PROTOCOL_NAME,
    ),
    DuratechDuralinkSensorDescription(
        key="transport",
        translation_key="transport",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: TRANSPORT_NAME,
    ),
    DuratechDuralinkSensorDescription(
        key="last_rs485_command",
        translation_key="last_rs485_command",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.last_rs485_command,
    ),
    DuratechDuralinkSensorDescription(
        key="queue_length",
        translation_key="queue_length",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.queue_length,
    ),
    DuratechDuralinkSensorDescription(
        key="remaining_power_off_countdown",
        translation_key="remaining_power_off_countdown",
        native_unit_of_measurement="s",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.remaining_power_off_countdown,
    ),
    DuratechDuralinkSensorDescription(
        key="power_state",
        translation_key="power_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.power_state,
    ),
    DuratechDuralinkSensorDescription(
        key="power_state_source",
        translation_key="power_state_source",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.power_state_source,
    ),
    DuratechDuralinkSensorDescription(
        key="last_lamp_command",
        translation_key="last_lamp_command",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.last_lamp_command,
    ),
    DuratechDuralinkSensorDescription(
        key="active_light_program",
        translation_key="active_light_program",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.active_light_program,
    ),
    DuratechDuralinkSensorDescription(
        key="last_rgb_color",
        translation_key="last_rgb_color",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: (
            ",".join(str(value) for value in data.last_rgb_color)
            if data.last_rgb_color is not None
            else None
        ),
    ),
    DuratechDuralinkSensorDescription(
        key="last_color_temperature_kelvin",
        translation_key="last_color_temperature_kelvin",
        native_unit_of_measurement="K",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.last_color_temperature_kelvin,
    ),
    DuratechDuralinkSensorDescription(
        key="last_brightness",
        translation_key="last_brightness",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.last_brightness,
    ),
    DuratechDuralinkSensorDescription(
        key="last_mode",
        translation_key="last_mode",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.last_mode,
    ),
    DuratechDuralinkSensorDescription(
        key="desired_light_state",
        translation_key="desired_light_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.desired_light_state,
    ),
    DuratechDuralinkSensorDescription(
        key="rgb_join_state",
        translation_key="rgb_join_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.rgb_join_state,
    ),
    DuratechDuralinkSensorDescription(
        key="startup_sequence_state",
        translation_key="startup_sequence_state",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.startup_sequence_state,
    ),
    DuratechDuralinkSensorDescription(
        key="init_phase",
        translation_key="init_phase",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.init_phase,
    ),
    DuratechDuralinkSensorDescription(
        key="init_command",
        translation_key="init_command",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.init_command,
    ),
    DuratechDuralinkSensorDescription(
        key="init_command_history",
        translation_key="init_command_history",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.init_command_history,
    ),
    DuratechDuralinkSensorDescription(
        key="auto_sync_status",
        translation_key="auto_sync_status",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.auto_sync_status,
    ),
    DuratechDuralinkSensorDescription(
        key="power_on_countdown",
        translation_key="power_on_countdown",
        native_unit_of_measurement="s",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.power_on_countdown,
    ),
    DuratechDuralinkSensorDescription(
        key="protocol_debug_logging",
        translation_key="protocol_debug_logging",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.protocol_debug_logging,
    ),
)

SENSOR_NAMES: dict[str, str] = {
    "gateway_connection": "Gateway-Verbindung",
    "protocol": "Protocol",
    "transport": "Transport",
    "last_rs485_command": "Letzter RS485-Befehl",
    "queue_length": "Queue-Länge",
    "remaining_power_off_countdown": "Abschalt-Countdown",
    "power_state": "Power State",
    "power_state_source": "Power State Source",
    "last_lamp_command": "Letzter Lampenbefehl",
    "active_light_program": "Active Light Program",
    "last_rgb_color": "Last RGB Value",
    "last_color_temperature_kelvin": "Last Color Temperature",
    "last_brightness": "Last Brightness",
    "last_mode": "Last Mode",
    "desired_light_state": "Desired State",
    "rgb_join_state": "RGB Join State",
    "startup_sequence_state": "Init Phase (legacy)",
    "init_phase": "Init Phase",
    "init_command": "Init Command",
    "init_command_history": "Init Command History",
    "auto_sync_status": "Lampen-Sync Status",
    "power_on_countdown": "Power-On Countdown",
    "protocol_debug_logging": "Protokoll-Debug-Logging",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Duratech DuraLink sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        DuratechDuralinkSensor(entry, coordinator, description)
        for description in SENSORS
    )


class DuratechDuralinkSensor(
    CoordinatorEntity[DuratechDuralinkCoordinator],
    SensorEntity,
):
    """Duratech DuraLink diagnostic sensor."""

    entity_description: DuratechDuralinkSensorDescription

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: DuratechDuralinkCoordinator,
        description: DuratechDuralinkSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_name = SENSOR_NAMES[description.key]
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, entry.entry_id)},
            "manufacturer": MANUFACTURER,
            "model": MODEL_PLP_REM_350,
            "name": NAME,
            "hw_version": GATEWAY_TARGET,
            "sw_version": INTEGRATION_VERSION,
            "configuration_url": f"http://{entry.data[CONF_HOST]}",
        }

    @property
    def native_value(self) -> Any:
        """Return the sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)
