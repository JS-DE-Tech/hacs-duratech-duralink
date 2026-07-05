"""Focused tests for Duratech DuraLink CommandManager behavior."""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_PATH = ROOT / "custom_components" / "duratech_duralink"


class Platform:
    """Minimal Home Assistant platform constants for import-time tests."""

    LIGHT = "light"
    SELECT = "select"
    BUTTON = "button"
    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"


homeassistant = types.ModuleType("homeassistant")
homeassistant.const = types.ModuleType("homeassistant.const")
homeassistant.const.ATTR_ENTITY_ID = "entity_id"
homeassistant.const.STATE_ON = "on"
homeassistant.const.Platform = Platform
homeassistant.core = types.ModuleType("homeassistant.core")
homeassistant.core.HomeAssistant = object
homeassistant.exceptions = types.ModuleType("homeassistant.exceptions")
homeassistant.exceptions.HomeAssistantError = Exception
sys.modules.setdefault("homeassistant", homeassistant)
sys.modules.setdefault("homeassistant.const", homeassistant.const)
sys.modules.setdefault("homeassistant.core", homeassistant.core)
sys.modules.setdefault("homeassistant.exceptions", homeassistant.exceptions)

custom_components = types.ModuleType("custom_components")
custom_components.__path__ = [str(ROOT / "custom_components")]
sys.modules.setdefault("custom_components", custom_components)
pkg = types.ModuleType("custom_components.duratech_duralink")
pkg.__path__ = [str(PACKAGE_PATH)]
sys.modules.setdefault("custom_components.duratech_duralink", pkg)

from custom_components.duratech_duralink.command_manager import (  # noqa: E402
    COMMAND_EFFECTS,
    DuratechDuralinkCommandManager,
    LightingMode,
)
from custom_components.duratech_duralink.const import (  # noqa: E402
    POWER_STATE_SOURCE_HA_SWITCH_STATE,
    PROGRAM_RGB,
    PowerMode,
    StartupPresetMode,
)
from custom_components.duratech_duralink.power_controller import (  # noqa: E402
    PowerControllerConfig,
)
from custom_components.duratech_duralink.protocol import (  # noqa: E402
    COMMAND_AUTO_SYNC,
    COMMAND_PC255255255,
    COMMAND_PD075,
    COMMAND_PL0,
    COMMAND_PL1,
    COMMAND_PS01,
    COMMAND_PS04,
    COMMAND_PS12,
    COMMAND_PS13,
    COMMAND_PS14,
    DuratechDuralinkProtocol,
)


class FakeTcpClient:
    """Collect RS485 commands instead of sending TCP."""

    def __init__(self) -> None:
        self.commands: list[str] = []

    async def async_send_command(self, command: str) -> None:
        """Record one command."""
        self.commands.append(command)
        await asyncio.sleep(0)


class BlockingTcpClient(FakeTcpClient):
    """TCP fake that blocks a send until the test releases it."""

    def __init__(self) -> None:
        super().__init__()
        self.send_started = asyncio.Event()
        self.release_send = asyncio.Event()

    async def async_send_command(self, command: str) -> None:
        """Record one command and pause before success is reported."""
        self.commands.append(command)
        self.send_started.set()
        await self.release_send.wait()
        await asyncio.sleep(0)


class FakePowerController:
    """Small HA switch style power controller fake."""

    exists = True
    state_source = POWER_STATE_SOURCE_HA_SWITCH_STATE

    def __init__(self, *, state: bool = False) -> None:
        self.state = state
        self.turn_on_count = 0
        self.turn_off_count = 0
        self.manager: DuratechDuralinkCommandManager | None = None
        self.config = PowerControllerConfig(
            mode=PowerMode.HOME_ASSISTANT_ENTITY,
            entity_id="switch.pool",
        )

    async def async_is_on(self) -> bool:
        """Return fake actuator state."""
        return self.state

    async def async_turn_on(self) -> None:
        """Turn fake actuator on and simulate HA state callback."""
        self.turn_on_count += 1
        self.state = True
        if self.manager is not None:
            await self.manager.async_update_transformer_power_state(
                True,
                POWER_STATE_SOURCE_HA_SWITCH_STATE,
            )

    async def async_turn_off(self) -> None:
        """Turn fake actuator off."""
        self.turn_off_count += 1
        self.state = False


class NoPowerController:
    """Power controller fake for constant power mode."""

    exists = False
    state_source = "optimistic"

    async def async_is_on(self) -> None:
        """Return unknown actuator state."""
        return None

    async def async_turn_on(self) -> None:
        """No-op."""

    async def async_turn_off(self) -> None:
        """No-op."""


def make_manager(
    tcp: FakeTcpClient | None = None,
    power: FakePowerController | NoPowerController | None = None,
    *,
    stored_light_state: dict[str, object] | None = None,
    startup_preset_mode: str = StartupPresetMode.FIXED_PROGRAM.value,
    startup_preset_command: str = "PS14",
    power_on_delay: int = 0,
    power_off_delay: int = 0,
    rgb_join_timeout_ms: int = 0,
    lamp_wakeup_delay_ms: int = 0,
) -> DuratechDuralinkCommandManager:
    """Build a CommandManager with fakes."""
    tcp = tcp or FakeTcpClient()
    power = power or NoPowerController()
    manager = DuratechDuralinkCommandManager(
        tcp,
        DuratechDuralinkProtocol(),
        power,
        power_on_delay,
        power_off_delay,
        rgb_join_timeout_ms,
        lamp_wakeup_delay_ms,
        0,
        startup_preset_mode,
        startup_preset_command,
        False,
        stored_light_state,
    )
    if isinstance(power, FakePowerController):
        power.manager = manager
    return manager


def run(coro: object) -> object:
    """Run one async test coroutine."""
    return asyncio.run(coro)


async def _power_off_then_turn_on(
    manager: DuratechDuralinkCommandManager,
) -> None:
    await manager.async_update_transformer_power_state(
        False,
        POWER_STATE_SOURCE_HA_SWITCH_STATE,
    )
    await manager.async_turn_on()


def test_restore_rgb_after_transformer_off_command_history() -> None:
    """Restore RGB and brightness after transformer power-on."""

    async def scenario() -> None:
        tcp = FakeTcpClient()
        power = FakePowerController()
        manager = make_manager(
            tcp,
            power,
            stored_light_state={
                "last_rgb": [45, 160, 255],
                "last_brightness": 204,
                "last_mode": LightingMode.RGB.value,
                "active_light_program": PROGRAM_RGB,
            },
            startup_preset_mode=StartupPresetMode.RESTORE_LAST_STATE.value,
        )
        await _power_off_then_turn_on(manager)
        expected = [
            COMMAND_PL0,
            COMMAND_PL1,
            COMMAND_PC255255255,
            "PD080",
            "PC045160255",
        ]
        assert tcp.commands == expected
        assert manager.diagnostics()["init_command_history"] == ", ".join(expected)
        assert manager.last_rs485_command == "PC045160255"
        await manager.async_shutdown()

    run(scenario())


def test_fixed_startup_preset_ps14_command_history() -> None:
    """Fixed PS14 preset should be the final command."""

    async def scenario() -> None:
        tcp = FakeTcpClient()
        power = FakePowerController()
        manager = make_manager(tcp, power)
        await _power_off_then_turn_on(manager)
        expected = [
            COMMAND_PL0,
            COMMAND_PL1,
            COMMAND_PC255255255,
            COMMAND_PD075,
            COMMAND_PS14,
        ]
        assert tcp.commands == expected
        assert manager.diagnostics()["init_command_history"] == ", ".join(expected)
        assert manager.last_rs485_command == COMMAND_PS14
        assert manager.diagnostics()["optimistic_is_on"] is True
        await manager.async_shutdown()

    run(scenario())


def test_fixed_startup_preset_uses_persisted_brightness_in_init() -> None:
    """Persisted brightness should replace fixed PD075 in mandatory init."""

    async def scenario() -> None:
        tcp = FakeTcpClient()
        power = FakePowerController()
        manager = make_manager(
            tcp,
            power,
            stored_light_state={
                "last_brightness": 204,
                "last_mode": LightingMode.PROGRAM.value,
                "active_light_program": COMMAND_EFFECTS[COMMAND_PS14],
            },
        )
        await _power_off_then_turn_on(manager)
        expected = [
            COMMAND_PL0,
            COMMAND_PL1,
            COMMAND_PC255255255,
            "PD080",
            COMMAND_PS14,
        ]
        assert tcp.commands == expected
        assert manager.diagnostics()["init_command_history"] == ", ".join(expected)
        assert manager.last_rs485_command == COMMAND_PS14
        await manager.async_shutdown()

    run(scenario())


def test_turn_on_while_transformer_off_is_optimistic_during_startup() -> None:
    """Light turn_on should expose on while power_on_delay is still running."""

    async def scenario() -> None:
        tcp = FakeTcpClient()
        power = FakePowerController()
        manager = make_manager(tcp, power, power_on_delay=1)
        await manager.async_update_transformer_power_state(
            False,
            POWER_STATE_SOURCE_HA_SWITCH_STATE,
        )

        turn_on_task = asyncio.create_task(manager.async_turn_on())
        try:
            for _ in range(20):
                if manager.startup_sequence_running:
                    break
                await asyncio.sleep(0.01)

            assert manager.startup_sequence_running is True
            assert manager.init_phase == "power_on_delay"
            assert manager.diagnostics()["optimistic_is_on"] is True
            assert tcp.commands == []
        finally:
            await manager.async_shutdown()
            turn_on_task.cancel()
            try:
                await turn_on_task
            except asyncio.CancelledError:
                pass

    run(scenario())


def test_rgb_join_sends_only_latest_value() -> None:
    """RGB join should coalesce slider updates."""

    async def scenario() -> None:
        tcp = FakeTcpClient()
        manager = make_manager(
            tcp,
            NoPowerController(),
            rgb_join_timeout_ms=40,
        )
        await manager.async_set_rgb((70, 130, 250))
        await manager.async_set_rgb((71, 134, 254))
        await manager.async_set_rgb((71, 135, 255))
        await asyncio.sleep(0.15)
        assert tcp.commands == ["PC071135255"]
        await manager.async_shutdown()

    run(scenario())


def test_color_temperature_3500_maps_to_pt035() -> None:
    """3500 K should send PT035 and persist color temperature mode."""

    async def scenario() -> None:
        tcp = FakeTcpClient()
        persisted: list[dict[str, object]] = []
        manager = make_manager(
            tcp,
            NoPowerController(),
            stored_light_state={
                "last_rgb": [45, 160, 255],
                "last_mode": LightingMode.RGB.value,
                "active_light_program": PROGRAM_RGB,
            },
        )

        async def save(payload: dict[str, object]) -> None:
            persisted.append(payload)

        manager.set_persist_callback(save)
        await manager.async_turn_on(color_temperature_kelvin=3500)

        assert tcp.commands == ["PT035"]
        assert manager.desired_state.mode is LightingMode.COLOR_TEMP
        assert manager.desired_state.color_temperature_kelvin == 3500
        assert manager.last_color_temperature_kelvin == 3500
        assert manager.last_rgb_color == (45, 160, 255)
        assert persisted[-1]["last_color_temperature_kelvin"] == 3500
        assert persisted[-1]["last_mode"] == LightingMode.COLOR_TEMP.value
        await manager.async_shutdown()

    run(scenario())


def test_color_temperature_4000_maps_to_pt040() -> None:
    """4000 K should send PT040."""

    async def scenario() -> None:
        tcp = FakeTcpClient()
        manager = make_manager(tcp, NoPowerController())
        await manager.async_turn_on(color_temperature_kelvin=4000)
        assert tcp.commands == ["PT040"]
        assert manager.last_color_temperature_kelvin == 4000
        await manager.async_shutdown()

    run(scenario())


def test_color_temperature_rounds_to_nearest_500_kelvin() -> None:
    """Unsupported Kelvin values should round to the nearest 500 K step."""

    async def scenario() -> None:
        tcp = FakeTcpClient()
        manager = make_manager(tcp, NoPowerController())
        await manager.async_turn_on(color_temperature_kelvin=3800)
        assert tcp.commands == ["PT040"]
        assert manager.last_color_temperature_kelvin == 4000
        await manager.async_shutdown()

    run(scenario())


def test_color_temperature_4403_exposes_transmitted_4500() -> None:
    """4403 K should send PT045 and expose 4500 K."""

    async def scenario() -> None:
        tcp = FakeTcpClient()
        persisted: list[dict[str, object]] = []
        manager = make_manager(tcp, NoPowerController())

        async def save(payload: dict[str, object]) -> None:
            persisted.append(payload)

        manager.set_persist_callback(save)
        await manager.async_turn_on(color_temperature_kelvin=4403)

        diagnostics = manager.diagnostics()
        assert tcp.commands == ["PT045"]
        assert manager.desired_state.color_temperature_kelvin == 4500
        assert manager.last_color_temperature_kelvin == 4500
        assert diagnostics["optimistic_color_temperature_kelvin"] == 4500
        assert persisted[-1]["last_color_temperature_kelvin"] == 4500
        await manager.async_shutdown()

    run(scenario())


def test_color_temperature_4403_exposes_4500_before_tcp_success() -> None:
    """Normalized Kelvin should be visible while PT045 is still sending."""

    async def scenario() -> None:
        tcp = BlockingTcpClient()
        persisted: list[dict[str, object]] = []
        manager = make_manager(tcp, NoPowerController())

        async def save(payload: dict[str, object]) -> None:
            persisted.append(payload)

        manager.set_persist_callback(save)
        turn_on_task = asyncio.create_task(
            manager.async_turn_on(color_temperature_kelvin=4403)
        )
        await tcp.send_started.wait()

        diagnostics = manager.diagnostics()
        assert tcp.commands == ["PT045"]
        assert diagnostics["optimistic_color_temperature_kelvin"] == 4500
        assert manager.desired_state.color_temperature_kelvin == 4500
        assert manager.last_color_temperature_kelvin is None
        assert persisted == []

        tcp.release_send.set()
        await turn_on_task
        assert manager.last_color_temperature_kelvin == 4500
        assert persisted[-1]["last_color_temperature_kelvin"] == 4500
        await manager.async_shutdown()

    run(scenario())


def test_color_temperature_4230_exposes_transmitted_4000() -> None:
    """4230 K should send PT040 and expose 4000 K."""

    async def scenario() -> None:
        tcp = FakeTcpClient()
        manager = make_manager(tcp, NoPowerController())
        await manager.async_turn_on(color_temperature_kelvin=4230)

        diagnostics = manager.diagnostics()
        assert tcp.commands == ["PT040"]
        assert manager.desired_state.color_temperature_kelvin == 4000
        assert manager.last_color_temperature_kelvin == 4000
        assert diagnostics["optimistic_color_temperature_kelvin"] == 4000
        await manager.async_shutdown()

    run(scenario())


def test_color_temperature_6600_exposes_transmitted_6500() -> None:
    """6600 K should clamp to PT065 and expose 6500 K."""

    async def scenario() -> None:
        tcp = FakeTcpClient()
        manager = make_manager(tcp, NoPowerController())
        await manager.async_turn_on(color_temperature_kelvin=6600)

        diagnostics = manager.diagnostics()
        assert tcp.commands == ["PT065"]
        assert manager.desired_state.color_temperature_kelvin == 6500
        assert manager.last_color_temperature_kelvin == 6500
        assert diagnostics["optimistic_color_temperature_kelvin"] == 6500
        await manager.async_shutdown()

    run(scenario())


def test_color_temperature_3200_exposes_transmitted_3500() -> None:
    """3200 K should clamp to PT035 and expose 3500 K."""

    async def scenario() -> None:
        tcp = FakeTcpClient()
        manager = make_manager(tcp, NoPowerController())
        await manager.async_turn_on(color_temperature_kelvin=3200)

        diagnostics = manager.diagnostics()
        assert tcp.commands == ["PT035"]
        assert manager.desired_state.color_temperature_kelvin == 3500
        assert manager.last_color_temperature_kelvin == 3500
        assert diagnostics["optimistic_color_temperature_kelvin"] == 3500
        await manager.async_shutdown()

    run(scenario())


def test_program_up_down_cycles_rgb_and_ps_programs() -> None:
    """Program buttons should use explicit RGB/PS commands."""

    async def scenario() -> None:
        tcp = FakeTcpClient()
        manager = make_manager(tcp, NoPowerController())
        await manager.async_next_program()
        assert tcp.commands[-1] == "PC255255255"
        assert manager.active_light_program == PROGRAM_RGB

        await manager.async_next_program()
        assert tcp.commands[-1] == COMMAND_PS01
        assert manager.active_light_program == COMMAND_EFFECTS[COMMAND_PS01]

        manager.active_light_program = COMMAND_EFFECTS[COMMAND_PS14]
        manager.desired_state.active_light_program = manager.active_light_program
        await manager.async_next_program()
        assert tcp.commands[-1] == "PC255255255"
        assert manager.active_light_program == PROGRAM_RGB

        await manager.async_previous_program()
        assert tcp.commands[-1] == COMMAND_PS14
        assert manager.active_light_program == COMMAND_EFFECTS[COMMAND_PS14]

        manager.active_light_program = COMMAND_EFFECTS[COMMAND_PS01]
        manager.desired_state.active_light_program = manager.active_light_program
        await manager.async_previous_program()
        assert tcp.commands[-1] == "PC255255255"
        assert manager.active_light_program == PROGRAM_RGB
        await manager.async_shutdown()

    run(scenario())


def test_lamp_wakeup_before_program_after_pl0() -> None:
    """Visual commands after PL0 should wake lamp first."""

    async def scenario() -> None:
        tcp = FakeTcpClient()
        manager = make_manager(
            tcp,
            NoPowerController(),
            lamp_wakeup_delay_ms=1,
        )
        manager.last_lamp_command = COMMAND_PL0
        manager.lamp_is_on = False
        await manager.async_select_program(COMMAND_EFFECTS[COMMAND_PS04])
        assert tcp.commands == [COMMAND_PL1, COMMAND_PS04]
        await manager.async_shutdown()

    run(scenario())


def test_lamp_wakeup_before_color_temperature_after_pl0() -> None:
    """PT color temperature commands after PL0 should wake lamp first."""

    async def scenario() -> None:
        tcp = FakeTcpClient()
        manager = make_manager(
            tcp,
            NoPowerController(),
            lamp_wakeup_delay_ms=1,
        )
        manager.last_lamp_command = COMMAND_PL0
        manager.lamp_is_on = False
        await manager.async_turn_on(color_temperature_kelvin=4000)
        assert tcp.commands == [COMMAND_PL1, "PT040"]
        await manager.async_shutdown()

    run(scenario())


def test_program_selection_preserves_last_rgb_without_sending_pc() -> None:
    """PSxx selection should preserve last RGB but send only the program command."""

    async def scenario() -> None:
        tcp = FakeTcpClient()
        manager = make_manager(
            tcp,
            NoPowerController(),
            stored_light_state={
                "last_rgb": [45, 160, 255],
                "last_mode": LightingMode.RGB.value,
                "active_light_program": PROGRAM_RGB,
            },
        )
        assert manager.last_rgb_color == (45, 160, 255)

        await manager.async_select_program(COMMAND_EFFECTS[COMMAND_PS01])
        assert tcp.commands == [COMMAND_PS01]
        assert manager.last_rgb_color == (45, 160, 255)
        assert manager.diagnostics()["optimistic_rgb_color"] is None
        assert manager.active_light_program == COMMAND_EFFECTS[COMMAND_PS01]
        await manager.async_shutdown()

    run(scenario())


def test_ps12_ps13_ps14_select_as_normal_programs_and_persist() -> None:
    """White-looking PS programs should behave as normal persisted programs."""

    async def scenario() -> None:
        tcp = FakeTcpClient()
        persisted: list[dict[str, object]] = []
        manager = make_manager(tcp, NoPowerController())

        async def save(payload: dict[str, object]) -> None:
            persisted.append(payload)

        manager.set_persist_callback(save)
        for command in (COMMAND_PS12, COMMAND_PS13, COMMAND_PS14):
            program = COMMAND_EFFECTS[command]
            await manager.async_select_program(program)
            assert tcp.commands[-1] == command
            assert manager.active_light_program == program
            assert manager.desired_state.active_light_program == program
            assert manager.desired_state.mode is LightingMode.PROGRAM
            assert manager.last_mode is LightingMode.PROGRAM
            assert persisted[-1]["active_light_program"] == program
            assert persisted[-1]["last_mode"] == LightingMode.PROGRAM.value

        assert tcp.commands == [COMMAND_PS12, COMMAND_PS13, COMMAND_PS14]
        await manager.async_shutdown()

    run(scenario())


def test_lampen_sync_sends_pss_once_and_sets_ps01_state() -> None:
    """Lampen-Sync should send PsS once and optimistically reset to PS01."""

    async def scenario() -> None:
        tcp = FakeTcpClient()
        persisted: list[dict[str, object]] = []
        manager = make_manager(
            tcp,
            NoPowerController(),
            stored_light_state={
                "last_rgb": [45, 160, 255],
                "last_mode": LightingMode.RGB.value,
                "active_light_program": PROGRAM_RGB,
            },
        )

        async def save(payload: dict[str, object]) -> None:
            persisted.append(payload)

        manager.set_persist_callback(save)
        await manager.async_lampen_sync()

        assert tcp.commands == [COMMAND_AUTO_SYNC]
        assert manager.last_rs485_command == COMMAND_AUTO_SYNC
        assert manager.auto_sync_status == "Lampen-Sync aktiv (45 s)"
        assert manager.active_light_program == COMMAND_EFFECTS[COMMAND_PS01]
        assert manager.desired_state.mode is LightingMode.PROGRAM
        assert manager.desired_state.effect == COMMAND_EFFECTS[COMMAND_PS01]
        assert manager.last_rgb_color == (45, 160, 255)
        assert persisted[-1]["active_light_program"] == COMMAND_EFFECTS[COMMAND_PS01]
        assert persisted[-1]["last_mode"] == LightingMode.PROGRAM.value
        await manager.async_shutdown()

    run(scenario())


def test_lampen_sync_blocks_rs485_commands_during_lock() -> None:
    """No extra RS485 commands may be sent during the 45 second sync window."""

    async def scenario() -> None:
        tcp = FakeTcpClient()
        manager = make_manager(tcp, NoPowerController())
        await manager.async_lampen_sync()

        try:
            await manager.async_set_brightness(204)
        except RuntimeError as err:
            assert "Lampen-Sync is active" in str(err)
        else:
            raise AssertionError("brightness command was not blocked")

        assert tcp.commands == [COMMAND_AUTO_SYNC]
        assert manager.last_rs485_command == COMMAND_AUTO_SYNC
        await manager.async_shutdown()

    run(scenario())


def test_lampen_sync_after_transformer_off_runs_init_then_pss() -> None:
    """Transformer OFF should run mandatory init/startup before PsS."""

    async def scenario() -> None:
        tcp = FakeTcpClient()
        power = FakePowerController()
        manager = make_manager(tcp, power)
        await manager.async_update_transformer_power_state(
            False,
            POWER_STATE_SOURCE_HA_SWITCH_STATE,
        )

        await manager.async_lampen_sync()

        assert tcp.commands == [
            COMMAND_PL0,
            COMMAND_PL1,
            COMMAND_PC255255255,
            COMMAND_PD075,
            COMMAND_PS14,
            COMMAND_AUTO_SYNC,
        ]
        assert power.turn_on_count == 1
        assert manager.auto_sync_status == "Lampen-Sync aktiv (45 s)"
        await manager.async_shutdown()

    run(scenario())


def test_lampen_sync_wakes_lamp_before_pss_after_pl0() -> None:
    """Lampen-Sync should wake the lamp before sending PsS."""

    async def scenario() -> None:
        tcp = FakeTcpClient()
        manager = make_manager(
            tcp,
            NoPowerController(),
            lamp_wakeup_delay_ms=1,
        )
        manager.last_lamp_command = COMMAND_PL0
        manager.lamp_is_on = False

        await manager.async_lampen_sync()

        assert tcp.commands == [COMMAND_PL1, COMMAND_AUTO_SYNC]
        assert manager.last_lamp_command == COMMAND_PL1
        await manager.async_shutdown()

    run(scenario())


def test_brightness_204_maps_to_pd080() -> None:
    """HA brightness 204 should map to PD080."""

    async def scenario() -> None:
        tcp = FakeTcpClient()
        manager = make_manager(tcp, NoPowerController())
        await manager.async_set_brightness(204)
        assert tcp.commands == ["PD080"]
        await manager.async_shutdown()

    run(scenario())


def test_pl0_invariant_starts_delayed_power_off() -> None:
    """OFF must send PL0 and start delayed power-off when configured."""

    async def scenario() -> None:
        tcp = FakeTcpClient()
        power = FakePowerController(state=True)
        manager = make_manager(tcp, power, power_off_delay=30)
        await manager.async_update_transformer_power_state(
            True,
            POWER_STATE_SOURCE_HA_SWITCH_STATE,
        )
        await manager.async_turn_off()
        assert tcp.commands == [COMMAND_PL0]
        assert manager.last_lamp_command == COMMAND_PL0
        assert manager.lamp_is_on is False
        assert manager.delayed_power_off_timer_active is True
        await manager.async_shutdown()

    run(scenario())


def test_turn_off_sets_optimistic_off_immediately() -> None:
    """Light turn_off should expose off before PL0 handling completes."""

    async def scenario() -> None:
        tcp = FakeTcpClient()
        manager = make_manager(tcp, NoPowerController())
        manager.desired_state.is_on = True

        turn_off_task = asyncio.create_task(manager.async_turn_off())
        await asyncio.sleep(0)

        assert manager.diagnostics()["optimistic_is_on"] is False
        await turn_off_task
        assert tcp.commands == [COMMAND_PL0]
        assert manager.diagnostics()["optimistic_is_on"] is False
        await manager.async_shutdown()

    run(scenario())


def test_diagnostics_omits_removed_default_startup_sequence() -> None:
    """Diagnostics should not reference the removed static startup sequence."""

    async def scenario() -> None:
        manager = make_manager()
        diagnostics = manager.diagnostics()
        assert "default_startup_sequence" not in diagnostics
        assert diagnostics["init_phase"] == manager.init_phase
        assert "init_command" in diagnostics
        assert "init_command_history" in diagnostics
        await manager.async_shutdown()

    run(scenario())
