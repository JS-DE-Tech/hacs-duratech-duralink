"""Central command manager for Duratech DuraLink."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
import logging
import math
import time

from .const import (
    DEFAULT_LAMP_WAKEUP_DELAY_MS,
    DEFAULT_INTER_COMMAND_DELAY_MS,
    COLOR_TEMPERATURE_STEP_KELVIN,
    DEFAULT_COLOR_TEMPERATURE_KELVIN,
    DEFAULT_RGB_JOIN_TIMEOUT_MS,
    DEFAULT_STARTUP_PRESET_COMMAND,
    DEFAULT_STARTUP_PRESET_MODE,
    EFFECT_PS01,
    EFFECT_PS02,
    EFFECT_PS03,
    EFFECT_PS04,
    EFFECT_PS05,
    EFFECT_PS06,
    EFFECT_PS07,
    EFFECT_PS08,
    EFFECT_PS09,
    EFFECT_PS10,
    EFFECT_PS11,
    EFFECT_PS12,
    EFFECT_PS13,
    EFFECT_PS14,
    InitPhase,
    LIGHT_EFFECT_OPTIONS,
    MAIN_PROGRAM_OPTIONS,
    MAX_COLOR_TEMPERATURE_KELVIN,
    MIN_COLOR_TEMPERATURE_KELVIN,
    POWER_STATE_SOURCE_OPTIMISTIC,
    POWER_STATE_SOURCE_UNKNOWN,
    PROGRAM_RGB,
    PowerState,
    StartupPresetMode,
    StartupSequenceState,
)
from .protocol import (
    COMMAND_AUTO_SYNC,
    COMMAND_PL0,
    COMMAND_PL1,
    COMMAND_PC255255255,
    COMMAND_PD075,
    COMMAND_PROGRAM_DOWN,
    COMMAND_PROGRAM_UP,
    COMMAND_PS01,
    COMMAND_PS02,
    COMMAND_PS03,
    COMMAND_PS04,
    COMMAND_PS05,
    COMMAND_PS06,
    COMMAND_PS07,
    COMMAND_PS08,
    COMMAND_PS09,
    COMMAND_PS10,
    COMMAND_PS11,
    COMMAND_PS12,
    COMMAND_PS13,
    COMMAND_PS14,
    DuratechDuralinkProtocol,
)
from .power_controller import DuratechDuralinkPowerController
from .tcp_client import DuratechDuralinkTcpClient

_LOGGER = logging.getLogger(__name__)

EFFECT_COMMANDS: dict[str, str] = {
    EFFECT_PS01: COMMAND_PS01,
    EFFECT_PS02: COMMAND_PS02,
    EFFECT_PS03: COMMAND_PS03,
    EFFECT_PS04: COMMAND_PS04,
    EFFECT_PS05: COMMAND_PS05,
    EFFECT_PS06: COMMAND_PS06,
    EFFECT_PS07: COMMAND_PS07,
    EFFECT_PS08: COMMAND_PS08,
    EFFECT_PS09: COMMAND_PS09,
    EFFECT_PS10: COMMAND_PS10,
    EFFECT_PS11: COMMAND_PS11,
    EFFECT_PS12: COMMAND_PS12,
    EFFECT_PS13: COMMAND_PS13,
    EFFECT_PS14: COMMAND_PS14,
}
COMMAND_EFFECTS: dict[str, str] = {command: effect for effect, command in EFFECT_COMMANDS.items()}
COLOR_PROGRAM_EFFECT_COMMANDS: dict[str, str] = {
    effect: command
    for effect, command in EFFECT_COMMANDS.items()
    if command.startswith("PS")
}
COLOR_PROGRAM_COMMAND_EFFECTS: dict[str, str] = {
    command: effect for effect, command in COLOR_PROGRAM_EFFECT_COMMANDS.items()
}

COLOR_PROGRAM_COMMANDS: tuple[str, ...] = (
    COMMAND_PS01,
    COMMAND_PS02,
    COMMAND_PS03,
    COMMAND_PS04,
    COMMAND_PS05,
    COMMAND_PS06,
    COMMAND_PS07,
    COMMAND_PS08,
    COMMAND_PS09,
    COMMAND_PS10,
    COMMAND_PS11,
    COMMAND_PS12,
    COMMAND_PS13,
    COMMAND_PS14,
)


class LightingMode(StrEnum):
    """Active desired lighting mode."""

    UNKNOWN = "unknown"
    RGB = "rgb"
    COLOR_TEMP = "color_temp"
    WHITE = "white"
    PROGRAM = "program"


class RGBJoinState(StrEnum):
    """RGB join/coalescing lifecycle state."""

    IDLE = "idle"
    PENDING = "pending"
    SENT = "sent"
    CANCELLED = "cancelled"


class _IntentKind(StrEnum):
    """Semantic command kinds queued by the command manager."""

    TURN_ON = "turn_on"
    TURN_OFF = "turn_off"
    SET_BRIGHTNESS = "set_brightness"
    SET_RGB = "set_rgb"
    SET_EFFECT = "set_effect"
    NEXT_PROGRAM = "next_program"
    PREVIOUS_PROGRAM = "previous_program"
    RAW_COMMAND = "raw_command"
    AUTO_SYNC = "auto_sync"


_STALE_VISUAL_INTENTS: set[_IntentKind] = {
    _IntentKind.TURN_ON,
    _IntentKind.SET_BRIGHTNESS,
    _IntentKind.SET_RGB,
    _IntentKind.SET_EFFECT,
    _IntentKind.NEXT_PROGRAM,
    _IntentKind.PREVIOUS_PROGRAM,
}


@dataclass(slots=True)
class DesiredLightState:
    """Desired light state maintained independently from physical state."""

    is_on: bool | None = None
    mode: LightingMode = LightingMode.UNKNOWN
    brightness: int | None = None
    rgb_color: tuple[int, int, int] | None = None
    color_temperature_kelvin: int | None = None
    effect: str | None = None
    active_light_program: str | None = None
    last_update: datetime | None = None

    def mark_updated(self) -> None:
        """Record a desired-state update timestamp."""
        self.last_update = datetime.now(UTC)

    def as_diagnostic(self) -> str:
        """Return a compact diagnostic representation."""
        if self.is_on is None:
            return "unknown"
        if not self.is_on:
            return "off"
        parts = ["on", f"mode={self.mode.value}"]
        if self.brightness is not None:
            parts.append(f"brightness={self.brightness}")
        if self.rgb_color is not None:
            parts.append(f"rgb={self.rgb_color}")
        if self.color_temperature_kelvin is not None:
            parts.append(f"color_temp={self.color_temperature_kelvin}")
        if self.effect is not None:
            parts.append(f"effect={self.effect}")
        if self.active_light_program is not None:
            parts.append(f"program={self.active_light_program}")
        if self.last_update is not None:
            parts.append(f"updated={self.last_update.isoformat()}")
        return ", ".join(parts)


@dataclass(slots=True)
class _QueuedIntent:
    """One serialized semantic command request."""

    kind: _IntentKind
    future: asyncio.Future[None] = field(repr=False)
    brightness: int | None = None
    rgb_color: tuple[int, int, int] | None = None
    color_temperature_kelvin: int | None = None
    effect: str | None = None
    raw_command: str | None = None


class DuratechDuralinkCommandManager:
    """Central command gateway for entity, service, and future KNX commands."""

    def __init__(
        self,
        tcp_client: DuratechDuralinkTcpClient,
        protocol: DuratechDuralinkProtocol,
        power_controller: DuratechDuralinkPowerController,
        power_on_delay: int,
        power_off_delay: int,
        rgb_join_timeout_ms: int = DEFAULT_RGB_JOIN_TIMEOUT_MS,
        lamp_wakeup_delay_ms: int = DEFAULT_LAMP_WAKEUP_DELAY_MS,
        inter_command_delay_ms: int = DEFAULT_INTER_COMMAND_DELAY_MS,
        startup_preset_mode: str = DEFAULT_STARTUP_PRESET_MODE,
        startup_preset_command: str = DEFAULT_STARTUP_PRESET_COMMAND,
        protocol_debug_logging: bool = False,
        stored_light_state: dict[str, object] | None = None,
    ) -> None:
        """Initialize the command manager."""
        self.tcp_client = tcp_client
        self.protocol = protocol
        self.power_controller = power_controller
        self.power_on_delay = power_on_delay
        self.power_off_delay = power_off_delay
        self.rgb_join_timeout_ms = max(0, int(rgb_join_timeout_ms))
        self.lamp_wakeup_delay_ms = max(0, int(lamp_wakeup_delay_ms))
        self.inter_command_delay_ms = max(0, int(inter_command_delay_ms))
        self.startup_preset_mode = self._normalize_startup_preset_mode(
            startup_preset_mode
        )
        self.startup_preset_command = self._normalize_startup_preset_command(
            startup_preset_command
        )
        self.protocol_debug_logging = protocol_debug_logging

        self.desired_state = DesiredLightState()
        self.last_rgb_color: tuple[int, int, int] | None = None
        self.last_color_temperature_kelvin: int | None = None
        self.last_brightness: int | None = None
        self.last_mode = LightingMode.UNKNOWN
        self.active_light_program: str | None = None
        self._persist_callback: (
            Callable[[dict[str, object]], Awaitable[None]] | None
        ) = None
        self._last_persisted_payload: dict[str, object] = {}
        self.queue_length = 0
        self.last_rs485_command: str | None = None
        self.last_response: str | None = None
        self.last_error: str | None = None
        self.remaining_power_off_countdown = 0
        self.delayed_power_off_timer_active = False
        self.transformer_powered: bool | None = None
        self.lamp_is_on: bool | None = None
        self.last_lamp_command: str | None = None
        self.power_state = PowerState.UNKNOWN.value
        self.power_state_source = POWER_STATE_SOURCE_UNKNOWN
        self.startup_sequence_state = StartupSequenceState.IDLE.value
        self.startup_sequence_running = False
        self.startup_sequence_task: asyncio.Task[list[str]] | None = None
        self.init_phase = InitPhase.IDLE.value
        self.init_command = "idle"
        self.init_command_history: list[str] = []
        self.power_on_countdown = 0
        self.auto_sync_status = "Bereit"
        self.rgb_join_state = RGBJoinState.IDLE.value

        self._queue: asyncio.Queue[_QueuedIntent] = asyncio.Queue()
        self._worker_task: asyncio.Task[None] | None = None
        self._stopping = False
        self._power_off_task: asyncio.Task[None] | None = None
        self._power_off_deadline: float | None = None
        self._auto_sync_task: asyncio.Task[None] | None = None
        self._auto_sync_lock_deadline: float | None = None
        self._rgb_join_task: asyncio.Task[None] | None = None
        self._pending_rgb_color: tuple[int, int, int] | None = None
        self._transformer_init_required = False
        self._update_callback: Callable[[], None] | None = None
        self._restore_persisted_light_state(stored_light_state or {})
        self._last_persisted_payload = self._persistent_light_state_payload()

    def set_update_callback(self, callback: Callable[[], None]) -> None:
        """Set a callback used to notify coordinator entities of state changes."""
        self._update_callback = callback

    def set_persist_callback(
        self,
        callback: Callable[[dict[str, object]], Awaitable[None]],
    ) -> None:
        """Set callback used to persist successful light state."""
        self._persist_callback = callback

    async def async_turn_on(
        self,
        *,
        brightness: int | None = None,
        rgb_color: tuple[int, int, int] | None = None,
        color_temperature_kelvin: int | None = None,
        effect: str | None = None,
    ) -> None:
        """Turn on and optionally update requested visual state in one intent."""
        self._reject_if_auto_sync_active(_IntentKind.TURN_ON.value)
        if effect is not None and effect not in LIGHT_EFFECT_OPTIONS:
            raise ValueError(f"Unsupported DuraLink effect: {effect}")

        self.last_error = None
        self._apply_optimistic_light_on()
        self._notify_update()

        if rgb_color is not None:
            await self._schedule_rgb_join(rgb_color)
            return
        if color_temperature_kelvin is not None:
            color_temperature_kelvin = self._normalize_color_temperature_kelvin(
                color_temperature_kelvin
            )
            self._apply_optimistic_color_temperature(color_temperature_kelvin)
            brightness = None
        elif effect is not None:
            await self._cancel_rgb_join("effect selected")
            brightness = None

        await self._enqueue_intent(
            _IntentKind.TURN_ON,
            brightness=brightness,
            rgb_color=rgb_color,
            color_temperature_kelvin=color_temperature_kelvin,
            effect=effect,
        )

    async def async_turn_off(self) -> None:
        """Turn the light off through the mandatory PL0 path."""
        self._reject_if_auto_sync_active(_IntentKind.TURN_OFF.value)
        self.last_error = None
        self._apply_optimistic_light_off()
        self._notify_update()

        # Mandatory Light OFF invariant:
        # - PL0 is always sent immediately through the CommandManager.
        # - PL0 is not coalesced away and does not wait behind stale queued
        #   brightness/RGB/effect commands.
        # - If a power controller exists, delayed power-off starts after PL0.
        #
        await self._cancel_rgb_join("light off")
        await self._enqueue_priority_off_intent()

    async def async_set_brightness(self, brightness: int) -> None:
        """Set desired brightness and transmit through the manager."""
        self._reject_if_auto_sync_active(_IntentKind.SET_BRIGHTNESS.value)
        self.last_error = None
        self._notify_update()
        if self.startup_sequence_running:
            return
        await self._enqueue_intent(_IntentKind.SET_BRIGHTNESS, brightness=brightness)

    async def async_set_rgb(self, rgb_color: tuple[int, int, int]) -> None:
        """Set desired RGB color and transmit through the manager."""
        self._reject_if_auto_sync_active(_IntentKind.SET_RGB.value)
        self.last_error = None
        self._notify_update()
        self._apply_optimistic_rgb(rgb_color)
        if self.startup_sequence_running:
            return
        await self._schedule_rgb_join(rgb_color, update_desired=False)

    async def async_set_effect(self, effect: str) -> None:
        """Set desired effect and transmit through the manager."""
        self._reject_if_auto_sync_active(_IntentKind.SET_EFFECT.value)
        if effect == PROGRAM_RGB:
            await self.async_select_program(effect)
            return
        if effect not in LIGHT_EFFECT_OPTIONS:
            raise ValueError(f"Unsupported DuraLink effect: {effect}")

        self.last_error = None
        self._notify_update()
        if self.startup_sequence_running:
            return
        await self._cancel_rgb_join("effect selected")
        await self._enqueue_intent(_IntentKind.SET_EFFECT, effect=effect)

    async def async_select_program(self, program: str) -> None:
        """Select an RGB/PS main light program."""
        self._reject_if_auto_sync_active(_IntentKind.SET_EFFECT.value)
        if program not in MAIN_PROGRAM_OPTIONS:
            raise ValueError(f"Unsupported DuraLink program: {program}")

        self.last_error = None
        self._notify_update()
        if self.startup_sequence_running:
            return
        await self._cancel_rgb_join("program selected")
        rgb_color = self._last_rgb_or_default() if program == PROGRAM_RGB else None
        await self._enqueue_intent(
            _IntentKind.SET_EFFECT,
            effect=program,
            rgb_color=rgb_color,
        )

    async def async_next_program(self) -> None:
        """Select the next program through semantic intent."""
        self._reject_if_auto_sync_active(_IntentKind.NEXT_PROGRAM.value)
        self.last_error = None
        self._notify_update()
        if self.startup_sequence_running:
            return
        await self._cancel_rgb_join("next program selected")
        await self._enqueue_intent(_IntentKind.NEXT_PROGRAM)

    async def async_previous_program(self) -> None:
        """Select the previous program through semantic intent."""
        self._reject_if_auto_sync_active(_IntentKind.PREVIOUS_PROGRAM.value)
        self.last_error = None
        self._notify_update()
        if self.startup_sequence_running:
            return
        await self._cancel_rgb_join("previous program selected")
        await self._enqueue_intent(_IntentKind.PREVIOUS_PROGRAM)

    async def async_lampen_sync(self) -> None:
        """Run the DuraLink lamp synchronization procedure."""
        self._debug(
            "DuraLink Lampen-Sync requested desired=%s queue=%s power_state=%s",
            self.desired_state.as_diagnostic(),
            self.queue_length,
            self.power_state,
        )
        self.last_error = None
        self._notify_update()
        if self._auto_sync_active():
            message = self._auto_sync_block_message()
            self.last_error = message
            _LOGGER.warning(message)
            self._debug(
                "DuraLink blocked/deferred command during Lampen-Sync command=%s status=%s queue=%s",
                COMMAND_AUTO_SYNC,
                self.auto_sync_status,
                self.queue_length,
            )
            self._notify_update()
            raise RuntimeError(message)
        await self._cancel_rgb_join("lampen sync")
        await self._enqueue_intent(_IntentKind.AUTO_SYNC)

    async def async_execute_intent(
        self,
        intent: str,
        *,
        brightness: int | None = None,
        rgb_color: tuple[int, int, int] | None = None,
        color_temperature_kelvin: int | None = None,
        effect: str | None = None,
    ) -> None:
        """Execute a semantic intent without exposing RS485 details."""
        intent_kind = _IntentKind(intent)
        if intent_kind is _IntentKind.TURN_ON:
            await self.async_turn_on(
                brightness=brightness,
                rgb_color=rgb_color,
                color_temperature_kelvin=color_temperature_kelvin,
                effect=effect,
            )
            return
        if intent_kind is _IntentKind.TURN_OFF:
            await self.async_turn_off()
            return
        if intent_kind is _IntentKind.SET_BRIGHTNESS and brightness is not None:
            await self.async_set_brightness(brightness)
            return
        if intent_kind is _IntentKind.SET_RGB and rgb_color is not None:
            await self.async_set_rgb(rgb_color)
            return
        if intent_kind is _IntentKind.SET_EFFECT and effect is not None:
            await self.async_set_effect(effect)
            return
        if intent_kind is _IntentKind.NEXT_PROGRAM:
            await self.async_next_program()
            return
        if intent_kind is _IntentKind.PREVIOUS_PROGRAM:
            await self.async_previous_program()
            return
        if intent_kind is _IntentKind.AUTO_SYNC:
            await self.async_lampen_sync()
            return
        raise ValueError(f"Unsupported or incomplete DuraLink intent: {intent}")

    async def send_command(self, command: str) -> None:
        """Send a raw developer/diagnostic command through the manager."""
        if command != COMMAND_AUTO_SYNC:
            self._reject_if_auto_sync_active(command)
        if command == COMMAND_PL0:
            await self.async_turn_off()
            return
        if command == COMMAND_AUTO_SYNC:
            await self.async_lampen_sync()
            return
        await self._enqueue_intent(_IntentKind.RAW_COMMAND, raw_command=command)

    async def async_cancel_power_timer(self) -> None:
        """Cancel the delayed power-off timer."""
        await self._cancel_power_off_timer()

    async def async_update_transformer_power_state(
        self,
        transformer_powered: bool | None,
        source: str,
        *,
        cancel_power_off_timer: bool = False,
    ) -> None:
        """Apply an externally observed transformer power state."""
        previous_powered = self.transformer_powered
        self.power_state_source = source
        if cancel_power_off_timer:
            await self._cancel_power_off_timer()

        if transformer_powered is None:
            self.transformer_powered = None
            if not self.delayed_power_off_timer_active:
                self.power_state = PowerState.UNKNOWN.value
            self._debug(
                "DuraLink transformer power state unknown source=%s queue=%s",
                self.power_state_source,
                self.queue_length,
            )
            self._notify_update()
            return

        self.transformer_powered = transformer_powered
        if transformer_powered and previous_powered is False:
            self._transformer_init_required = True
            self._debug(
                "DuraLink transformer ON observed after OFF; mandatory startup init required source=%s power_state=%s queue=%s",
                self.power_state_source,
                self.power_state,
                self.queue_length,
            )
        if not (transformer_powered and self.delayed_power_off_timer_active):
            self.power_state = (
                PowerState.ON.value if transformer_powered else PowerState.OFF.value
            )
        if not transformer_powered:
            self._transformer_init_required = True
            self.delayed_power_off_timer_active = False
            self.remaining_power_off_countdown = 0
            self._power_off_deadline = None
        self._debug(
            "DuraLink transformer power state updated powered=%s source=%s power_state=%s queue=%s",
            self.transformer_powered,
            self.power_state_source,
            self.power_state,
            self.queue_length,
        )
        self._notify_update()

    async def async_turn_transformer_on(self) -> None:
        """Turn the configured transformer actuator on."""
        if not self.power_controller.exists:
            return
        await self._cancel_power_off_timer()
        self.power_state = PowerState.POWERING_ON.value
        self._notify_update()
        try:
            await self.power_controller.async_turn_on()
        except Exception as err:
            self.last_error = str(err)
            self.power_state = PowerState.ERROR.value
            self._notify_update()
            raise
        self.transformer_powered = True
        self.power_state = PowerState.ON.value
        self.power_state_source = self._power_controller_write_source()
        self._notify_update()

    async def async_turn_transformer_off(self) -> None:
        """Turn the configured transformer actuator off."""
        if not self.power_controller.exists:
            return
        await self._cancel_power_off_timer()
        self.power_state = PowerState.POWERING_OFF.value
        self._notify_update()
        try:
            await self.power_controller.async_turn_off()
        except Exception as err:
            self.last_error = str(err)
            self.power_state = PowerState.ERROR.value
            self._notify_update()
            raise
        self.transformer_powered = False
        self.power_state = PowerState.OFF.value
        self.power_state_source = self._power_controller_write_source()
        self._notify_update()

    async def async_shutdown(self) -> None:
        """Cancel timers and worker tasks before integration unload."""
        self._stopping = True
        await self._cancel_rgb_join("shutdown")
        await self._cancel_power_off_timer()
        await self._cancel_startup_sequence_task()
        await self._cancel_auto_sync_task()
        while not self._queue.empty():
            item = self._queue.get_nowait()
            if not item.future.done():
                item.future.cancel()
            self._queue.task_done()
        self._sync_queue_length()
        if self._worker_task is not None:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
            self._worker_task = None
        self._notify_update()

    async def _schedule_rgb_join(
        self,
        rgb_color: tuple[int, int, int],
        *,
        update_desired: bool = True,
    ) -> None:
        """Schedule one coalesced RGB command after the join timeout."""
        if update_desired:
            self._apply_optimistic_rgb(rgb_color)

        rgb_color = self._clamp_rgb(rgb_color)
        replaced = self._rgb_join_task is not None and not self._rgb_join_task.done()
        await self._cancel_rgb_join("RGB join updated", mark_cancelled=False)
        self._pending_rgb_color = rgb_color
        self.rgb_join_state = RGBJoinState.PENDING.value
        self._debug(
            "DuraLink RGB join %s rgb=%s timeout_ms=%s desired=%s queue=%s power_state=%s",
            "updated/replaced" if replaced else "scheduled",
            rgb_color,
            self.rgb_join_timeout_ms,
            self.desired_state.as_diagnostic(),
            self.queue_length,
            self.power_state,
        )
        self._rgb_join_task = asyncio.create_task(self._run_rgb_join_task())
        self._notify_update()

    async def _cancel_rgb_join(
        self,
        reason: str,
        *,
        mark_cancelled: bool = True,
    ) -> None:
        """Cancel any pending RGB join task and queued RGB join intent."""
        task = self._rgb_join_task
        had_pending_task = task is not None and not task.done()
        if had_pending_task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._rgb_join_task = None

        dropped_queued = self._drop_pending_rgb_queue_items()
        if self._pending_rgb_color is not None or had_pending_task or dropped_queued:
            self._debug(
                "DuraLink RGB join cancelled reason=%s pending_rgb=%s dropped_queued=%s desired=%s queue=%s power_state=%s",
                reason,
                self._pending_rgb_color,
                dropped_queued,
                self.desired_state.as_diagnostic(),
                self.queue_length,
                self.power_state,
            )
            self._pending_rgb_color = None
            if mark_cancelled:
                self.rgb_join_state = RGBJoinState.CANCELLED.value
            self._notify_update()

    def _drop_pending_rgb_queue_items(self) -> bool:
        """Drop queued RGB join sends that have not started processing."""
        if self._queue.empty():
            return False

        dropped = False
        retained: list[_QueuedIntent] = []
        while not self._queue.empty():
            item = self._queue.get_nowait()
            if item.kind is _IntentKind.SET_RGB:
                dropped = True
                if not item.future.done():
                    item.future.set_result(None)
            else:
                retained.append(item)
            self._queue.task_done()

        for item in retained:
            self._queue.put_nowait(item)
        if dropped:
            self._sync_queue_length()
        return dropped

    async def _run_rgb_join_task(self) -> None:
        """Wait for RGB quiet period and enqueue the latest RGB command."""
        try:
            if self.rgb_join_timeout_ms > 0:
                await asyncio.sleep(self.rgb_join_timeout_ms / 1000)
            rgb_color = self._pending_rgb_color
            if rgb_color is None:
                self.rgb_join_state = RGBJoinState.IDLE.value
                self._notify_update()
                return
            command = self._rgb_to_command(rgb_color)
            self._debug(
                "DuraLink RGB join sending rgb=%s final_rgb_command=%s desired=%s queue=%s power_state=%s",
                rgb_color,
                command,
                self.desired_state.as_diagnostic(),
                self.queue_length,
                self.power_state,
            )
            await self._enqueue_intent(_IntentKind.SET_RGB, rgb_color=rgb_color)
        except asyncio.CancelledError:
            raise
        finally:
            if self._rgb_join_task is asyncio.current_task():
                self._rgb_join_task = None

    async def _enqueue_intent(
        self,
        kind: _IntentKind,
        *,
        brightness: int | None = None,
        rgb_color: tuple[int, int, int] | None = None,
        color_temperature_kelvin: int | None = None,
        effect: str | None = None,
        raw_command: str | None = None,
    ) -> None:
        """Enqueue one semantic intent and wait for processing."""
        self._ensure_worker()
        loop = asyncio.get_running_loop()
        future: asyncio.Future[None] = loop.create_future()
        await self._queue.put(
            _QueuedIntent(
                kind=kind,
                future=future,
                brightness=brightness,
                rgb_color=rgb_color,
                color_temperature_kelvin=color_temperature_kelvin,
                effect=effect,
                raw_command=raw_command,
            )
        )
        self._sync_queue_length()
        self._notify_update()
        await future

    async def _enqueue_priority_off_intent(self) -> None:
        """Queue light-off ahead of retained work and drop stale visuals."""
        self._ensure_worker()
        loop = asyncio.get_running_loop()
        future: asyncio.Future[None] = loop.create_future()
        retained: list[_QueuedIntent] = []
        while not self._queue.empty():
            item = self._queue.get_nowait()
            if item.kind in _STALE_VISUAL_INTENTS:
                if not item.future.done():
                    item.future.set_result(None)
            else:
                retained.append(item)
            self._queue.task_done()

        self._queue.put_nowait(_QueuedIntent(kind=_IntentKind.TURN_OFF, future=future))
        for item in retained:
            self._queue.put_nowait(item)
        self._sync_queue_length()
        self._notify_update()
        await future

    def _ensure_worker(self) -> None:
        """Start the queue worker if needed."""
        if self._worker_task is None or self._worker_task.done():
            self._stopping = False
            self._worker_task = asyncio.create_task(self._run_queue_worker())

    async def _run_queue_worker(self) -> None:
        """Serialize queued semantic intents so TCP sends never overlap."""
        while not self._stopping:
            item = await self._queue.get()
            self._sync_queue_length()
            self._notify_update()
            try:
                await self._process_intent(item)
            except Exception as err:
                if not item.future.done():
                    item.future.set_exception(err)
            else:
                if not item.future.done():
                    item.future.set_result(None)
            finally:
                self._queue.task_done()
                self._sync_queue_length()
                self._notify_update()

    async def _process_intent(self, item: _QueuedIntent) -> None:
        """Translate one semantic intent into the required RS485 command sequence."""
        if self._auto_sync_active():
            self._raise_auto_sync_blocked(item.kind.value)

        if item.kind is _IntentKind.TURN_OFF:
            await self._send_light_off(COMMAND_PL0)
            self._apply_successful_intent(item)
            return
        if item.kind is _IntentKind.TURN_ON:
            await self._send_non_off_sequence(self._commands_for_turn_on(item))
            self._apply_successful_intent(item)
            await self._persist_light_state_if_changed()
            return
        if item.kind is _IntentKind.SET_BRIGHTNESS and item.brightness is not None:
            await self._send_non_off_sequence(
                [self._brightness_to_command(item.brightness)]
            )
            self._apply_successful_intent(item)
            await self._persist_light_state_if_changed()
            return
        if item.kind is _IntentKind.SET_RGB and item.rgb_color is not None:
            await self._send_non_off_sequence([self._rgb_to_command(item.rgb_color)])
            self._apply_successful_intent(item)
            await self._persist_light_state_if_changed()
            self._pending_rgb_color = None
            self.rgb_join_state = RGBJoinState.SENT.value
            self._debug(
                "DuraLink RGB join sent rgb=%s final_rgb_command=%s desired=%s queue=%s power_state=%s",
                item.rgb_color,
                self._rgb_to_command(item.rgb_color),
                self.desired_state.as_diagnostic(),
                self.queue_length,
                self.power_state,
            )
            self._notify_update()
            return
        if item.kind is _IntentKind.SET_EFFECT and item.effect is not None:
            if item.effect == PROGRAM_RGB and item.rgb_color is None:
                item.rgb_color = self._last_rgb_or_default()
            await self._send_non_off_sequence([self._command_for_effect_intent(item)])
            self._apply_successful_intent(item)
            await self._persist_light_state_if_changed()
            return
        if item.kind is _IntentKind.NEXT_PROGRAM:
            item.effect = self._next_program_option()
            if item.effect == PROGRAM_RGB:
                item.rgb_color = self._last_rgb_or_default()
            await self._send_non_off_sequence([self._command_for_effect_intent(item)])
            self._apply_successful_intent(item)
            await self._persist_light_state_if_changed()
            return
        if item.kind is _IntentKind.PREVIOUS_PROGRAM:
            item.effect = self._previous_program_option()
            if item.effect == PROGRAM_RGB:
                item.rgb_color = self._last_rgb_or_default()
            await self._send_non_off_sequence([self._command_for_effect_intent(item)])
            self._apply_successful_intent(item)
            await self._persist_light_state_if_changed()
            return
        if item.kind is _IntentKind.AUTO_SYNC:
            await self._process_auto_sync_intent(item)
            return
        if item.kind is _IntentKind.RAW_COMMAND and item.raw_command is not None:
            await self._send_non_off_sequence(
                [item.raw_command],
                allow_lamp_wakeup=False,
            )

    async def _process_auto_sync_intent(self, item: _QueuedIntent) -> None:
        """Send PsS once, update optimistic PS01 state, and start command lock."""
        if self._auto_sync_active():
            self._raise_auto_sync_blocked(item.kind.value)

        try:
            await self._send_non_off_sequence([COMMAND_AUTO_SYNC])
        except Exception:
            self.auto_sync_status = "Fehler"
            self._debug(
                "DuraLink Lampen-Sync error desired=%s queue=%s power_state=%s",
                self.desired_state.as_diagnostic(),
                self.queue_length,
                self.power_state,
            )
            self._notify_update()
            raise

        self._apply_successful_intent(item)
        await self._persist_light_state_if_changed()
        self._start_auto_sync_lock()

    async def _run_transformer_startup_task(
        self,
        final_commands: list[str],
    ) -> list[str]:
        """Run mandatory transformer init and optional Startup Preset."""
        self._reset_init_command_history()
        self._debug(
            "DuraLink Init started final_commands=%s desired=%s queue=%s power_state=%s",
            final_commands,
            self.desired_state.as_diagnostic(),
            self.queue_length,
            self.power_state,
        )
        self.startup_sequence_running = True
        self.startup_sequence_state = StartupSequenceState.RUNNING.value
        self.init_phase = InitPhase.POWER_ON_DELAY.value
        self.init_command = "waiting_power_on_delay"
        self.power_on_countdown = self.power_on_delay
        self._debug(
            "DuraLink Waiting power_on_delay: %s seconds",
            self.power_on_countdown,
        )
        self._notify_update()
        try:
            await self._wait_power_on_delay()
            self.init_phase = InitPhase.TRANSFORMER_INIT.value
            self._debug("DuraLink entering transformer_init")
            self._notify_update()
            init_commands = await self._execute_transformer_init_sequence()
            self.init_phase = InitPhase.STARTUP_PRESET.value
            self.init_command = "startup_preset"
            self._debug("DuraLink entering startup_preset")
            self._notify_update()
            startup_commands = await self._execute_startup_preset(final_commands)
            self.power_on_countdown = 0
            self._transformer_init_required = False
            self._notify_update()
            return init_commands + startup_commands
        except asyncio.CancelledError:
            self.init_phase = InitPhase.IDLE.value
            self.init_command = "idle"
            self.power_on_countdown = 0
            self.startup_sequence_state = StartupSequenceState.IDLE.value
            self._debug("DuraLink startup cancelled")
            raise
        except Exception:
            self.init_phase = InitPhase.ERROR.value
            self.init_command = "idle"
            self.power_on_countdown = 0
            self.startup_sequence_state = StartupSequenceState.FAILED.value
            self._debug("DuraLink startup failed")
            raise
        finally:
            if self.init_phase != InitPhase.STARTUP_PRESET.value:
                self.startup_sequence_running = False
            self._notify_update()

    async def _cancel_startup_sequence_task(self) -> None:
        """Cancel the startup sequence task if it is active."""
        if (
            self.startup_sequence_task is not None
            and not self.startup_sequence_task.done()
        ):
            self._debug("DuraLink startup cancelled because task was active")
            self.startup_sequence_task.cancel()
            try:
                await self.startup_sequence_task
            except asyncio.CancelledError:
                pass
        self.startup_sequence_running = False
        self.startup_sequence_task = None
        self.startup_sequence_state = StartupSequenceState.IDLE.value
        self.init_phase = InitPhase.IDLE.value
        self.init_command = "idle"
        self.power_on_countdown = 0
        self._notify_update()

    async def _wait_power_on_delay(self) -> None:
        """Wait for transformer boot while exposing a countdown."""
        self.power_on_countdown = max(0, int(self.power_on_delay))
        self._notify_update()
        while self.power_on_countdown > 0:
            self._debug(
                "DuraLink Waiting power_on_delay: %s seconds",
                self.power_on_countdown,
            )
            await asyncio.sleep(1)
            self.power_on_countdown -= 1
            self._notify_update()
        self._debug("DuraLink power_on_delay countdown=0")

    def _commands_for_turn_on(self, item: _QueuedIntent) -> list[str]:
        """Build the Node-RED-compatible command for a turn-on intent."""
        if item.rgb_color is not None:
            return [self._rgb_to_command(item.rgb_color)]
        if item.color_temperature_kelvin is not None:
            return [
                self._color_temperature_to_command(item.color_temperature_kelvin)
            ]
        if item.effect is not None:
            return [EFFECT_COMMANDS[item.effect]]
        if item.brightness is not None:
            return [self._brightness_to_command(item.brightness)]
        return [COMMAND_PL1]

    def _next_program_option(self) -> str:
        """Return the next explicit RGB/PS program option."""
        current_index = self._current_program_index()
        if current_index is None:
            return PROGRAM_RGB
        return MAIN_PROGRAM_OPTIONS[(current_index + 1) % len(MAIN_PROGRAM_OPTIONS)]

    def _previous_program_option(self) -> str:
        """Return the previous explicit RGB/PS program option."""
        current_index = self._current_program_index()
        if current_index is None:
            return COMMAND_EFFECTS[COMMAND_PS14]
        return MAIN_PROGRAM_OPTIONS[(current_index - 1) % len(MAIN_PROGRAM_OPTIONS)]

    def _current_program_index(self) -> int | None:
        """Return the active RGB/PS program index."""
        active_program = self.active_light_program
        if active_program is None:
            active_program = self.desired_state.active_light_program
        if active_program not in MAIN_PROGRAM_OPTIONS:
            return None
        return MAIN_PROGRAM_OPTIONS.index(active_program)

    def _command_for_program_option(self, option: str) -> str:
        """Return explicit RS485 command for a main program option."""
        if option == PROGRAM_RGB:
            return self._rgb_to_command(self._last_rgb_or_default())
        if option in COLOR_PROGRAM_EFFECT_COMMANDS:
            return COLOR_PROGRAM_EFFECT_COMMANDS[option]
        raise ValueError(f"Unsupported DuraLink program: {option}")

    def _command_for_effect_intent(self, item: _QueuedIntent) -> str:
        """Return explicit RS485 command for an effect/program queued intent."""
        if item.effect == PROGRAM_RGB:
            return self._rgb_to_command(item.rgb_color or self._last_rgb_or_default())
        if item.effect in EFFECT_COMMANDS:
            return EFFECT_COMMANDS[item.effect]
        raise ValueError(f"Unsupported DuraLink effect: {item.effect}")

    def _last_rgb_or_default(self) -> tuple[int, int, int]:
        """Return last successful RGB value or protocol-safe white fallback."""
        return self.last_rgb_color or (255, 255, 255)

    def _apply_optimistic_light_on(self) -> None:
        """Expose a pending light-on request before transformer startup finishes."""
        if self.desired_state.is_on is True:
            return
        self.desired_state.is_on = True
        self.desired_state.mark_updated()
        self._debug(
            "DuraLink optimistic light ON requested desired=%s queue=%s power_state=%s init_phase=%s",
            self.desired_state.as_diagnostic(),
            self.queue_length,
            self.power_state,
            self.init_phase,
        )
        self._notify_update()

    def _apply_optimistic_light_off(self) -> None:
        """Expose a pending light-off request immediately while preserving PL0."""
        self.desired_state.is_on = False
        self.desired_state.mark_updated()
        self._debug(
            "DuraLink optimistic light OFF requested desired=%s queue=%s power_state=%s init_phase=%s",
            self.desired_state.as_diagnostic(),
            self.queue_length,
            self.power_state,
            self.init_phase,
        )
        self._notify_update()

    def _apply_optimistic_rgb(self, rgb_color: tuple[int, int, int]) -> None:
        """Apply desired RGB state before the coalesced command is sent."""
        self.desired_state.is_on = True
        self.desired_state.rgb_color = self._clamp_rgb(rgb_color)
        if self.desired_state.effect is not None:
            self._debug(
                "DuraLink RGB cleared effect previous_effect=%s active_mode=%s queue=%s power_state=%s",
                self.desired_state.effect,
                LightingMode.RGB.value,
                self.queue_length,
                self.power_state,
            )
        self.desired_state.effect = None
        self.desired_state.color_temperature_kelvin = None
        self.desired_state.mode = LightingMode.RGB
        self.desired_state.active_light_program = PROGRAM_RGB
        self.active_light_program = PROGRAM_RGB
        self.desired_state.mark_updated()
        self._debug(
            "DuraLink optimistic RGB updated active_mode=%s desired=%s queue=%s power_state=%s",
            self.desired_state.mode.value,
            self.desired_state.as_diagnostic(),
            self.queue_length,
            self.power_state,
        )
        self._notify_update()

    def _apply_optimistic_color_temperature(
        self,
        color_temperature_kelvin: int,
    ) -> None:
        """Apply desired color temperature before the command is sent."""
        color_temperature = self._normalize_color_temperature_kelvin(
            color_temperature_kelvin
        )
        self.desired_state.is_on = True
        self.desired_state.color_temperature_kelvin = color_temperature
        self.desired_state.rgb_color = None
        self.desired_state.effect = None
        self.desired_state.mode = LightingMode.COLOR_TEMP
        self.desired_state.mark_updated()
        self._debug(
            "DuraLink optimistic color temperature updated color_temp=%s desired=%s queue=%s power_state=%s",
            color_temperature,
            self.desired_state.as_diagnostic(),
            self.queue_length,
            self.power_state,
        )
        self._notify_update()

    def _apply_successful_intent(self, item: _QueuedIntent) -> None:
        """Update optimistic Home Assistant state after successful TCP send."""
        if item.kind is _IntentKind.TURN_OFF:
            self.desired_state.is_on = False
        elif item.kind in {
            _IntentKind.TURN_ON,
            _IntentKind.SET_BRIGHTNESS,
            _IntentKind.SET_RGB,
            _IntentKind.SET_EFFECT,
            _IntentKind.NEXT_PROGRAM,
            _IntentKind.PREVIOUS_PROGRAM,
            _IntentKind.AUTO_SYNC,
        }:
            self.desired_state.is_on = True

        if item.brightness is not None:
            self.desired_state.brightness = self._clamp_brightness(item.brightness)
            self.last_brightness = self.desired_state.brightness
        if item.rgb_color is not None:
            self.desired_state.rgb_color = self._clamp_rgb(item.rgb_color)
            if self.desired_state.effect is not None:
                self._debug(
                    "DuraLink RGB cleared effect previous_effect=%s active_mode=%s queue=%s power_state=%s",
                    self.desired_state.effect,
                    LightingMode.RGB.value,
                    self.queue_length,
                    self.power_state,
                )
            self.desired_state.effect = None
            self.desired_state.mode = LightingMode.RGB
            self.desired_state.active_light_program = PROGRAM_RGB
            self.active_light_program = PROGRAM_RGB
            self.last_rgb_color = self.desired_state.rgb_color
            self.last_mode = LightingMode.RGB
            self.desired_state.color_temperature_kelvin = None
        if item.color_temperature_kelvin is not None:
            color_temperature = self._normalize_color_temperature_kelvin(
                item.color_temperature_kelvin
            )
            self.desired_state.color_temperature_kelvin = color_temperature
            self.desired_state.rgb_color = None
            self.desired_state.effect = None
            self.desired_state.mode = LightingMode.COLOR_TEMP
            self.last_color_temperature_kelvin = color_temperature
            self.last_mode = LightingMode.COLOR_TEMP
        if item.effect is not None:
            if item.effect == PROGRAM_RGB:
                self.desired_state.effect = None
                self.desired_state.color_temperature_kelvin = None
                self.desired_state.rgb_color = self._clamp_rgb(
                    item.rgb_color or self._last_rgb_or_default()
                )
                self.desired_state.mode = LightingMode.RGB
                self.desired_state.active_light_program = PROGRAM_RGB
                self.active_light_program = PROGRAM_RGB
                self.last_rgb_color = self.desired_state.rgb_color
                self.last_mode = LightingMode.RGB
                self.desired_state.mark_updated()
                self._debug(
                    "DuraLink optimistic state updated active_mode=%s desired=%s power_state=%s queue=%s",
                    self.desired_state.mode.value,
                    self.desired_state.as_diagnostic(),
                    self.power_state,
                    self.queue_length,
                )
                self._notify_update()
                return
            self.desired_state.effect = item.effect
            self.desired_state.color_temperature_kelvin = None
            effect_command = EFFECT_COMMANDS[item.effect]
            next_mode = LightingMode.PROGRAM
            if self.desired_state.rgb_color is not None:
                self._debug(
                    "DuraLink Program cleared RGB previous_rgb=%s active_mode=%s queue=%s power_state=%s",
                    self.desired_state.rgb_color,
                    next_mode.value,
                    self.queue_length,
                    self.power_state,
                )
            self.desired_state.rgb_color = None
            self.desired_state.mode = next_mode
            self.desired_state.active_light_program = item.effect
            self.active_light_program = item.effect
            self.last_mode = LightingMode.PROGRAM

        if item.kind is _IntentKind.AUTO_SYNC:
            self.desired_state.effect = COMMAND_EFFECTS[COMMAND_PS01]
            self.desired_state.rgb_color = None
            self.desired_state.color_temperature_kelvin = None
            self.desired_state.mode = LightingMode.PROGRAM
            self.desired_state.active_light_program = COMMAND_EFFECTS[COMMAND_PS01]
            self.active_light_program = COMMAND_EFFECTS[COMMAND_PS01]
            self.last_mode = LightingMode.PROGRAM

        self.desired_state.mark_updated()
        self._debug(
            "DuraLink optimistic state updated active_mode=%s desired=%s power_state=%s queue=%s",
            self.desired_state.mode.value,
            self.desired_state.as_diagnostic(),
            self.power_state,
            self.queue_length,
        )
        self._notify_update()

    async def _send_non_off_sequence(
        self,
        commands: list[str],
        *,
        allow_lamp_wakeup: bool = True,
    ) -> None:
        """Apply power logic and send a sequence of non-off RS485 commands."""
        if not commands:
            return
        await self._cancel_power_off_timer()
        startup_commands = await self._ensure_power_for_command(commands)
        final_commands = self._remaining_commands_after_startup(
            commands,
            startup_commands,
        )
        try:
            for command in final_commands:
                if self.init_phase == InitPhase.STARTUP_PRESET.value:
                    self.init_phase = InitPhase.REQUESTED_COMMAND.value
                    self.init_command = InitPhase.REQUESTED_COMMAND.value
                    self._notify_update()
                self._debug("DuraLink Requested command TX: %s", command)
                if command == COMMAND_PL0:
                    await self._send_light_off(command)
                elif allow_lamp_wakeup:
                    await self._send_rs485_with_lamp_wakeup(command)
                else:
                    await self._send_rs485(command)
                if self.init_phase in {
                    InitPhase.STARTUP_PRESET.value,
                    InitPhase.REQUESTED_COMMAND.value,
                }:
                    self._append_init_command_history(command)
        except Exception:
            if self.init_phase in {
                InitPhase.STARTUP_PRESET.value,
                InitPhase.REQUESTED_COMMAND.value,
            }:
                self.init_phase = InitPhase.ERROR.value
                self.init_command = "idle"
                self.power_on_countdown = 0
                self.startup_sequence_running = False
                self.startup_sequence_state = StartupSequenceState.FAILED.value
                self._notify_update()
            raise
        else:
            if self.init_phase in {
                InitPhase.STARTUP_PRESET.value,
                InitPhase.REQUESTED_COMMAND.value,
            }:
                self.init_phase = InitPhase.READY.value
                self.init_command = "done"
                self.power_on_countdown = 0
                self.startup_sequence_running = False
                self.startup_sequence_state = StartupSequenceState.IDLE.value
                self._debug(
                    "DuraLink Init finished history=%s",
                    self._init_command_history_string(),
                )
                self._notify_update()
        # Future queue enhancements can build on the current RGB join and
        # duplicate-command debounce paths without weakening PL0 priority.

    async def _send_light_off(self, command: str) -> None:
        """Send mandatory PL0 immediately and start delayed power-off if needed."""
        self._debug("DuraLink PL0 handling path entered queue=%s", self.queue_length)
        await self._cancel_power_off_timer()
        await self._send_rs485(command)
        if not self.power_controller.exists:
            self.delayed_power_off_timer_active = False
            self.remaining_power_off_countdown = 0
            self.power_state = PowerState.UNKNOWN.value
            self._notify_update()
            return

        self.transformer_powered = True
        self.power_state = PowerState.POWER_OFF_DELAY.value
        self.power_state_source = POWER_STATE_SOURCE_OPTIMISTIC
        self._start_power_off_timer()

    async def _ensure_power_for_command(self, final_commands: list[str]) -> list[str]:
        """Ensure transformer power is on before non-off commands."""
        if not self.power_controller.exists:
            self._debug(
                "DuraLink startup skipped because no power controller exists commands=%s",
                final_commands,
            )
            return []

        if self.transformer_powered is True and not self._transformer_init_required:
            self._debug(
                "DuraLink startup skipped because transformer already initialized commands=%s power_state=%s source=%s",
                final_commands,
                self.power_state,
                self.power_state_source,
            )
            self.power_state = PowerState.ON.value
            self._notify_update()
            return []

        was_powered_before_check = self.transformer_powered
        is_on = await self.power_controller.async_is_on()
        self.power_state_source = self.power_controller.state_source
        self._debug(
            "DuraLink power check before command commands=%s transformer_powered=%s async_is_on=%s source=%s power_state=%s queue=%s",
            final_commands,
            self.transformer_powered,
            is_on,
            self.power_state_source,
            self.power_state,
            self.queue_length,
        )
        if (
            is_on
            and was_powered_before_check is not False
            and not self._transformer_init_required
        ):
            self._debug(
                "DuraLink startup skipped because HA switch is already ON and no prior OFF was observed commands=%s source=%s",
                final_commands,
                self.power_state_source,
            )
            self.transformer_powered = True
            self.power_state = PowerState.ON.value
            self._notify_update()
            return []

        if not self._transformer_init_required:
            self._debug(
                "DuraLink transformer ON requested power_state=%s",
                self.power_state,
            )
        self._transformer_init_required = True
        if is_on is not True:
            self.power_state = PowerState.POWERING_ON.value
            self._notify_update()
            try:
                self._debug(
                    "DuraLink power controller requested ON commands=%s source=%s",
                    final_commands,
                    self.power_state_source,
                )
                await self.power_controller.async_turn_on()
            except Exception as err:
                self.last_error = str(err)
                self.power_state = PowerState.ERROR.value
                self._notify_update()
                raise
            self.transformer_powered = True
            self.power_state = PowerState.ON.value
            self.power_state_source = self._power_controller_write_source()
            self._debug(
                "DuraLink HA switch turned ON power_state=%s source=%s",
                self.power_state,
                self.power_state_source,
            )
            self._notify_update()
        else:
            self.transformer_powered = True
            self.power_state = PowerState.ON.value
            self._debug(
                "DuraLink HA switch is ON after prior OFF; mandatory startup init will run commands=%s source=%s",
                final_commands,
                self.power_state_source,
            )
            self._notify_update()
        self._debug(
            "DuraLink creating startup task commands=%s init_required=%s task_exists=%s",
            final_commands,
            self._transformer_init_required,
            self.startup_sequence_task is not None
            and not self.startup_sequence_task.done(),
        )
        self.startup_sequence_task = asyncio.create_task(
            self._run_transformer_startup_task(final_commands)
        )
        self._debug("DuraLink startup task created")
        try:
            return await self.startup_sequence_task
        finally:
            self.startup_sequence_task = None
            self._notify_update()

    async def _execute_transformer_init_sequence(self) -> list[str]:
        """Send mandatory transformer init after power-on delay."""
        init_commands = [
            COMMAND_PL0,
            COMMAND_PL1,
            COMMAND_PC255255255,
            self._startup_init_brightness_command(),
        ]
        self._debug(
            "DuraLink executing transformer init sequence commands=%s desired=%s queue=%s power_state=%s",
            init_commands,
            self.desired_state.as_diagnostic(),
            self.queue_length,
            self.power_state,
        )
        sent_commands: list[str] = []
        for index, command in enumerate(init_commands):
            self.init_command = command
            self._debug("DuraLink Init TX: %s", command)
            self._notify_update()
            await self._send_rs485(command)
            self._append_init_command_history(command)
            sent_commands.append(command)
            if index < len(init_commands) - 1:
                await self._wait_inter_command_delay()
        await self._wait_inter_command_delay()
        return sent_commands

    async def _execute_startup_preset(self, final_commands: list[str]) -> list[str]:
        """Execute the startup preset after transformer boot delay."""
        commands = self._startup_preset_commands(
            include_brightness=self.last_brightness is None
        )
        if not commands:
            return []
        self._debug(
            "DuraLink executing Startup Preset mode=%s commands=%s final_commands=%s desired=%s queue=%s power_state=%s",
            self.startup_preset_mode,
            commands,
            final_commands,
            self.desired_state.as_diagnostic(),
            self.queue_length,
            self.power_state,
        )
        self._notify_update()
        sent_commands: list[str] = []
        try:
            for index, command in enumerate(commands):
                self.init_command = "startup_preset"
                self._debug("DuraLink Startup preset TX: %s", command)
                self._notify_update()
                await self._send_rs485(command)
                self._append_init_command_history(command)
                self._apply_successful_startup_command(command)
                await self._persist_light_state_if_changed()
                sent_commands.append(command)
                if index < len(commands) - 1:
                    await self._wait_inter_command_delay()
        except Exception:
            self.startup_sequence_state = StartupSequenceState.FAILED.value
            self._notify_update()
            raise
        return sent_commands

    async def _wait_inter_command_delay(self) -> None:
        """Wait between init/startup RS485 commands."""
        if self.inter_command_delay_ms <= 0:
            return
        self._debug(
            "DuraLink Waiting inter_command_delay_ms=%s",
            self.inter_command_delay_ms,
        )
        await asyncio.sleep(self.inter_command_delay_ms / 1000)

    def _startup_preset_commands(self, *, include_brightness: bool = True) -> list[str]:
        """Build Startup Preset commands from configured mode and DesiredState."""
        if self.startup_preset_mode == StartupPresetMode.FIXED_PROGRAM.value:
            if self.startup_preset_command == PROGRAM_RGB:
                return [self._rgb_to_command(self._last_rgb_or_default())]
            return [self.startup_preset_command]

        commands: list[str] = []
        if self.desired_state.mode is LightingMode.RGB and self.desired_state.rgb_color:
            commands.append(self._rgb_to_command(self.desired_state.rgb_color))
        elif self.last_mode is LightingMode.RGB:
            commands.append(self._rgb_to_command(self._last_rgb_or_default()))
        elif (
            self.desired_state.mode is LightingMode.COLOR_TEMP
            and self.desired_state.color_temperature_kelvin is not None
        ):
            commands.append(
                self._color_temperature_to_command(
                    self.desired_state.color_temperature_kelvin
                )
            )
        elif (
            self.last_mode is LightingMode.COLOR_TEMP
            and self.last_color_temperature_kelvin is not None
        ):
            commands.append(
                self._color_temperature_to_command(
                    self.last_color_temperature_kelvin
                )
            )
        elif (
            self.desired_state.mode in {LightingMode.WHITE, LightingMode.PROGRAM}
            and self.desired_state.effect in EFFECT_COMMANDS
        ):
            commands.append(EFFECT_COMMANDS[self.desired_state.effect])
        elif (
            self.last_mode is LightingMode.PROGRAM
            and self.active_light_program in COLOR_PROGRAM_EFFECT_COMMANDS
        ):
            commands.append(COLOR_PROGRAM_EFFECT_COMMANDS[self.active_light_program])

        if not commands:
            commands.append(COMMAND_PS12)

        if include_brightness and self.desired_state.brightness is not None:
            commands.append(self._brightness_to_command(self.desired_state.brightness))
        return commands

    def _startup_init_brightness_command(self) -> str:
        """Return the mandatory init brightness command."""
        if self.last_brightness is None:
            return COMMAND_PD075
        return self._brightness_to_command(self.last_brightness)

    async def _send_rs485_with_lamp_wakeup(self, command: str) -> None:
        """Wake the lamp after PL0 before sending a visual command."""
        if self._lamp_wakeup_required(command):
            self._debug(
                "DuraLink lamp wake-up required before command=%s desired=%s queue=%s power_state=%s",
                command,
                self.desired_state.as_diagnostic(),
                self.queue_length,
                self.power_state,
            )
            self._debug("DuraLink sending PL1 for lamp wake-up")
            await self._send_rs485(COMMAND_PL1)
            if self.lamp_wakeup_delay_ms > 0:
                self._debug(
                    "DuraLink waiting lamp_wakeup_delay=%s ms",
                    self.lamp_wakeup_delay_ms,
                )
                await asyncio.sleep(self.lamp_wakeup_delay_ms / 1000)
            self._debug("DuraLink sending final command=%s", command)
        await self._send_rs485(command)

    def _lamp_wakeup_required(self, command: str) -> bool:
        """Return whether PL1 must be sent before a visual command."""
        return self.last_lamp_command == COMMAND_PL0 and self._is_visual_command(command)

    @staticmethod
    def _is_visual_command(command: str) -> bool:
        """Return whether the command requires the lamp controller to be awake."""
        return (
            command.startswith("PC")
            or command.startswith("PD")
            or command.startswith("PT")
            or command.startswith("PW")
            or command.startswith("PS")
            or command in {COMMAND_AUTO_SYNC, COMMAND_PROGRAM_UP, COMMAND_PROGRAM_DOWN}
        )

    @staticmethod
    def _remaining_commands_after_startup(
        commands: list[str],
        startup_commands: list[str],
    ) -> list[str]:
        """Skip final commands already sent by the Startup Preset."""
        remaining = list(commands)
        for startup_command in startup_commands:
            if remaining and remaining[0] == startup_command:
                remaining.pop(0)
        return remaining

    def _apply_successful_startup_command(self, command: str) -> None:
        """Update DesiredState for an already-sent Startup Preset command."""
        if command in COMMAND_EFFECTS:
            self.desired_state.is_on = True
            self.desired_state.effect = COMMAND_EFFECTS[command]
            self.desired_state.rgb_color = None
            self.desired_state.mode = LightingMode.PROGRAM
            if command in COLOR_PROGRAM_COMMANDS:
                self.active_light_program = COMMAND_EFFECTS[command]
                self.desired_state.active_light_program = self.active_light_program
                self.last_mode = LightingMode.PROGRAM
        elif command.startswith("PC") and len(command) == 11:
            try:
                rgb_color = (
                    int(command[2:5]),
                    int(command[5:8]),
                    int(command[8:11]),
                )
            except ValueError:
                return
            self.desired_state.is_on = True
            self.desired_state.rgb_color = self._clamp_rgb(rgb_color)
            self.desired_state.effect = None
            self.desired_state.mode = LightingMode.RGB
            self.desired_state.active_light_program = PROGRAM_RGB
            self.active_light_program = PROGRAM_RGB
            self.last_rgb_color = self.desired_state.rgb_color
            self.last_mode = LightingMode.RGB
        elif command.startswith("PT") and len(command) == 5:
            try:
                color_temperature = int(command[2:5]) * 100
            except ValueError:
                return
            color_temperature = self._normalize_color_temperature_kelvin(
                color_temperature
            )
            self.desired_state.is_on = True
            self.desired_state.color_temperature_kelvin = color_temperature
            self.desired_state.rgb_color = None
            self.desired_state.effect = None
            self.desired_state.mode = LightingMode.COLOR_TEMP
            self.last_color_temperature_kelvin = color_temperature
            self.last_mode = LightingMode.COLOR_TEMP
        elif command.startswith("PD") and len(command) == 5:
            try:
                percent = max(0, min(100, int(command[2:5])))
            except ValueError:
                return
            self.desired_state.brightness = round(percent * 255 / 100)
            self.last_brightness = self.desired_state.brightness
        else:
            return

        self.desired_state.mark_updated()
        self._debug(
            "DuraLink Startup Preset updated DesiredState command=%s active_mode=%s desired=%s queue=%s power_state=%s",
            command,
            self.desired_state.mode.value,
            self.desired_state.as_diagnostic(),
            self.queue_length,
            self.power_state,
        )
        self._notify_update()

    async def _send_rs485(self, command: str) -> None:
        """Send one RS485 command through the TCP client."""
        if self._auto_sync_active():
            self._raise_auto_sync_blocked(command)

        try:
            await self.tcp_client.async_send_command(command)
        except Exception as err:
            self.last_error = str(err)
            self.power_state = (
                PowerState.ERROR.value
                if self.power_controller.exists
                else self.power_state
            )
            _LOGGER.warning("Failed to send DuraLink command %s: %s", command, err)
            self._notify_update()
            raise

        self.last_rs485_command = command
        self.last_response = None
        self.last_error = None
        if command == COMMAND_PL0:
            self.last_lamp_command = COMMAND_PL0
            self.lamp_is_on = False
        elif command == COMMAND_PL1:
            self.last_lamp_command = COMMAND_PL1
            self.lamp_is_on = True
        self._debug(
            "DuraLink final RS485 command=%s active_mode=%s desired=%s queue=%s power_state=%s",
            command,
            self.desired_state.mode.value,
            self.desired_state.as_diagnostic(),
            self.queue_length,
            self.power_state,
        )
        self._notify_update()

    def _start_auto_sync_lock(self) -> None:
        """Start the fixed Lampen-Sync command lock and visible countdown."""
        if self._auto_sync_task is not None and not self._auto_sync_task.done():
            self._auto_sync_task.cancel()
        self._auto_sync_lock_deadline = time.monotonic() + 45
        self.auto_sync_status = self._auto_sync_running_status(45)
        self._debug(
            "DuraLink Lampen-Sync command lock started status=%s desired=%s queue=%s power_state=%s",
            self.auto_sync_status,
            self.desired_state.as_diagnostic(),
            self.queue_length,
            self.power_state,
        )
        self._notify_update()
        self._auto_sync_task = asyncio.create_task(self._run_auto_sync_countdown())

    async def _run_auto_sync_countdown(self) -> None:
        """Maintain the Lampen-Sync countdown and completion status."""
        try:
            while self._auto_sync_lock_deadline is not None:
                remaining = self._auto_sync_lock_deadline - time.monotonic()
                if remaining <= 0:
                    break
                await asyncio.sleep(min(1, remaining))
                remaining_seconds = math.ceil(
                    max(0, self._auto_sync_lock_deadline - time.monotonic())
                )
                if remaining_seconds > 0:
                    self.auto_sync_status = self._auto_sync_running_status(
                        remaining_seconds
                    )
                    self._notify_update()

            self._auto_sync_lock_deadline = None
            self.auto_sync_status = "Abgeschlossen"
            self._debug(
                "DuraLink Lampen-Sync countdown finished desired=%s queue=%s power_state=%s",
                self.desired_state.as_diagnostic(),
                self.queue_length,
                self.power_state,
            )
            self._notify_update()
            await asyncio.sleep(5)
            self.auto_sync_status = "Bereit"
            self._debug("DuraLink Lampen-Sync status returned to Bereit")
            self._notify_update()
        except asyncio.CancelledError:
            raise
        except Exception as err:
            self.last_error = str(err)
            self.auto_sync_status = "Fehler"
            self._debug("DuraLink Lampen-Sync error=%s", err)
            self._notify_update()
            raise
        finally:
            if self._auto_sync_task is asyncio.current_task():
                self._auto_sync_task = None

    async def _cancel_auto_sync_task(self) -> None:
        """Cancel Lampen-Sync countdown task on unload."""
        if self._auto_sync_task is not None and not self._auto_sync_task.done():
            self._auto_sync_task.cancel()
            try:
                await self._auto_sync_task
            except asyncio.CancelledError:
                pass
        self._auto_sync_task = None

    def _auto_sync_active(self) -> bool:
        """Return whether the fixed Lampen-Sync RS485 lock is active."""
        return (
            self._auto_sync_lock_deadline is not None
            and time.monotonic() < self._auto_sync_lock_deadline
        )

    def _auto_sync_block_message(self) -> str:
        """Return a clear warning for blocked commands during Lampen-Sync."""
        return (
            "DuraLink Lampen-Sync is active; RS485 commands are blocked "
            "during the 45 second synchronization window."
        )

    def _reject_if_auto_sync_active(self, command: str) -> None:
        """Reject public commands while Lampen-Sync is active."""
        if self._auto_sync_active():
            self._raise_auto_sync_blocked(command)

    def _raise_auto_sync_blocked(self, command: str) -> None:
        """Reject a command while Lampen-Sync owns the RS485 bus."""
        message = self._auto_sync_block_message()
        self.last_error = message
        _LOGGER.warning(message)
        self._debug(
            "DuraLink blocked/deferred command during Lampen-Sync command=%s status=%s queue=%s",
            command,
            self.auto_sync_status,
            self.queue_length,
        )
        self._notify_update()
        raise RuntimeError(message)

    @staticmethod
    def _auto_sync_running_status(remaining_seconds: int) -> str:
        """Return the visible Lampen-Sync countdown status."""
        return f"Lampen-Sync aktiv ({remaining_seconds} s)"

    def _start_power_off_timer(self) -> None:
        """Start delayed transformer power-off timer."""
        self.delayed_power_off_timer_active = True
        self._power_off_deadline = time.monotonic() + self.power_off_delay
        self.remaining_power_off_countdown = self.power_off_delay
        self._debug(
            "DuraLink delayed power-off timer started delay=%s queue=%s",
            self.power_off_delay,
            self.queue_length,
        )
        self._power_off_task = asyncio.create_task(self._run_power_off_timer())
        self._notify_update()

    async def _cancel_power_off_timer(self) -> None:
        """Cancel delayed power-off timer if it is active."""
        if self._power_off_task is not None and not self._power_off_task.done():
            self._debug("DuraLink delayed power-off timer cancelled")
            self._power_off_task.cancel()
            try:
                await self._power_off_task
            except asyncio.CancelledError:
                pass
        self._power_off_task = None
        self._power_off_deadline = None
        self.delayed_power_off_timer_active = False
        self.remaining_power_off_countdown = 0
        if self.power_controller.exists and self.transformer_powered:
            self.power_state = PowerState.ON.value
        self._notify_update()

    async def _run_power_off_timer(self) -> None:
        """Run delayed transformer power-off timer."""
        try:
            while self._power_off_deadline is not None:
                remaining = self._power_off_deadline - time.monotonic()
                if remaining <= 0:
                    break
                self.remaining_power_off_countdown = math.ceil(remaining)
                self.power_state = PowerState.POWER_OFF_DELAY.value
                self._notify_update()
                await asyncio.sleep(min(1, remaining))

            self.remaining_power_off_countdown = 0
            self.delayed_power_off_timer_active = False
            self._power_off_deadline = None
            self.power_state = PowerState.POWERING_OFF.value
            self._debug("DuraLink delayed power-off timer expired")
            self._notify_update()
            self._debug("Turning off DuraLink transformer power actuator")
            await self.power_controller.async_turn_off()
            self.transformer_powered = False
            self.power_state = PowerState.OFF.value
            self.power_state_source = self._power_controller_write_source()
            self._notify_update()
        except asyncio.CancelledError:
            raise
        except Exception as err:
            self.last_error = str(err)
            self.power_state = PowerState.ERROR.value
            self.delayed_power_off_timer_active = False
            self.remaining_power_off_countdown = 0
            _LOGGER.warning("Failed delayed DuraLink power-off: %s", err)
            self._notify_update()

    def _power_controller_write_source(self) -> str:
        """Return the diagnostic source after a successful actuator write."""
        source = self.power_controller.state_source
        if source == POWER_STATE_SOURCE_UNKNOWN:
            return POWER_STATE_SOURCE_OPTIMISTIC
        return source

    def _sync_queue_length(self) -> None:
        """Update queue length diagnostics from the asyncio.Queue."""
        self.queue_length = self._queue.qsize()

    def _restore_persisted_light_state(self, state: dict[str, object]) -> None:
        """Restore last usable light state from Home Assistant storage."""
        rgb = state.get("last_rgb")
        if (
            isinstance(rgb, list | tuple)
            and len(rgb) == 3
            and all(isinstance(value, int) for value in rgb)
        ):
            self.last_rgb_color = self._clamp_rgb((rgb[0], rgb[1], rgb[2]))
            self.desired_state.rgb_color = self.last_rgb_color

        brightness = state.get("last_brightness")
        if isinstance(brightness, int):
            self.last_brightness = self._clamp_brightness(brightness)
            self.desired_state.brightness = self.last_brightness

        color_temperature = state.get("last_color_temperature_kelvin")
        if isinstance(color_temperature, int):
            self.last_color_temperature_kelvin = (
                self._normalize_color_temperature_kelvin(color_temperature)
            )

        active_program = state.get("active_light_program")
        if isinstance(active_program, str) and active_program in MAIN_PROGRAM_OPTIONS:
            self.active_light_program = active_program
            self.desired_state.active_light_program = active_program

        mode = state.get("last_mode")
        if mode == LightingMode.RGB.value:
            self.last_mode = LightingMode.RGB
            self.desired_state.mode = LightingMode.RGB
            self.desired_state.effect = None
            self.desired_state.color_temperature_kelvin = None
            self.active_light_program = PROGRAM_RGB
            self.desired_state.active_light_program = PROGRAM_RGB
        elif mode == LightingMode.COLOR_TEMP.value:
            self.last_mode = LightingMode.COLOR_TEMP
            self.desired_state.mode = LightingMode.COLOR_TEMP
            self.desired_state.effect = None
            self.desired_state.color_temperature_kelvin = (
                self.last_color_temperature_kelvin
                or DEFAULT_COLOR_TEMPERATURE_KELVIN
            )
        elif mode == LightingMode.PROGRAM.value:
            self.last_mode = LightingMode.PROGRAM
            self.desired_state.mode = LightingMode.PROGRAM
            if (
                self.active_light_program is not None
                and self.active_light_program in COLOR_PROGRAM_EFFECT_COMMANDS
            ):
                self.desired_state.effect = self.active_light_program

        if (
            self.desired_state.mode is not LightingMode.UNKNOWN
            or self.desired_state.brightness is not None
        ):
            self.desired_state.mark_updated()

    def _persistent_light_state_payload(self) -> dict[str, object]:
        """Return persistable successful light state."""
        payload: dict[str, object] = {
            "last_mode": self.last_mode.value,
        }
        if self.last_rgb_color is not None:
            payload["last_rgb"] = list(self.last_rgb_color)
        if self.last_brightness is not None:
            payload["last_brightness"] = self.last_brightness
        if self.last_color_temperature_kelvin is not None:
            payload["last_color_temperature_kelvin"] = (
                self.last_color_temperature_kelvin
            )
        if self.active_light_program is not None:
            payload["active_light_program"] = self.active_light_program
        return payload

    async def _persist_light_state_if_changed(self) -> None:
        """Persist last usable light state when a successful send changed it."""
        if self._persist_callback is None:
            return
        payload = self._persistent_light_state_payload()
        if payload == self._last_persisted_payload:
            return
        self._last_persisted_payload = dict(payload)
        await self._persist_callback(payload)

    def _reset_init_command_history(self) -> None:
        """Clear transformer init command history at startup sequence begin."""
        self.init_command_history = []
        self._debug(
            "DuraLink Init Command History: %s",
            self._init_command_history_string(),
        )
        self._notify_update()

    def _append_init_command_history(self, command: str) -> None:
        """Append one init/startup/final command to bounded diagnostics history."""
        self.init_command_history.append(command)
        self.init_command_history = self.init_command_history[-10:]
        self._debug(
            "DuraLink Init Command History: %s",
            self._init_command_history_string(),
        )
        self._notify_update()

    def _init_command_history_string(self) -> str:
        """Return comma-separated init command history for diagnostics."""
        return ", ".join(self.init_command_history)

    @staticmethod
    def _brightness_to_command(brightness: int) -> str:
        """Convert Home Assistant brightness 0..255 to PD000..PD100."""
        percent = round(
            DuratechDuralinkCommandManager._clamp_brightness(brightness) * 100 / 255
        )
        return f"PD{percent:03d}"

    @staticmethod
    def _rgb_to_command(rgb_color: tuple[int, int, int]) -> str:
        """Convert RGB tuple to PCrrrgggbbb."""
        red, green, blue = DuratechDuralinkCommandManager._clamp_rgb(rgb_color)
        return f"PC{red:03d}{green:03d}{blue:03d}"

    @staticmethod
    def _color_temperature_to_command(color_temperature_kelvin: int) -> str:
        """Convert Kelvin color temperature to PTxyz."""
        kelvin = DuratechDuralinkCommandManager._normalize_color_temperature_kelvin(
            color_temperature_kelvin
        )
        return f"PT{kelvin // 100:03d}"

    @staticmethod
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

    @staticmethod
    def _normalize_startup_preset_command(command: str) -> str:
        """Return a valid startup preset command."""
        command = str(command).strip()
        if command == PROGRAM_RGB:
            return PROGRAM_RGB
        if command in COMMAND_EFFECTS:
            return command
        return DEFAULT_STARTUP_PRESET_COMMAND

    @staticmethod
    def _normalize_startup_preset_mode(mode: str) -> str:
        """Return a valid startup preset mode."""
        try:
            return StartupPresetMode(str(mode)).value
        except ValueError:
            return DEFAULT_STARTUP_PRESET_MODE

    @staticmethod
    def _clamp_brightness(brightness: int) -> int:
        """Clamp brightness to the Home Assistant 0..255 range."""
        return max(0, min(255, int(brightness)))

    @staticmethod
    def _clamp_rgb(rgb_color: tuple[int, int, int]) -> tuple[int, int, int]:
        """Clamp RGB values to the protocol range."""
        red, green, blue = rgb_color
        return (
            max(0, min(255, int(red))),
            max(0, min(255, int(green))),
            max(0, min(255, int(blue))),
        )

    def _notify_update(self) -> None:
        """Notify coordinator state changed."""
        if self._update_callback is not None:
            self._update_callback()

    def _debug(self, message: str, *args: object) -> None:
        """Log protocol debug details when enabled."""
        if self.protocol_debug_logging:
            _LOGGER.debug(message, *args)

    def diagnostics(self) -> dict[str, object]:
        """Return command-manager diagnostic state."""
        return {
            "desired_light_state": self.desired_state.as_diagnostic(),
            "optimistic_mode": self.desired_state.mode.value,
            "optimistic_is_on": self.desired_state.is_on,
            "optimistic_brightness": self.desired_state.brightness,
            "optimistic_rgb_color": self.desired_state.rgb_color,
            "optimistic_color_temperature_kelvin": (
                self.desired_state.color_temperature_kelvin
            ),
            "optimistic_effect": self.desired_state.effect,
            "active_light_program": self.active_light_program,
            "last_rgb_color": self.last_rgb_color,
            "last_color_temperature_kelvin": self.last_color_temperature_kelvin,
            "last_brightness": self.last_brightness,
            "last_mode": self.last_mode.value,
            "rgb_join_state": self.rgb_join_state,
            "queue_length": self.queue_length,
            "last_rs485_command": self.last_rs485_command,
            "last_response": self.last_response,
            "last_error": self.last_error,
            "remaining_power_off_countdown": self.remaining_power_off_countdown,
            "delayed_power_off_timer_active": self.delayed_power_off_timer_active,
            "transformer_powered": self.transformer_powered,
            "lamp_is_on": self.lamp_is_on,
            "last_lamp_command": self.last_lamp_command,
            "power_state": self.power_state,
            "power_state_source": self.power_state_source,
            "protocol_debug_logging": self.protocol_debug_logging,
            "lamp_wakeup_delay_ms": self.lamp_wakeup_delay_ms,
            "startup_preset_mode": self.startup_preset_mode,
            "startup_preset_command": self.startup_preset_command,
            "inter_command_delay_ms": self.inter_command_delay_ms,
            "startup_sequence_state": self.init_phase,
            "startup_sequence_running": self.startup_sequence_running,
            "startup_sequence_task_active": (
                self.startup_sequence_task is not None
                and not self.startup_sequence_task.done()
            ),
            "init_phase": self.init_phase,
            "init_command": self.init_command,
            "init_command_history": self._init_command_history_string(),
            "auto_sync_status": self.auto_sync_status,
            "power_on_countdown": self.power_on_countdown,
        }
