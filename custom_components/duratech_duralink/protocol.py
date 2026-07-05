"""RS485 protocol constants and helpers for Duratech DuraLink."""

from __future__ import annotations

COMMAND_PL0 = "PL0"
COMMAND_PL1 = "PL1"
COMMAND_PC255255255 = "PC255255255"
COMMAND_PD075 = "PD075"
COMMAND_PW1 = "PW1"
COMMAND_PW2 = "PW2"
COMMAND_PW3 = "PW3"
COMMAND_PD100 = "PD100"
COMMAND_PROGRAM_UP = "PsU"
COMMAND_PROGRAM_DOWN = "PsD"
COMMAND_AUTO_SYNC = "PsS"
COMMAND_PS01 = "PS01"
COMMAND_PS02 = "PS02"
COMMAND_PS03 = "PS03"
COMMAND_PS04 = "PS04"
COMMAND_PS05 = "PS05"
COMMAND_PS06 = "PS06"
COMMAND_PS07 = "PS07"
COMMAND_PS08 = "PS08"
COMMAND_PS09 = "PS09"
COMMAND_PS10 = "PS10"
COMMAND_PS11 = "PS11"
COMMAND_PS12 = "PS12"
COMMAND_PS13 = "PS13"
COMMAND_PS14 = "PS14"

PROGRAM_WHITE_COMMANDS: dict[int, str] = {
    1: COMMAND_PW1,
    2: COMMAND_PW2,
    3: COMMAND_PW3,
}

PROGRAM_COLOR_COMMANDS: dict[int, str] = {
    4: COMMAND_PS01,
    5: COMMAND_PS02,
    6: COMMAND_PS03,
    7: COMMAND_PS04,
    8: COMMAND_PS05,
    9: COMMAND_PS06,
    10: COMMAND_PS07,
    11: COMMAND_PS08,
    12: COMMAND_PS09,
    13: COMMAND_PS10,
    14: COMMAND_PS11,
    15: COMMAND_PS12,
    16: COMMAND_PS13,
    17: COMMAND_PS14,
}

PROGRAM_COMMANDS: dict[int, str] = {
    **PROGRAM_WHITE_COMMANDS,
    **PROGRAM_COLOR_COMMANDS,
}

PROGRAM_SELECT_OPTIONS: tuple[str, ...] = (
    COMMAND_PS01,
    COMMAND_PS02,
    COMMAND_PS03,
    COMMAND_PS04,
    COMMAND_PS05,
    COMMAND_PS06,
    COMMAND_PS07,
    COMMAND_PS08,
    COMMAND_PS09,
    COMMAND_PS10,
    COMMAND_PS11,
    COMMAND_PS12,
    COMMAND_PS13,
    COMMAND_PS14,
)

class DuratechDuralinkProtocol:
    """Protocol boundary for future framed RS485 support."""

    def build_command_frame(self, command: str) -> bytes:
        """Build a frame for a command once framed protocol support is added."""
        raise NotImplementedError("RS485 frame encoding is not implemented yet")
