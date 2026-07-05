"""Select platform for Duratech DuraLink programs."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    GATEWAY_TARGET,
    INTEGRATION_VERSION,
    MAIN_PROGRAM_OPTIONS,
    MANUFACTURER,
    MODEL_PLP_REM_350,
    NAME,
)
from .coordinator import DuratechDuralinkCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Duratech DuraLink select entities."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities([DuratechDuralinkProgramSelect(entry, coordinator)])


class DuratechDuralinkProgramSelect(
    CoordinatorEntity[DuratechDuralinkCoordinator],
    SelectEntity,
):
    """Program select entity."""

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: DuratechDuralinkCoordinator,
    ) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator)
        self._attr_name = "Lichtprogramm"
        self._attr_unique_id = f"{entry.entry_id}_program"
        self._attr_options = list(MAIN_PROGRAM_OPTIONS)
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
    def current_option(self) -> str | None:
        """Return the selected program."""
        return self.coordinator.data.selected_program

    async def async_select_option(self, option: str) -> None:
        """Select a program through the coordinator."""
        await self.coordinator.async_select_program(option)
