# RS485 Protocol

## Mode

The integration uses write-only optimistic ASCII control for the PLP-REM-350.
Commands are considered successful when they are queued, written to the TCP
gateway, and drained without a transport error.

No command terminator is appended by default. The options flow can configure
none, `\r`, `\n`, or `\r\n`.

## Implemented Commands

| Command | Meaning |
| --- | --- |
| `PL0` | Light off. Sent immediately for light-off requests. |
| `PL1` | Light on and automatic lamp wake-up. |
| `PsS` | Auto sync procedure / Lampen-Sync. |
| `PS01`..`PS14` | Normal light programs. |
| `PW1`..`PW3` | Raw white-program commands for developer/raw service use. |
| `PCrrrgggbbb` | RGB color with three-digit zero-padded red, green, and blue channels. |
| `PTxyz` | White color temperature where `xyz` is Kelvin divided by 100. |
| `PD000`..`PD100` | Brightness percentage. |

Raw/developer commands retained for protocol completeness:

| Command | Meaning |
| --- | --- |
| `PsU` | Raw next-program command. Normal buttons use explicit `PSxx` commands instead. |
| `PsD` | Raw previous-program command. Normal buttons use explicit `PSxx` commands instead. |

Future protocol extensions documented but not implemented:

| Command | Future use |
| --- | --- |
| `PRAx` | Red channel adjustment extension. |
| `PRBx` | Blue channel adjustment extension. |
| `PRMx` | Mixed or mode adjustment extension. |

## Program Mapping

| Label | RS485 command |
| --- | --- |
| Blau | `PS01` |
| Tuerkis | `PS02` |
| Gelb | `PS03` |
| Rot | `PS04` |
| Gruen | `PS05` |
| Lila | `PS06` |
| Warmweiss | `PS07` |
| Blau | `PS08` |
| Orange | `PS09` |
| Farbwechsel langsam | `PS10` |
| Farbwechsel schnell | `PS11` |
| Warmweiss | `PS12` |
| Neutralweiss | `PS13` |
| Kaltweiss | `PS14` |

Programs are exposed through the DuraLink program select entity, not through the
Home Assistant light effect API.

## Command Families

| Semantic request | RS485 output |
| --- | --- |
| RGB | `PCrrrgggbbb` only. |
| Color temperature | `PTxyz` only. |
| Program selection | `PS01`..`PS14` only. |
| Brightness | `PD000`..`PD100` only. |
| ON | `PL1` only. |
| OFF | `PL0` only. |
| Lampen-Sync | `PsS` once, then 45 second command lock. |

Brightness is independent from the active lighting mode. `PDxxx` must not change
RGB, program, effect, or mode.

## Color Temperature

`PTxyz` uses Kelvin divided by 100:

| Kelvin | Command |
| --- | --- |
| 3500 K | `PT035` |
| 4000 K | `PT040` |
| 4500 K | `PT045` |
| 5000 K | `PT050` |
| 5500 K | `PT055` |
| 6000 K | `PT060` |
| 6500 K | `PT065` |

Home Assistant values are clamped to 3500 K through 6500 K and rounded to the
nearest 500 K before DesiredState is updated and persisted.

## Startup Init

After the integration powers on a configured transformer switch, no RS485
command is sent during `power_on_delay`. Then the mandatory init sequence is
sent with `inter_command_delay_ms` between commands:

1. `PL0`
2. `PL1`
3. `PC255255255`
4. `PD<last_brightness_or_075>`

The Startup Preset follows this mandatory init sequence.

## Lamp Wake-Up

If the last lamp command was `PL0`, the next visual command first sends `PL1`,
waits `lamp_wakeup_delay`, and then sends the requested command.

`PT` color-temperature commands are visual commands and use the same wake-up
path.

## Lampen-Sync

`PsS` is exposed only through the Lampen-Sync button and service. It is never run
automatically.

After `PsS` is sent:

- No further RS485 command is sent for exactly 45 seconds.
- Commands requested during the lock window are rejected.
- The status sensor counts down from `Lampen-Sync aktiv (45 s)`.
- The active program is set optimistically to Program 1 / Blau (`PS01`).
