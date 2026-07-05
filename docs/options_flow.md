# Options Flow

## Purpose

The options flow lets installers tune command timing, startup behavior, and
diagnostics after the gateway has been configured.

Connection identity is intentionally kept in the config entry. Changing host,
port, or the transformer actuator should be handled by reconfiguring the entry.

## Options

| Option | Default | Description |
| --- | --- | --- |
| `power_on_delay` | 10 seconds | Wait after transformer power-on before the first RS485 init command. |
| `power_off_delay` | 1800 seconds | Wait after `PL0` before turning the configured transformer switch off. |
| `command_debounce_ms` | 500 ms | Suppresses duplicate user/Home Assistant commands. |
| `rgb_join_timeout_ms` | 400 ms | Coalesces rapid RGB picker changes into one `PCrrrgggbbb` command. |
| `lamp_wakeup_delay` | 300 ms | Wait after automatic `PL1` before a visual command when the lamp was off. |
| `inter_command_delay_ms` | 500 ms | Delay between RS485 commands during transformer init/startup sequences. |
| `startup_preset_mode` | `fixed_program` | Selects fixed startup program or restore-last-state behavior. |
| `startup_preset_command` | `PS14` | Fixed startup program, default `Kaltweiss`. |
| `command_terminator` | none | Optional ASCII terminator: none, `\r`, `\n`, or `\r\n`. |
| `protocol_debug_logging` | false | Enables detailed protocol and command-manager debug logging. |

## Startup Preset

The mandatory transformer init sequence always runs after the integration powers
on the configured transformer switch:

1. Wait `power_on_delay`.
2. Send `PL0`.
3. Wait `inter_command_delay_ms`.
4. Send `PL1`.
5. Wait `inter_command_delay_ms`.
6. Send `PC255255255`.
7. Wait `inter_command_delay_ms`.
8. Send `PD<last_brightness_or_075>`.
9. Wait `inter_command_delay_ms`.
10. Apply the Startup Preset.

`startup_preset_mode` controls only the optional final preset step:

| Mode | Behavior |
| --- | --- |
| `fixed_program` | Send the selected `PSxx` startup program. |
| `restore_last_state` | Restore the last persisted RGB, color temperature, or program state. |

## Diagnostics

Protocol debug logging is disabled by default. When enabled, it logs command
decisions, queue length, DesiredState, power state, RGB join, startup/init
progress, Lampen-Sync status, and transmitted RS485 commands.
