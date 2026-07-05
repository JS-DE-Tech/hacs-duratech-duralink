"""Power controller abstraction for optional transformer power control."""

from __future__ import annotations

from dataclasses import dataclass
import logging

from homeassistant.const import ATTR_ENTITY_ID, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .const import (
    POWER_STATE_SOURCE_HA_SWITCH_STATE,
    POWER_STATE_SOURCE_OPTIMISTIC,
    POWER_STATE_SOURCE_UNKNOWN,
    PowerMode,
)

_LOGGER = logging.getLogger(__name__)


KNX_DEPRECATION_MESSAGE = (
    "Direct KNX power control is deprecated. Please create a Home Assistant "
    "switch entity and select it as power actuator."
)


@dataclass(slots=True)
class PowerControllerConfig:
    """Power controller configuration."""

    mode: PowerMode
    entity_id: str | None = None
    knx_group_address: str | None = None
    knx_power_command_group_address: str | None = None
    knx_power_status_group_address: str | None = None
    knx_power_same_command_status: bool = True
    protocol_debug_logging: bool = False


class PowerControllerError(HomeAssistantError):
    """Raised when transformer power control fails."""


class DuratechDuralinkPowerController:
    """Optional transformer power controller abstraction.

    Direct KNX power control is deprecated. KNX users should expose the
    actuator as a Home Assistant switch and select that entity here.
    Shelly devices are supported through Home Assistant switch entities only.
    """

    def __init__(self, hass: HomeAssistant, config: PowerControllerConfig) -> None:
        """Initialize the power controller."""
        self.hass = hass
        self.config = config

    @property
    def exists(self) -> bool:
        """Return whether an external power actuator is configured."""
        return self.config.mode is PowerMode.HOME_ASSISTANT_ENTITY

    @property
    def state_source(self) -> str:
        """Return the source of the currently readable power state."""
        if not self.exists:
            return POWER_STATE_SOURCE_OPTIMISTIC
        if self.config.mode is PowerMode.HOME_ASSISTANT_ENTITY:
            return POWER_STATE_SOURCE_HA_SWITCH_STATE
        if self.config.mode is PowerMode.KNX_GROUP_ADDRESS:
            return POWER_STATE_SOURCE_UNKNOWN
        return POWER_STATE_SOURCE_UNKNOWN

    async def async_is_on(self) -> bool | None:
        """Return current transformer power state if known."""
        if not self.exists:
            return None
        if (
            self.config.mode is PowerMode.HOME_ASSISTANT_ENTITY
            and self.config.entity_id is not None
        ):
            state = self.hass.states.get(self.config.entity_id)
            return state is not None and state.state == STATE_ON
        if self.config.mode is PowerMode.KNX_GROUP_ADDRESS:
            _LOGGER.warning(KNX_DEPRECATION_MESSAGE)
            return None
        return None

    async def async_turn_on(self) -> None:
        """Turn transformer power on."""
        if not self.exists:
            return
        if (
            self.config.mode is PowerMode.HOME_ASSISTANT_ENTITY
            and self.config.entity_id is not None
        ):
            await self.hass.services.async_call(
                "switch",
                "turn_on",
                {ATTR_ENTITY_ID: self.config.entity_id},
                blocking=True,
            )
            return

        if self.config.mode is PowerMode.KNX_GROUP_ADDRESS:
            _LOGGER.warning(KNX_DEPRECATION_MESSAGE)
            return

    async def async_turn_off(self) -> None:
        """Turn transformer power off."""
        if not self.exists:
            return
        if (
            self.config.mode is PowerMode.HOME_ASSISTANT_ENTITY
            and self.config.entity_id is not None
        ):
            await self.hass.services.async_call(
                "switch",
                "turn_off",
                {ATTR_ENTITY_ID: self.config.entity_id},
                blocking=True,
            )
            return

        if self.config.mode is PowerMode.KNX_GROUP_ADDRESS:
            _LOGGER.warning(KNX_DEPRECATION_MESSAGE)
            return
