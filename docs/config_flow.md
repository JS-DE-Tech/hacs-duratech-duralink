# Configuration Flow

## Purpose

The configuration flow creates one Home Assistant config entry for a DuraLink
TCP-to-RS485 gateway.

The flow collects only stable setup data:

- Host or IP address of the Waveshare gateway.
- TCP port, usually `502`.
- Optional device name.
- Optional external transformer power actuator.

Runtime tuning values are configured later in the options flow.

## Power Actuator Modes

New setup offers two power modes:

| Mode | Description |
| --- | --- |
| Constant power / Dauerstrom | No external transformer actuator is controlled by the integration. |
| Home Assistant switch entity / Home Assistant Entitaet | The transformer is controlled through an existing Home Assistant `switch` entity. |

Direct KNX power control is deprecated and is not offered for new setup. Existing
legacy entries are handled defensively and log a migration warning. KNX actuators
should be exposed to Home Assistant as switch entities and selected through the
Home Assistant switch entity mode.

## Validation

The config flow validates:

- Host and port format.
- TCP reachability of the configured gateway.
- Duplicate entries using the normalized host and port.
- Selected power entity belongs to the `switch` domain.

The temporary TCP client used during setup is always closed after the connection
test.

## Stored Data

Configuration data contains:

- `host`
- `port`
- Optional `name`
- `power_mode`
- Optional `power_entity_id`

Options are initialized with conservative defaults for power delays, RGB join,
lamp wake-up, inter-command delay, startup preset, command terminator, and
protocol debug logging.
