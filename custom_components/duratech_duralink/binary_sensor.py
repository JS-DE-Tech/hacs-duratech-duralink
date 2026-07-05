"""Binary sensors for Duratech DuraLink."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
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
)
from .coordinator import DuratechDuralinkCoordinator, DuratechDuralinkData


@dataclass(frozen=True, kw_only=True)
class DuratechDuralinkBinarySensorDescription(BinarySensorEntityDescription):
    """Description for a Duratech DuraLink binary sensor."""

    value_fn: Callable[[DuratechDuralinkData], bool | None]


BINARY_SENSORS: tuple[DuratechDuralinkBinarySensorDescription, ...] = (
    DuratechDuralinkBinarySensorDescription(
        key="transformer_powered",
        translation_key="transformer_powered",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.transformer_powered,
    ),
    DuratechDuralinkBinarySensorDescription(
        key="lamp_is_on",
        translation_key="lamp_is_on",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.lamp_is_on,
    ),
    DuratechDuralinkBinarySensorDescription(
        key="delayed_power_off_timer_active",
        translation_key="delayed_power_off_timer_active",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.delayed_power_off_timer_active,
    ),
)

BINARY_SENSOR_NAMES: dict[str, str] = {
    "transformer_powered": "Trafo eingeschaltet",
    "lamp_is_on": "Lampe eingeschaltet",
    "delayed_power_off_timer_active": "Abschalt-Timer aktiv",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Duratech DuraLink binary sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        DuratechDuralinkBinarySensor(entry, coordinator, description)
        for description in BINARY_SENSORS
    )


class DuratechDuralinkBinarySensor(
    CoordinatorEntity[DuratechDuralinkCoordinator],
    BinarySensorEntity,
):
    """Duratech DuraLink binary sensor."""

    entity_description: DuratechDuralinkBinarySensorDescription

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: DuratechDuralinkCoordinator,
        description: DuratechDuralinkBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_name = BINARY_SENSOR_NAMES[description.key]
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
    def is_on(self) -> bool | None:
        """Return the binary sensor value."""
        return self.entity_description.value_fn(self.coordinator.data)
