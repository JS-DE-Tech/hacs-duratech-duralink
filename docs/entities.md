# Entities

## Device Metadata

The integration exposes one Home Assistant device with:

- Manufacturer: Duratech / SpectraVision
- Model: PLP-REM-350
- Firmware: current integration version
- Hardware: Waveshare RS485 to PoE ETH (B)
- Protocol: Propulsion Systems DuraLink RS485
- Transport: TCP/IP

## Light

The primary light entity exposes:

- On/off
- Brightness
- RGB color
- White color temperature

The light always advertises `ColorMode.RGB` and `ColorMode.COLOR_TEMP`.
`rgb_color` remains a valid tuple even while a program or color temperature is
active so the Home Assistant RGB picker stays visible.

Color temperature values are clamped to 3500 K through 6500 K and rounded to the
nearest 500 K step before DesiredState is updated. Commands are sent as `PTxyz`,
for example `PT035` for 3500 K and `PT065` for 6500 K.

DuraLink programs are not exposed as Home Assistant light effects.

## Program Select

The program select entity is the normal UI for DuraLink programs:

- `RGB`
- `PS01` through `PS14`

`PS12`, `PS13`, and `PS14` are included as normal programs. `PW1`, `PW2`, and
`PW3` remain raw protocol commands only and are not exposed as separate normal
controls.

Selecting `RGB` sends the last RGB value or `PC255255255` as a fallback.
Selecting a `PSxx` program sends only that program command and persists the
active program and mode.

## Buttons

Buttons:

| Button | Behavior |
| --- | --- |
| Next Program | Cycles through `RGB`, then `PS01`..`PS14` using explicit commands. |
| Previous Program | Cycles backward through `RGB` and `PS14`..`PS01` using explicit commands. |
| Lampen-Sync | Sends `PsS` through the coordinator and CommandManager. |

Buttons do not communicate with the TCP client directly.

## Sensors

Useful diagnostic sensors include:

- Gateway connection
- Protocol
- Transport
- Last RS485 command
- Queue length
- Remaining power-off countdown
- Power state
- Power state source
- Last lamp command
- Active light program
- Last RGB value
- Last color temperature
- Last brightness
- Last mode
- Desired light state
- RGB join state
- Init phase
- Init command
- Init command history
- Lampen-Sync status
- Power-on countdown

Highly technical diagnostics are disabled by default where appropriate.

## Binary Sensors

Binary sensors:

- Transformer powered
- Lamp is on
- Delayed power-off timer active

## Services

Services route through the same coordinator and CommandManager path as entities:

- `duratech_duralink.refresh`
- `duratech_duralink.send_raw_command`
- `duratech_duralink.cancel_power_timer`
- `duratech_duralink.turn_transformer_on`
- `duratech_duralink.turn_transformer_off`
- `duratech_duralink.execute_intent`
- `duratech_duralink.lampen_sync`

`send_raw_command` is intended for diagnostics and developer use.
