"""Source-level tests for the DuraLink Home Assistant light surface."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LIGHT_SOURCE = ROOT / "custom_components" / "duratech_duralink" / "light.py"
SELECT_SOURCE = ROOT / "custom_components" / "duratech_duralink" / "select.py"
BUTTON_SOURCE = ROOT / "custom_components" / "duratech_duralink" / "button.py"
INIT_SOURCE = ROOT / "custom_components" / "duratech_duralink" / "__init__.py"
COORDINATOR_SOURCE = ROOT / "custom_components" / "duratech_duralink" / "coordinator.py"
CONST_SOURCE = ROOT / "custom_components" / "duratech_duralink" / "const.py"
SENSOR_SOURCE = ROOT / "custom_components" / "duratech_duralink" / "sensor.py"
DIAGNOSTICS_SOURCE = (
    ROOT / "custom_components" / "duratech_duralink" / "diagnostics.py"
)


def _light_source() -> str:
    """Return the light entity source."""
    return LIGHT_SOURCE.read_text(encoding="utf-8")


def test_light_entity_does_not_advertise_effects() -> None:
    """The light entity must not make programs visible as HA effects."""
    source = _light_source()

    assert "LightEntityFeature" not in source
    assert "_attr_effect_list" not in source
    assert "ATTR_EFFECT" not in source


def test_light_entity_keeps_rgb_color_mode() -> None:
    """The light entity should keep RGB and color temperature controls available."""
    source = _light_source()

    assert "_attr_supported_color_modes = {ColorMode.RGB, ColorMode.COLOR_TEMP}" in source
    assert "_attr_color_mode = ColorMode.RGB" in source
    assert "color_mode = ColorMode.RGB" in source
    assert "ColorMode.COLOR_TEMP" in source
    assert "def color_temp_kelvin" in source


def test_light_rgb_color_has_last_rgb_and_white_fallback() -> None:
    """The light entity must never expose a null RGB color."""
    source = _light_source()

    assert "self.coordinator.data.optimistic_rgb_color" in source
    assert "self.coordinator.data.last_rgb_color" in source
    assert "or (255, 255, 255)" in source


def test_light_color_temperature_has_default_and_turn_on_path() -> None:
    """The light entity should expose and accept Kelvin color temperature."""
    source = _light_source()

    assert "DEFAULT_COLOR_TEMPERATURE_KELVIN" in source
    assert "COLOR_TEMPERATURE_STEP_KELVIN" in source
    assert "def _normalize_color_temperature_kelvin" in source
    assert 'kwargs.get("color_temp_kelvin")' in source
    assert "_normalize_color_temperature_kelvin(color_temperature_kelvin)" in source
    assert "color_temperature_kelvin=" in source


def test_light_effect_property_returns_none() -> None:
    """Active programs must not be mirrored into light.effect."""
    module = ast.parse(_light_source())
    effect_functions = [
        node
        for node in ast.walk(module)
        if isinstance(node, ast.FunctionDef) and node.name == "effect"
    ]

    assert len(effect_functions) == 1
    returns = [
        node
        for node in ast.walk(effect_functions[0])
        if isinstance(node, ast.Return)
    ]
    assert len(returns) == 1
    assert isinstance(returns[0].value, ast.Constant)
    assert returns[0].value.value is None


def test_program_select_remains_program_ui() -> None:
    """The select entity remains the normal RGB/PSxx program selector."""
    source = SELECT_SOURCE.read_text(encoding="utf-8")

    assert "MAIN_PROGRAM_OPTIONS" in source
    assert "_attr_options = list(MAIN_PROGRAM_OPTIONS)" in source
    assert "async_select_program(option)" in source


def test_device_metadata_is_detailed_and_dynamic() -> None:
    """Device metadata should expose hardware details without hardcoded firmware."""
    const_source = CONST_SOURCE.read_text(encoding="utf-8")
    light_source = _light_source()
    sensor_source = SENSOR_SOURCE.read_text(encoding="utf-8")
    diagnostics_source = DIAGNOSTICS_SOURCE.read_text(encoding="utf-8")

    assert 'MODEL_PLP_REM_350 = "PLP-REM-350"' in const_source
    assert 'MANUFACTURER = "Duratech / SpectraVision"' in const_source
    assert 'GATEWAY_TARGET = "Waveshare RS485 to PoE ETH (B)"' in const_source
    assert 'PROTOCOL_NAME = "Propulsion Systems DuraLink RS485"' in const_source
    assert 'TRANSPORT_NAME = "TCP/IP"' in const_source
    assert '"sw_version": INTEGRATION_VERSION' in light_source
    assert '"hw_version": GATEWAY_TARGET' in light_source
    assert 'key="protocol"' in sensor_source
    assert 'key="transport"' in sensor_source
    assert '"protocol": PROTOCOL_NAME' in diagnostics_source
    assert '"transport": TRANSPORT_NAME' in diagnostics_source


def test_lampen_sync_button_and_service_route_through_coordinator() -> None:
    """Lampen-Sync UI entry points must not send TCP directly."""
    button_source = BUTTON_SOURCE.read_text(encoding="utf-8")
    init_source = INIT_SOURCE.read_text(encoding="utf-8")

    assert 'key="lampen_sync"' in button_source
    assert "async_lampen_sync()" in button_source
    assert "async_send_command" not in button_source
    assert "SERVICE_LAMPEN_SYNC" in init_source
    assert "_async_handle_lampen_sync" in init_source
    assert "coordinator.async_lampen_sync()" in init_source


def test_coordinator_does_not_hide_pending_optimistic_on_during_init_pl0() -> None:
    """Mandatory init PL0 must not hide a pending desired on state."""
    source = COORDINATOR_SOURCE.read_text(encoding="utf-8")

    assert "self.data.lamp_is_on is False" in source
    assert "self.data.optimistic_is_on is not True" in source
