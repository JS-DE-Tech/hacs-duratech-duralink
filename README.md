# Duratech / SpectraVision DuraLink for Home Assistant

<p align="center">
  <img
    src="https://raw.githubusercontent.com/JS-DE-Tech/hacs-duratech-duralink/main/docs/images/plp-rem-350.jpeg"
    alt="Duratech / SpectraVision PLP-REM-350 DuraLink controller"
    width="420">
</p>

Home Assistant HACS custom integration for controlling Duratech / SpectraVision
DuraLink PLP-REM-350 pool light controllers locally via TCP-to-RS485.

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Custom%20Integration-41BDF5)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-Custom%20Repository-41BDF5)](https://hacs.xyz/)
[![Protocol](https://img.shields.io/badge/Protocol-TCP--to--RS485-success)](docs/rs485_protocol.md)
[![License](https://img.shields.io/badge/License-MIT-blue)](LICENSE)
[![Support](https://img.shields.io/badge/Support-PayPal-00457C)](https://paypal.me/JensSaffrich)

This integration controls the DuraLink controller locally over your LAN. It does
not require MQTT, Node-RED, or a cloud connection. Home Assistant entities route
all actions through the coordinator and CommandManager, which then sends the
verified RS485 commands over the configured TCP gateway.

## Supported hardware

| Component | Supported hardware |
| --- | --- |
| Controller | PLP-REM-350 |
| Gateway | Waveshare RS485 to PoE ETH (B) |
| Lights | SpectraVision / Duravision RGB / RGBW pool lights |

## Features

- Local TCP-to-RS485 control.
- RGB color control.
- Color temperature control via `PTxyz`.
- 15 light programs through the program select entity.
- Brightness control.
- Mandatory transformer startup sequence.
- Startup preset or restore last state.
- Automatic lamp wake-up after `PL0`.
- Lampen-Sync / Auto Sync via `PsS`.
- Optional Home Assistant transformer power entity.

## Hardware overview

<p align="center">
  <img
    src="https://raw.githubusercontent.com/JS-DE-Tech/hacs-duratech-duralink/main/docs/images/plp-rem-350_detail.jpeg"
    alt="PLP-REM-350 DuraLink controller detail"
    width="420">
  <img
    src="https://raw.githubusercontent.com/JS-DE-Tech/hacs-duratech-duralink/main/docs/images/waveshare.jpeg"
    alt="Waveshare RS485 to PoE ETH (B) gateway"
    width="320">
  <img
    src="https://raw.githubusercontent.com/JS-DE-Tech/hacs-duratech-duralink/main/docs/images/poolleds.jpeg"
    alt="SpectraVision / Duravision pool lights"
    width="420">
</p>

The PLP-REM-350 remains the lighting controller. The Waveshare gateway only
bridges TCP/IP from Home Assistant to the DuraLink RS485 bus.

## Waveshare configuration

Configure the Waveshare RS485 to PoE ETH (B) gateway as a TCP server.

<p align="center">
  <img
    src="https://raw.githubusercontent.com/JS-DE-Tech/hacs-duratech-duralink/main/docs/images/waveshare_config.png"
    alt="Waveshare TCP-to-RS485 configuration"
    width="720">
</p>

Use these serial and network settings:

| Setting | Value |
| --- | --- |
| Work Mode | TCP Server |
| Device Port | 502 |
| Baud Rate | 9600 |
| Databits | 8 |
| Parity | None |
| Stopbits | 1 |
| Flow control | None |
| Protocol | None |
| Multi-host | No |

After saving the configuration, restart the gateway if requested by the web
interface.

## Wiring

Connect the RS485 side of the Waveshare gateway to the DuraLink RS485 terminals:

| Waveshare | DuraLink |
| --- | --- |
| 485A | RS485 A |
| 485B | RS485 B |
| GND | Optional, if available or required by the installation |

If commands are not accepted by the controller, verify the A/B polarity first.
Some installations label RS485 terminals differently.

## Installation

1. Open HACS in Home Assistant.
2. Add this repository as a custom repository:

   ```text
   JS-DE-Tech/hacs-duratech-duralink
   ```

3. Select category:

   ```text
   Integration
   ```

4. Install **Duratech / SpectraVision DuraLink**.
5. Restart Home Assistant.
6. Add the integration from **Settings -> Devices & services**.

## Configuration

During setup, enter the connection details for the Waveshare gateway:

- Host/IP address of the Waveshare gateway.
- TCP port, usually `502`.
- Optional Home Assistant switch entity for transformer power control.

The options flow exposes timing and startup settings:

- Power-on delay.
- Lamp wake-up delay.
- Startup preset.
- Restore last state mode.

Use a transformer power entity only when Home Assistant can control the external
transformer actuator as a normal switch entity. Constant power installations do
not need a power entity.

## Entities

The entity model is documented in:

[docs/entities.md](docs/entities.md)

The integration exposes a Home Assistant light entity, a program select entity,
diagnostic sensors, transformer/lamp binary sensors, and buttons for next
program, previous program, and Lampen-Sync.

## RS485 protocol

The implemented and documented RS485 commands are described in:

[docs/rs485_protocol.md](docs/rs485_protocol.md)

The integration currently uses write-only optimistic control. It sends verified
DuraLink ASCII commands such as `PL0`, `PL1`, `PCrrrgggbbb`, `PTxyz`, `PDxxx`,
`PS01`..`PS14`, and `PsS`.

## Notes

- No cloud connection is required.
- No MQTT broker is required.
- No direct TCP communication is performed from Home Assistant entities.
- All commands are routed through the coordinator and CommandManager.
- The integration is designed for local control through a TCP-to-RS485 gateway.
