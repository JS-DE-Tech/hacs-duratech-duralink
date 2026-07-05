"""Async TCP client skeleton for the Duratech DuraLink gateway."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging

from .const import GatewayConnectionState

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class DuratechDuralinkTcpClient:
    """Small async TCP client for a TCP-to-RS485 gateway."""

    host: str
    port: int
    timeout: float
    command_terminator: str = ""
    protocol_debug_logging: bool = False
    connection_state: str = GatewayConnectionState.DISCONNECTED.value
    _reader: asyncio.StreamReader | None = None
    _writer: asyncio.StreamWriter | None = None

    @property
    def is_connected(self) -> bool:
        """Return whether the socket appears connected."""
        return self._writer is not None and not self._writer.is_closing()

    async def async_connect(self) -> None:
        """Open the TCP connection."""
        if self.is_connected:
            return
        if self.protocol_debug_logging:
            _LOGGER.debug(
                "Connecting to DuraLink gateway at %s:%s",
                self.host,
                self.port,
            )
        self.connection_state = GatewayConnectionState.CONNECTING.value
        try:
            self._reader, self._writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.timeout,
            )
        except Exception:
            self.connection_state = GatewayConnectionState.DISCONNECTED.value
            raise
        self.connection_state = GatewayConnectionState.CONNECTED.value
        if self.protocol_debug_logging:
            _LOGGER.debug(
                "Connected to DuraLink gateway at %s:%s",
                self.host,
                self.port,
            )

    async def async_send_command(self, command: str) -> None:
        """Send a plain ASCII command to the gateway."""
        await self.async_connect()
        if self._writer is None:
            raise ConnectionError("DuraLink TCP writer is not available")

        payload = f"{command}{self.command_terminator}".encode("ascii")
        if self.protocol_debug_logging:
            _LOGGER.debug(
                "DuraLink TX command=%s terminator=%r host=%s port=%s",
                command,
                self.command_terminator,
                self.host,
                self.port,
            )
        try:
            self._writer.write(payload)
            await asyncio.wait_for(self._writer.drain(), timeout=self.timeout)
        except Exception:
            self.connection_state = GatewayConnectionState.DISCONNECTED.value
            if self.protocol_debug_logging:
                _LOGGER.debug(
                    "DuraLink TX failed command=%s host=%s port=%s",
                    command,
                    self.host,
                    self.port,
                    exc_info=True,
                )
            await self.async_close()
            raise
        self.connection_state = GatewayConnectionState.CONNECTED.value
        if self.protocol_debug_logging:
            _LOGGER.debug(
                "DuraLink TX success command=%s host=%s port=%s",
                command,
                self.host,
                self.port,
            )

    async def async_test_connection(self) -> None:
        """Open and close a TCP connection to validate basic reachability."""
        reader: asyncio.StreamReader | None = None
        writer: asyncio.StreamWriter | None = None
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(self.host, self.port),
                timeout=self.timeout,
            )
        finally:
            del reader
            if writer is not None:
                writer.close()
                await writer.wait_closed()

    async def async_close(self) -> None:
        """Close the TCP connection."""
        if self._writer is None:
            return
        if self.protocol_debug_logging:
            _LOGGER.debug("Closing DuraLink gateway TCP connection")
        self._writer.close()
        await self._writer.wait_closed()
        self._reader = None
        self._writer = None
        self.connection_state = GatewayConnectionState.DISCONNECTED.value
