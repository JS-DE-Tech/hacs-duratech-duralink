# Power Controller

## Purpose

The power controller coordinates an optional external transformer actuator with
RS485 lighting commands. Transformer state and lamp state are independent:

| State | Meaning |
| --- | --- |
| Transformer powered | RS485 communication is possible. |
| Lamp on | The DuraLink controller accepts visual commands. |

## Supported Public Modes

| Mode | Description |
| --- | --- |
| Constant power | The transformer is always powered and no actuator is controlled. |
| Home Assistant switch entity | The integration calls `switch.turn_on` and `switch.turn_off` for the selected entity. |

Direct KNX power control is deprecated and not offered in new setup. Existing
legacy entries do not crash; they log a warning asking the user to expose the
KNX actuator as a Home Assistant switch entity.

## Home Assistant Switch Tracking

When a switch entity is configured, its state is authoritative:

- External ON sets transformer powered to true and power state to `on`.
- External OFF sets transformer powered to false and power state to `off`.
- External OFF cancels an obsolete delayed power-off timer.
- The next visual command after external OFF powers the switch on, waits
  `power_on_delay`, runs mandatory transformer init, applies the Startup Preset,
  and then sends the requested command if still needed.

The power state source is reported as `ha_switch_state`.

## Mandatory Transformer Init

After the integration powers on the transformer switch, no RS485 command is sent
until `power_on_delay` has elapsed. Then the mandatory init sequence is sent:

1. `PL0`
2. `PL1`
3. `PC255255255`
4. `PD<last_brightness_or_075>`

`inter_command_delay_ms` is applied between these RS485 commands. The Startup
Preset follows the mandatory init sequence.

## Delayed Power-Off

Light OFF preserves the PL0 invariant:

1. `PL0` is sent immediately.
2. If a power switch is configured, the delayed power-off timer starts.
3. After `power_off_delay`, the selected switch is turned off.
4. Any visual command during the countdown cancels the timer and keeps the
   transformer powered.
