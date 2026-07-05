"""Coordinator for the Duratech DuraLink integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .command_manager import DuratechDuralinkCommandManager
from .const import (
    DOMAIN,
    GatewayConnectionState,
    InitPhase,
    POWER_STATE_SOURCE_UNKNOWN,
    PowerState,
)
from .tcp_client import DuratechDuralinkTcpClient

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class DuratechDuralinkData:
    """Coordinator data exposed to scaffold entities."""

    gateway_connection: str = GatewayConnectionState.DISCONNECTED.value
    selected_program: str | None = None
    last_rs485_command: str | None = None
    last_response: str | None = None
    last_error: str | None = None
    queue_length: int = 0
    remaining_power_off_countdown: int = 0
    desired_light_state: str = "unknown"
    optimistic_is_on: bool | None = None
    optimistic_brightness: int | None = None
    optimistic_rgb_color: tuple[int, int, int] | None = None
    optimistic_color_temperature_kelvin: int | None = None
    optimistic_effect: str | None = None
    active_light_program: str | None = None
    last_rgb_color: tuple[int, int, int] | None = None
    last_color_temperature_kelvin: int | None = None
    last_brightness: int | None = None
    last_mode: str | None = None
    optimistic_mode: str | None = None
    rgb_join_state: str = "idle"
    protocol_debug_logging: bool = False
    startup_sequence_state: str = InitPhase.IDLE.value
    startup_sequence_running: bool = False
    startup_sequence_task_active: bool = False
    init_phase: str = InitPhase.IDLE.value
    init_command: str = "idle"
    init_command_history: str = ""
    auto_sync_status: str = "Bereit"
    power_on_countdown: int = 0
    power_state: str = PowerState.UNKNOWN.value
    power_state_source: str = POWER_STATE_SOURCE_UNKNOWN
    transformer_powered: bool | None = None
    lamp_is_on: bool | None = None
    last_lamp_command: str | None = None
    delayed_power_off_timer_active: bool = False
    reconnect_counter: int = 0


class DuratechDuralinkCoordinator(DataUpdateCoordinator[DuratechDuralinkData]):
    """Central coordinator for runtime state and entity updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        tcp_client: DuratechDuralinkTcpClient,
        command_manager: DuratechDuralinkCommandManager,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=30),
        )
        self.tcp_client = tcp_client
        self.command_manager = command_manager
        self.data = DuratechDuralinkData()

    async def _async_update_data(self) -> DuratechDuralinkData:
        """Refresh scaffold data without polling RS485 yet."""
        if self.command_manager.power_controller.exists:
            transformer_powered = (
                await self.command_manager.power_controller.async_is_on()
            )
            await self.command_manager.async_update_transformer_power_state(
                transformer_powered,
                self.command_manager.power_controller.state_source,
                cancel_power_off_timer=transformer_powered is False,
            )
        self._sync_from_command_manager()
        self.data.gateway_connection = self.tcp_client.connection_state
        return self.data

    async def async_turn_on(
        self,
        *,
        brightness: int | None = None,
        rgb_color: tuple[int, int, int] | None = None,
        color_temperature_kelvin: int | None = None,
        effect: str | None = None,
    ) -> None:
        """Route a light-on request through the command manager."""
        await self.command_manager.async_turn_on(
            brightness=brightness,
            rgb_color=rgb_color,
            color_temperature_kelvin=color_temperature_kelvin,
            effect=effect,
        )
        self._sync_from_command_manager()
        self.async_set_updated_data(self.data)

    async def async_turn_off(self) -> None:
        """Route a light-off request through the command manager."""
        await self.command_manager.async_turn_off()
        self._sync_from_command_manager()
        self.async_set_updated_data(self.data)

    async def async_set_brightness(self, brightness: int) -> None:
        """Route a brightness request through the command manager."""
        await self.command_manager.async_set_brightness(brightness)
        self._sync_from_command_manager()
        self.async_set_updated_data(self.data)

    async def async_set_rgb(self, rgb_color: tuple[int, int, int]) -> None:
        """Route an RGB request through the command manager."""
        await self.command_manager.async_set_rgb(rgb_color)
        self._sync_from_command_manager()
        self.async_set_updated_data(self.data)

    async def async_set_effect(self, effect: str) -> None:
        """Route an effect/program request through the command manager."""
        await self.command_manager.async_set_effect(effect)
        self.data.selected_program = self.command_manager.active_light_program
        self._sync_from_command_manager()
        self.async_set_updated_data(self.data)

    async def async_select_program(self, program: str) -> None:
        """Route a main program selection through the command manager."""
        await self.command_manager.async_select_program(program)
        self._sync_from_command_manager()
        self.async_set_updated_data(self.data)

    async def async_next_program(self) -> None:
        """Route a next-program request through the command manager."""
        await self.command_manager.async_next_program()
        self._sync_from_command_manager()
        self.async_set_updated_data(self.data)

    async def async_previous_program(self) -> None:
        """Route a previous-program request through the command manager."""
        await self.command_manager.async_previous_program()
        self._sync_from_command_manager()
        self.async_set_updated_data(self.data)

    async def async_lampen_sync(self) -> None:
        """Route Lampen-Sync through the command manager."""
        await self.command_manager.async_lampen_sync()
        self._sync_from_command_manager()
        self.async_set_updated_data(self.data)

    async def async_execute_intent(
        self,
        intent: str,
        *,
        brightness: int | None = None,
        rgb_color: tuple[int, int, int] | None = None,
        color_temperature_kelvin: int | None = None,
        effect: str | None = None,
    ) -> None:
        """Route a semantic intent through the command manager."""
        await self.command_manager.async_execute_intent(
            intent,
            brightness=brightness,
            rgb_color=rgb_color,
            color_temperature_kelvin=color_temperature_kelvin,
            effect=effect,
        )
        self._sync_from_command_manager()
        self.async_set_updated_data(self.data)

    async def async_send_raw_command(self, command: str) -> None:
        """Route a developer raw command through the command manager."""
        await self.command_manager.send_command(command)
        self._sync_from_command_manager()
        self.async_set_updated_data(self.data)

    async def async_cancel_power_timer(self) -> None:
        """Cancel the delayed transformer power-off timer."""
        await self.command_manager.async_cancel_power_timer()
        self._sync_from_command_manager()
        self.async_set_updated_data(self.data)

    async def async_turn_transformer_on(self) -> None:
        """Turn the configured transformer actuator on."""
        await self.command_manager.async_turn_transformer_on()
        self._sync_from_command_manager()
        self.async_set_updated_data(self.data)

    async def async_turn_transformer_off(self) -> None:
        """Turn the configured transformer actuator off."""
        await self.command_manager.async_turn_transformer_off()
        self._sync_from_command_manager()
        self.async_set_updated_data(self.data)

    def command_manager_updated(self) -> None:
        """Handle diagnostic updates from the command manager."""
        self._sync_from_command_manager()
        self.async_set_updated_data(self.data)

    def _sync_from_command_manager(self) -> None:
        """Copy command-manager placeholder diagnostics into coordinator data."""
        diagnostics = self.command_manager.diagnostics()
        self.data.gateway_connection = self.tcp_client.connection_state
        self.data.desired_light_state = str(diagnostics["desired_light_state"])
        self.data.optimistic_mode = str(diagnostics["optimistic_mode"])
        optimistic_is_on = diagnostics["optimistic_is_on"]
        self.data.optimistic_is_on = (
            optimistic_is_on if isinstance(optimistic_is_on, bool) else None
        )
        optimistic_brightness = diagnostics["optimistic_brightness"]
        self.data.optimistic_brightness = (
            optimistic_brightness if isinstance(optimistic_brightness, int) else None
        )
        optimistic_rgb_color = diagnostics["optimistic_rgb_color"]
        self.data.optimistic_rgb_color = (
            optimistic_rgb_color
            if isinstance(optimistic_rgb_color, tuple)
            else None
        )
        optimistic_color_temperature = diagnostics[
            "optimistic_color_temperature_kelvin"
        ]
        self.data.optimistic_color_temperature_kelvin = (
            optimistic_color_temperature
            if isinstance(optimistic_color_temperature, int)
            else None
        )
        optimistic_effect = diagnostics["optimistic_effect"]
        self.data.optimistic_effect = (
            optimistic_effect if isinstance(optimistic_effect, str) else None
        )
        active_program = diagnostics["active_light_program"]
        self.data.active_light_program = (
            active_program if isinstance(active_program, str) else None
        )
        self.data.selected_program = self.data.active_light_program
        last_rgb_color = diagnostics["last_rgb_color"]
        self.data.last_rgb_color = (
            last_rgb_color if isinstance(last_rgb_color, tuple) else None
        )
        last_color_temperature = diagnostics["last_color_temperature_kelvin"]
        self.data.last_color_temperature_kelvin = (
            last_color_temperature
            if isinstance(last_color_temperature, int)
            else None
        )
        last_brightness = diagnostics["last_brightness"]
        self.data.last_brightness = (
            last_brightness if isinstance(last_brightness, int) else None
        )
        last_mode = diagnostics["last_mode"]
        self.data.last_mode = last_mode if isinstance(last_mode, str) else None
        self.data.rgb_join_state = str(diagnostics["rgb_join_state"])
        self.data.queue_length = int(diagnostics["queue_length"])
        self.data.protocol_debug_logging = bool(
            diagnostics["protocol_debug_logging"]
        )
        last_command = diagnostics["last_rs485_command"]
        self.data.last_rs485_command = (
            last_command if isinstance(last_command, str) else None
        )
        last_response = diagnostics["last_response"]
        self.data.last_response = last_response if isinstance(last_response, str) else None
        last_error = diagnostics["last_error"]
        self.data.last_error = last_error if isinstance(last_error, str) else None
        self.data.remaining_power_off_countdown = int(
            diagnostics["remaining_power_off_countdown"]
        )
        self.data.delayed_power_off_timer_active = bool(
            diagnostics["delayed_power_off_timer_active"]
        )
        self.data.power_state = str(diagnostics["power_state"])
        self.data.power_state_source = str(diagnostics["power_state_source"])
        transformer_powered = diagnostics["transformer_powered"]
        self.data.transformer_powered = (
            transformer_powered if isinstance(transformer_powered, bool) else None
        )
        lamp_is_on = diagnostics["lamp_is_on"]
        self.data.lamp_is_on = lamp_is_on if isinstance(lamp_is_on, bool) else None
        if (
            self.data.lamp_is_on is False
            and self.data.optimistic_is_on is not True
        ):
            self.data.optimistic_is_on = False
        last_lamp_command = diagnostics["last_lamp_command"]
        self.data.last_lamp_command = (
            last_lamp_command if isinstance(last_lamp_command, str) else None
        )
        self.data.startup_sequence_state = str(diagnostics["startup_sequence_state"])
        self.data.startup_sequence_running = bool(
            diagnostics["startup_sequence_running"]
        )
        self.data.startup_sequence_task_active = bool(
            diagnostics["startup_sequence_task_active"]
        )
        self.data.init_phase = str(diagnostics["init_phase"])
        self.data.init_command = str(diagnostics["init_command"])
        self.data.init_command_history = str(diagnostics["init_command_history"])
        self.data.auto_sync_status = str(diagnostics["auto_sync_status"])
        self.data.power_on_countdown = int(diagnostics["power_on_countdown"])
