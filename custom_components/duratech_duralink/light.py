"""Light platform for Duratech DuraLink."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    COLOR_TEMPERATURE_STEP_KELVIN,
    DEFAULT_COLOR_TEMPERATURE_KELVIN,
    DOMAIN,
    GATEWAY_TARGET,
    INTEGRATION_VERSION,
    MANUFACTURER,
    MAX_COLOR_TEMPERATURE_KELVIN,
    MIN_COLOR_TEMPERATURE_KELVIN,
    MODEL_PLP_REM_350,
    NAME,
)
from .coordinator import DuratechDuralinkCoordinator

_LOGGER = logging.getLogger(__name__)


def _normalize_color_temperature_kelvin(color_temperature_kelvin: int) -> int:
    """Clamp and round Kelvin to the supported 500 K protocol step."""
    kelvin = max(
        MIN_COLOR_TEMPERATURE_KELVIN,
        min(MAX_COLOR_TEMPERATURE_KELVIN, int(color_temperature_kelvin)),
    )
    offset = kelvin - MIN_COLOR_TEMPERATURE_KELVIN
    rounded_steps = int(
        (offset + COLOR_TEMPERATURE_STEP_KELVIN / 2)
        // COLOR_TEMPERATURE_STEP_KELVIN
    )
    return MIN_COLOR_TEMPERATURE_KELVIN + (
        rounded_steps * COLOR_TEMPERATURE_STEP_KELVIN
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Duratech DuraLink light entity."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities([DuratechDuralinkLight(entry, coordinator)])


class DuratechDuralinkLight(CoordinatorEntity[DuratechDuralinkCoordinator], LightEntity):
    """Primary native Home Assistant light entity."""

    _attr_color_mode = ColorMode.RGB
    _attr_supported_color_modes = {ColorMode.RGB, ColorMode.COLOR_TEMP}
    _attr_min_color_temp_kelvin = MIN_COLOR_TEMPERATURE_KELVIN
    _attr_max_color_temp_kelvin = MAX_COLOR_TEMPERATURE_KELVIN

    def __init__(
        self,
        entry: ConfigEntry,
        coordinator: DuratechDuralinkCoordinator,
    ) -> None:
        """Initialize the light entity."""
        super().__init__(coordinator)
        self._entry = entry
        self._attr_name = "Poolbeleuchtung"
        self._attr_unique_id = f"{entry.entry_id}_light"
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
        """Return optimistic on state."""
        return self.coordinator.data.optimistic_is_on

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        """Return color modes supported by the DuraLink light."""
        color_modes = {ColorMode.RGB, ColorMode.COLOR_TEMP}
        self._debug("DuraLink supported_color_modes=%s", color_modes)
        return color_modes

    @property
    def color_mode(self) -> ColorMode:
        """Return active color mode without hiding RGB controls after effects."""
        color_mode = (
            ColorMode.COLOR_TEMP
            if self.coordinator.data.optimistic_mode == "color_temp"
            else ColorMode.RGB
        )
        self._debug(
            "DuraLink color_mode decision=%s is_on=%s desired=%s effect=%s rgb=%s color_temp=%s",
            color_mode,
            self.is_on,
            self.coordinator.data.desired_light_state,
            self.effect,
            self.rgb_color,
            self.color_temp_kelvin,
        )
        return color_mode

    @property
    def brightness(self) -> int | None:
        """Return optimistic brightness."""
        return self.coordinator.data.optimistic_brightness

    @property
    def rgb_color(self) -> tuple[int, int, int]:
        """Return a stable RGB value so Home Assistant keeps the picker visible."""
        rgb_color = (
            self.coordinator.data.optimistic_rgb_color
            or self.coordinator.data.last_rgb_color
            or (255, 255, 255)
        )
        self._debug("DuraLink rgb_color=%s", rgb_color)
        return rgb_color

    @property
    def color_temp_kelvin(self) -> int:
        """Return active or last known color temperature."""
        return (
            self.coordinator.data.optimistic_color_temperature_kelvin
            or self.coordinator.data.last_color_temperature_kelvin
            or DEFAULT_COLOR_TEMPERATURE_KELVIN
        )

    @property
    def effect(self) -> str | None:
        """Do not expose DuraLink programs as Home Assistant light effects."""
        return None

    @property
    def available(self) -> bool:
        """Return entity availability."""
        return self.coordinator.last_update_success

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on through the coordinator."""
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        rgb_color = kwargs.get(ATTR_RGB_COLOR)
        color_temperature_kelvin = kwargs.get("color_temp_kelvin")
        effect = kwargs.get("effect")

        await self.coordinator.async_turn_on(
            brightness=int(brightness) if brightness is not None else None,
            rgb_color=rgb_color,
            color_temperature_kelvin=(
                _normalize_color_temperature_kelvin(color_temperature_kelvin)
                if color_temperature_kelvin is not None
                else None
            ),
            effect=str(effect) if effect is not None else None,
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off through the coordinator."""
        await self.coordinator.async_turn_off()

    def _debug(self, message: str, *args: object) -> None:
        """Log light diagnostics only when protocol debug logging is enabled."""
        if self.coordinator.data.protocol_debug_logging:
            _LOGGER.debug(message, *args)
