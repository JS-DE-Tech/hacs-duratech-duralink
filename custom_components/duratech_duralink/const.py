"""Constants for the Duratech DuraLink integration."""

from __future__ import annotations

from enum import StrEnum

from homeassistant.const import Platform

DOMAIN = "duratech_duralink"
NAME = "Duratech DuraLink"
MANUFACTURER = "Duratech / SpectraVision"
MODEL_PLP_REM_350 = "PLP-REM-350"
GATEWAY_TARGET = "Waveshare RS485 to PoE ETH (B)"
SUGGESTED_GATEWAY_MODEL = GATEWAY_TARGET
PROTOCOL_NAME = "Propulsion Systems DuraLink RS485"
TRANSPORT_NAME = "TCP/IP"
VERSION = "0.1.0"
INTEGRATION_VERSION = VERSION

DEFAULT_PORT = 502
DEFAULT_TIMEOUT = 5
DEFAULT_POWER_ON_DELAY = 10
DEFAULT_POWER_OFF_DELAY = 1800
DEFAULT_COMMAND_DEBOUNCE_MS = 500
DEFAULT_INTER_COMMAND_DELAY_MS = 500
DEFAULT_RGB_JOIN_TIMEOUT_MS = 400
DEFAULT_LAMP_WAKEUP_DELAY_MS = 300
DEFAULT_STARTUP_PRESET_MODE = "fixed_program"
DEFAULT_STARTUP_PRESET_COMMAND = "PS14"
DEFAULT_COMMAND_TERMINATOR = ""
DEFAULT_PROTOCOL_DEBUG_LOGGING = False
DEFAULT_COLOR_TEMPERATURE_KELVIN = 3500
MIN_COLOR_TEMPERATURE_KELVIN = 3500
MAX_COLOR_TEMPERATURE_KELVIN = 6500
COLOR_TEMPERATURE_STEP_KELVIN = 500

POWER_STATE_SOURCE_OPTIMISTIC = "optimistic"
POWER_STATE_SOURCE_HA_SWITCH_STATE = "ha_switch_state"
POWER_STATE_SOURCE_UNKNOWN = "unknown"

PLATFORMS: tuple[Platform, ...] = (
    Platform.LIGHT,
    Platform.SELECT,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
)

CONF_POWER_MODE = "power_mode"
CONF_POWER_ENTITY_ID = "power_entity_id"
CONF_KNX_GROUP_ADDRESS = "knx_group_address"
CONF_KNX_POWER_SAME_COMMAND_STATUS = "knx_power_same_command_status"
CONF_KNX_POWER_COMMAND_GROUP_ADDRESS = "knx_power_command_group_address"
CONF_KNX_POWER_STATUS_GROUP_ADDRESS = "knx_power_status_group_address"
CONF_POWER_ON_DELAY = "power_on_delay"
CONF_POWER_OFF_DELAY = "power_off_delay"
CONF_COMMAND_DEBOUNCE_MS = "command_debounce_ms"
CONF_INTER_COMMAND_DELAY_MS = "inter_command_delay_ms"
CONF_RGB_JOIN_TIMEOUT_MS = "rgb_join_timeout_ms"
CONF_LAMP_WAKEUP_DELAY_MS = "lamp_wakeup_delay"
CONF_STARTUP_PRESET_MODE = "startup_preset_mode"
CONF_STARTUP_PRESET_COMMAND = "startup_preset_command"
CONF_COMMAND_TERMINATOR = "command_terminator"
CONF_PROTOCOL_DEBUG_LOGGING = "protocol_debug_logging"

SERVICE_REFRESH = "refresh"
SERVICE_SEND_RAW_COMMAND = "send_raw_command"
SERVICE_CANCEL_POWER_TIMER = "cancel_power_timer"
SERVICE_TURN_TRANSFORMER_ON = "turn_transformer_on"
SERVICE_TURN_TRANSFORMER_OFF = "turn_transformer_off"
SERVICE_EXECUTE_INTENT = "execute_intent"
SERVICE_LAMPEN_SYNC = "lampen_sync"

ATTR_ENTRY_ID = "entry_id"
ATTR_COMMAND = "command"
ATTR_INTENT = "intent"
ATTR_BRIGHTNESS = "brightness"
ATTR_RGB_COLOR = "rgb_color"
ATTR_EFFECT = "effect"

PROGRAM_RGB = "RGB"
EFFECT_PS01 = "Blau (PS01)"
EFFECT_PS02 = "Türkis (PS02)"
EFFECT_PS03 = "Gelb (PS03)"
EFFECT_PS04 = "Rot (PS04)"
EFFECT_PS05 = "Grün (PS05)"
EFFECT_PS06 = "Lila (PS06)"
EFFECT_PS07 = "Warmweiß (PS07)"
EFFECT_PS08 = "Blau (PS08)"
EFFECT_PS09 = "Orange (PS09)"
EFFECT_PS10 = "Farbwechsel langsam (PS10)"
EFFECT_PS11 = "Farbwechsel schnell (PS11)"
EFFECT_PS12 = "Warmweiß (PS12)"
EFFECT_PS13 = "Neutralweiß (PS13)"
EFFECT_PS14 = "Kaltweiß (PS14)"
COLOR_PROGRAM_EFFECT_OPTIONS: tuple[str, ...] = (
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
)
MAIN_PROGRAM_OPTIONS: tuple[str, ...] = (
    PROGRAM_RGB,
    *COLOR_PROGRAM_EFFECT_OPTIONS,
)
LIGHT_EFFECT_OPTIONS: tuple[str, ...] = (
    *COLOR_PROGRAM_EFFECT_OPTIONS,
)
STARTUP_PRESET_PROGRAM_OPTIONS: tuple[str, ...] = (
    PROGRAM_RGB,
    *COLOR_PROGRAM_EFFECT_OPTIONS,
)

class PowerMode(StrEnum):
    """Configured transformer power actuator mode."""

    NONE = "none"
    HOME_ASSISTANT_ENTITY = "home_assistant_entity"
    KNX_GROUP_ADDRESS = "knx_group_address"


class StartupPresetMode(StrEnum):
    """Configured startup preset behavior after transformer startup."""

    FIXED_PROGRAM = "fixed_program"
    RESTORE_LAST_STATE = "restore_last_state"


class GatewayConnectionState(StrEnum):
    """Gateway connection state exposed independently from light state."""

    CONNECTED = "Connected"
    DISCONNECTED = "Disconnected"
    CONNECTING = "Connecting"


class StartupSequenceState(StrEnum):
    """Startup sequence diagnostic state."""

    IDLE = "idle"
    RUNNING = "running"
    FAILED = "failed"


class InitPhase(StrEnum):
    """Transformer initialization phase."""

    IDLE = "idle"
    POWER_ON_DELAY = "power_on_delay"
    TRANSFORMER_INIT = "transformer_init"
    STARTUP_PRESET = "startup_preset"
    REQUESTED_COMMAND = "requested_command"
    READY = "ready"
    ERROR = "error"


class PowerState(StrEnum):
    """Internal transformer power state used for diagnostics."""

    UNKNOWN = "unknown"
    OFF = "off"
    POWERING_ON = "powering_on"
    ON = "on"
    POWER_OFF_DELAY = "power_off_delay"
    POWERING_OFF = "powering_off"
    ERROR = "error"
