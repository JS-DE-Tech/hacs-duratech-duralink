# Architecture

## Overview

The Duratech DuraLink integration exposes a PLP-REM-350 pool light controller to
Home Assistant through a local TCP-to-RS485 gateway.

The PLP-REM-350 is treated as a write-only ASCII command receiver. There is no
required status polling or response parsing before Home Assistant state is
updated. State is optimistic and follows the command manager's DesiredState.

## Command Path

All commands follow one path:

```text
Home Assistant entity/service
  -> coordinator
  -> CommandManager
  -> TCP client
  -> TCP-to-RS485 gateway
  -> DuraLink RS485 bus
```

Entities and services do not communicate with the TCP client directly.

## Runtime Components

| Component | Responsibility |
| --- | --- |
| Coordinator | Owns shared runtime state, restoration, diagnostics, and entity updates. |
| CommandManager | Owns DesiredState, queue handling, RGB join, lamp wake-up, transformer init, Startup Preset, PL0 handling, Lampen-Sync lock, and RS485 transmission decisions. |
| TCP client | Opens the network connection and writes ASCII commands to the gateway. |
| Power controller | Optional Home Assistant switch abstraction for transformer power. |
| Entities | Thin Home Assistant projections of coordinator state. |

## DesiredState

DesiredState uses an explicit lighting mode:

- `unknown`
- `rgb`
- `color_temp`
- `program`
- `white`

Command rules:

- `PCrrrgggbbb` sets RGB mode and clears the active program.
- `PTxyz` sets color temperature mode.
- `PS01`..`PS14` set program mode.
- `PDxxx` changes brightness only.
- `PL1` turns the lamp on without changing the active mode.
- `PL0` preserves the mandatory light-off invariant.

## RGB Join

Home Assistant RGB picker movement is coalesced with `rgb_join_timeout_ms`
(default 400 ms). DesiredState updates immediately, but only the latest RGB value
is sent after the quiet window.

Pending RGB joins are cancelled by:

- Light OFF.
- Program selection.
- Program Up/Down.
- Integration unload.

## Transformer Init And Startup Preset

When the integration turns on a configured transformer switch, it always waits
`power_on_delay` before sending any RS485 command. It then sends the mandatory
init sequence using `inter_command_delay_ms` between commands:

1. `PL0`
2. `PL1`
3. `PC255255255`
4. `PD<last_brightness_or_075>`

After init, the Startup Preset is applied:

- `fixed_program` sends the configured `PSxx`, default `PS14`.
- `restore_last_state` restores the last persisted RGB, color temperature, or
  program state.

Finally, the requested user command is sent if it is still required.

## Lamp Wake-Up

If the last lamp command was `PL0` and the transformer is already powered, the
next visual command wakes the lamp first:

1. Send `PL1`.
2. Wait `lamp_wakeup_delay`.
3. Send the requested visual command.

This applies to RGB, color temperature, brightness, program selection, Program
Up/Down, and Lampen-Sync.

## Lampen-Sync

The `PsS` auto-sync command is user-triggered only. After `PsS` is sent, the
CommandManager blocks further RS485 commands for 45 seconds and exposes the
Lampen-Sync countdown diagnostic state. The active program is set
optimistically to Program 1 / Blau (`PS01`).

## Power Control

New setup supports:

- Constant power.
- Home Assistant switch entity.

Direct KNX power control is deprecated. Existing legacy entries log a warning
and should be migrated to a Home Assistant switch entity.

## Diagnostics

Diagnostics include gateway connection, transformer powered, power state,
power-state source, lamp state, last lamp command, active light program, last RGB
value, last color temperature, brightness, mode, last RS485 command, init phase,
init command, init command history, power-on countdown, remaining power-off
countdown, RGB join state, Lampen-Sync status, and queue length.
