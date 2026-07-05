"""Button platform for Duratech DuraLink."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
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
from .coordinator import DuratechDuralinkCoordinator


BUTTONS: tuple[ButtonEntityDescription, ...] = (
    ButtonEntityDescription(
        key="program_up",
        translation_key="program_up",
    ),
    ButtonEntityDescription(
        key="program_down",
        translation_key="program_down",
    ),
    ButtonEntityDescription(
        key="lampen_sync",
        translation_key="lampen_sync",
    ),
)

BUTTON_NAMES: dict[str, str] = {
    "program_up": "Naechstes Programm",
    "program_down": "Vorheriges Programm",
    "lampen_sync": "Lampen-Sync",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Duratech DuraLink buttons."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(
        DuratechDuralinkButton(entry, coordinator, description)
        for description in BUTTONS
    )


class DuratechDuralinkButton(
    CoordinatorEntity[DuratechDuralinkCoordinator],
    ButtonEntity,
):
    """Duratech DuraLink command button."""

    entity_description: ButtonEntityDescription

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: DuratechDuralinkCoordinator,
        description: ButtonEntityDescription,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_name = BUTTON_NAMES[description.key]
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

    async def async_press(self) -> None:
        """Send the button command through the coordinator."""
        if self.entity_description.key == "program_up":
            await self.coordinator.async_next_program()
            return
        if self.entity_description.key == "program_down":
            await self.coordinator.async_previous_program()
            return
        await self.coordinator.async_lampen_sync()
