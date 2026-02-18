#!/usr/bin/env python3
"""
KPA500 Amplifier Serial Interface Module

Async interface for controlling the Elecraft KPA500 amplifier via serial port.
Based on KPA500 Programmer's Reference documentation.
"""

import asyncio
import logging
from enum import IntEnum, Enum
from dataclasses import dataclass
from typing import Optional, Protocol, Self
import serial_asyncio_fast

logger = logging.getLogger(__name__)


class Band(IntEnum):
    """KPA500 band selection values."""
    BAND_160M = 0
    BAND_80M = 1
    BAND_60M = 2
    BAND_40M = 3
    BAND_30M = 4
    BAND_20M = 5
    BAND_17M = 6
    BAND_15M = 7
    BAND_12M = 8
    BAND_10M = 9
    BAND_6M = 10


class OperatingMode(IntEnum):
    """KPA500 operating mode."""
    STANDBY = 0
    OPERATE = 1


class PowerState(IntEnum):
    """KPA500 power state."""
    OFF = 0
    ON = 1


class FanSpeed(IntEnum):
    """KPA500 minimum fan speed setting."""
    LOW = 0
    MEDIUM = 1
    HIGH = 2


class BaudRate(IntEnum):
    """Serial baud rate settings."""
    BAUD_4800 = 0
    BAUD_9600 = 1
    BAUD_19200 = 2
    BAUD_38400 = 3


class Fault(IntEnum):
    """KPA500 fault codes."""
    NONE = 0
    CURRENT = 1
    TEMPERATURE = 2
    VOLTAGE = 3
    SWR = 4
    OVERDRIVE = 5
    BIAS_TIMEOUT = 6
    POWER = 7
    KEYING = 8
    BAND_ERROR = 9
    PA_COMMUNICATION = 10


class RadioInterface(IntEnum):
    """Radio interface selection."""
    RS232 = 0
    AUX = 1


@dataclass
class PowerSWR:
    """Power and SWR reading from the KPA500."""
    power_watts: int
    swr: float


@dataclass
class VoltageCurrentReading:
    """Voltage and current reading from the KPA500."""
    voltage: float  # Volts
    current: float  # Amps


class AsyncSerialStream(Protocol):
    """Protocol for async serial stream interface."""

    async def read(self, n: int) -> bytes: ...
    async def readline(self) -> bytes: ...
    def write(self, data: bytes) -> None: ...
    async def drain(self) -> None: ...


class KPA500:
    """
    Async interface for the Elecraft KPA500 amplifier.

    This class provides methods to control and monitor the KPA500 amplifier
    via its serial command protocol.
    """

    DEFAULT_BAUDRATE = 38400
    DEFAULT_TIMEOUT = 1.0
    DEFAULT_RETRY_COUNT = 3
    DEFAULT_RETRY_INTERVAL = 0.1
    COMMAND_PREFIX = "^"
    COMMAND_TERMINATOR = ";"

    def __init__(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        timeout: float = DEFAULT_TIMEOUT,
        retry_count: int = DEFAULT_RETRY_COUNT,
        retry_interval: float = DEFAULT_RETRY_INTERVAL
    ):
        """
        Initialize KPA500 interface with async streams.

        Args:
            reader: Async stream reader for receiving data
            writer: Async stream writer for sending data
            timeout: Command timeout in seconds
            retry_count: Number of retries for set commands
            retry_interval: Interval between retries in seconds
        """
        self._reader = reader
        self._writer = writer
        self._timeout = timeout
        self._retry_count = retry_count
        self._retry_interval = retry_interval
        self._lock = asyncio.Lock()
        self._power_on: Optional[bool] = None

    @classmethod
    async def from_serial_port(
        cls,
        port: str,
        baudrate: int = DEFAULT_BAUDRATE,
        timeout: float = DEFAULT_TIMEOUT,
        retry_count: int = DEFAULT_RETRY_COUNT,
        retry_interval: float = DEFAULT_RETRY_INTERVAL
    ) -> Self:
        """
        Create KPA500 interface from a serial port.

        Args:
            port: Serial port path (e.g., '/dev/ttyUSB0' or 'COM3')
            baudrate: Baud rate (default 38400)
            timeout: Command timeout in seconds
            retry_count: Number of retries for set commands
            retry_interval: Interval between retries in seconds

        Returns:
            Configured KPA500 instance
        """
        reader, writer = await serial_asyncio_fast.open_serial_connection(
            url=port,
            baudrate=baudrate,
            bytesize=8,
            parity='N',
            stopbits=1
        )

        instance = cls(reader, writer, timeout, retry_count, retry_interval)
        await instance._detect_power_state()
        return instance

    async def _detect_power_state(self) -> None:
        """
        Detect if the KPA500 is powered on or in bootloader mode.

        If the device responds with a valid power state, it's powered on.
        If no response or just echo, assume it's in bootloader mode.
        """
        try:
            response = await self._send_command("ON", timeout=0.5)
            # Valid response is "ON0" or "ON1", not just "ON" (which would be echo)
            if response in ("ON0", "ON1"):
                self._power_on = True
            else:
                self._power_on = False
        except asyncio.TimeoutError:
            self._power_on = False

    @property
    def is_powered_on(self) -> Optional[bool]:
        """Return True if KPA500 is powered on, False if in bootloader mode."""
        return self._power_on

    async def _send_command(
        self,
        command: str,
        data: str = "",
        timeout: Optional[float] = None,
        wait_response: bool = True
    ) -> Optional[str]:
        """
        Send a command to the KPA500 and optionally wait for response.

        Args:
            command: Command without prefix (e.g., "ON", "BN")
            data: Optional data to append to command
            timeout: Override default timeout
            wait_response: If False, return immediately after sending (for set commands)

        Returns:
            Response string without prefix/terminator, or None if no response
        """
        timeout = timeout if timeout is not None else self._timeout
        full_command = f"{self.COMMAND_PREFIX}{command}{data}{self.COMMAND_TERMINATOR}"

        async with self._lock:
            # Clear any pending data
            try:
                while True:
                    await asyncio.wait_for(
                        self._reader.read(100),
                        timeout=0.01
                    )
            except asyncio.TimeoutError:
                pass

            # Send command
            logger.debug("KPA500 TX: %s", full_command)
            self._writer.write(full_command.encode('ascii'))
            await self._writer.drain()

            if not wait_response:
                return None

            # Wait for response
            try:
                response = await asyncio.wait_for(
                    self._reader.readuntil(b';'),
                    timeout=timeout
                )
                response_str = response.decode('ascii').strip()
                logger.debug("KPA500 RX: %s", response_str)
                # Remove prefix and terminator
                if response_str.startswith(self.COMMAND_PREFIX):
                    response_str = response_str[1:]
                if response_str.endswith(self.COMMAND_TERMINATOR):
                    response_str = response_str[:-1]
                return response_str
            except asyncio.TimeoutError:
                logger.debug("KPA500 RX: <timeout>")
                return None

    async def _get_command(self, command: str) -> Optional[str]:
        """Send a GET command and return the response data portion."""
        response = await self._send_command(command)
        if response and response.startswith(command):
            return response[len(command):]
        return response

    async def _set_command(self, command: str, data: str) -> bool:
        """
        Send a SET command and verify it was accepted.

        KPA500 set commands do not return a response, so we send the set command
        then follow up with a get command to verify the value was set.

        Retries up to retry_count times with retry_interval delay between attempts.
        """
        for attempt in range(self._retry_count):
            # Send the set command (no response expected)
            await self._send_command(command, data, wait_response=False)
            # Verify by reading back with a get command
            response = await self._get_command(command)
            if response == data:
                return True
            if attempt < self._retry_count - 1:
                await asyncio.sleep(self._retry_interval)

        return False

    # Power Control

    async def get_power_state(self) -> Optional[PowerState]:
        """Get current power state."""
        response = await self._get_command("ON")
        if response:
            return PowerState(int(response))
        return None

    async def set_power_state(self, state: PowerState) -> bool:
        """Set power state (turn on/off)."""
        result = await self._set_command("ON", str(state.value))
        if result:
            self._power_on = state == PowerState.ON
        return result

    async def power_on(self) -> bool:
        """
        Turn the KPA500 on.

        If the device is in bootloader mode, sends the 'P' command to power on,
        then polls for the device to become responsive.

        Returns:
            True if power on succeeded, False otherwise
        """
        # If already powered on, use normal command
        if self._power_on:
            return await self.set_power_state(PowerState.ON)

        # In bootloader mode, send 'P' to power on
        async with self._lock:
            self._writer.write(b'P')
            await self._writer.drain()

        # Poll for device to become responsive (12 attempts, 0.25s each = 3s total)
        for _ in range(12):
            await asyncio.sleep(0.25)
            try:
                response = await self._send_command("ON", timeout=0.25)
                if response and response.startswith("ON"):
                    self._power_on = True
                    return True
            except asyncio.TimeoutError:
                continue

        return False

    async def power_off(self) -> bool:
        """Turn the KPA500 off."""
        return await self.set_power_state(PowerState.OFF)

    # Operating Mode

    async def get_operating_mode(self) -> Optional[OperatingMode]:
        """Get current operating mode (Standby/Operate)."""
        response = await self._get_command("OS")
        if response:
            return OperatingMode(int(response))
        return None

    async def set_operating_mode(self, mode: OperatingMode) -> bool:
        """Set operating mode."""
        return await self._set_command("OS", str(mode.value))

    async def set_standby(self) -> bool:
        """Put amplifier in standby mode."""
        return await self.set_operating_mode(OperatingMode.STANDBY)

    async def set_operate(self) -> bool:
        """Put amplifier in operate mode."""
        return await self.set_operating_mode(OperatingMode.OPERATE)

    # Band Control

    async def get_band(self) -> Optional[Band]:
        """Get current band selection."""
        response = await self._get_command("BN")
        if response:
            return Band(int(response))
        return None

    async def set_band(self, band: Band) -> bool:
        """Set band selection."""
        return await self._set_command("BN", f"{band.value:02d}")

    # ALC Control

    async def get_alc(self) -> Optional[int]:
        """Get ALC threshold setting (0-210)."""
        response = await self._get_command("AL")
        if response:
            return int(response)
        return None

    async def set_alc(self, value: int) -> bool:
        """Set ALC threshold (0-210)."""
        if not 0 <= value <= 210:
            raise ValueError("ALC value must be between 0 and 210")
        return await self._set_command("AL", f"{value:03d}")

    # Fan Control

    async def get_fan_speed(self) -> Optional[FanSpeed]:
        """Get minimum fan speed setting."""
        response = await self._get_command("FC")
        if response:
            return FanSpeed(int(response))
        return None

    async def set_fan_speed(self, speed: FanSpeed) -> bool:
        """Set minimum fan speed."""
        return await self._set_command("FC", str(speed.value))

    # Speaker Control

    async def get_speaker(self) -> Optional[bool]:
        """Get speaker on/off state."""
        response = await self._get_command("SP")
        if response:
            return response == "1"
        return None

    async def set_speaker(self, enabled: bool) -> bool:
        """Set speaker on/off."""
        return await self._set_command("SP", "1" if enabled else "0")

    # T/R Delay

    async def get_tr_delay(self) -> Optional[int]:
        """Get T/R delay time in milliseconds."""
        response = await self._get_command("TR")
        if response:
            return int(response)
        return None

    async def set_tr_delay(self, delay_ms: int) -> bool:
        """Set T/R delay time in milliseconds (0-50)."""
        if not 0 <= delay_ms <= 50:
            raise ValueError("T/R delay must be between 0 and 50 ms")
        return await self._set_command("TR", f"{delay_ms:02d}")

    # Fault Handling

    async def get_fault(self) -> Optional[Fault]:
        """Get current fault code."""
        response = await self._get_command("FL")
        if response:
            return Fault(int(response))
        return None

    async def clear_fault(self) -> bool:
        """Clear current fault."""
        response = await self._send_command("FL", "C")
        return response is not None

    # Readings

    async def get_power_swr(self) -> Optional[PowerSWR]:
        """
        Get current power output and SWR.

        Returns:
            PowerSWR with power in watts and SWR ratio
        """
        response = await self._get_command("WS")
        if response:
            # Format: WSppppss; where pppp=power, ss=SWR*10
            power = int(response[:4])
            swr_raw = int(response[4:])
            swr = swr_raw / 10.0
            return PowerSWR(power_watts=power, swr=swr)
        return None

    async def get_temperature(self) -> Optional[int]:
        """Get PA heatsink temperature in degrees Celsius."""
        response = await self._get_command("TM")
        if response:
            return int(response)
        return None

    async def get_voltage_current(self) -> Optional[VoltageCurrentReading]:
        """
        Get PA voltage and current.

        Returns:
            VoltageCurrentReading with voltage in volts and current in amps
        """
        response = await self._get_command("VI")
        if response:
            # Format: VIvvvcc; where vvv=voltage*10, cc=current*10
            voltage_raw = int(response[:3])
            current_raw = int(response[3:])
            return VoltageCurrentReading(
                voltage=voltage_raw / 10.0,
                current=current_raw / 10.0
            )
        return None

    # Device Information

    async def get_serial_number(self) -> Optional[str]:
        """Get device serial number."""
        return await self._get_command("SN")

    async def get_firmware_version(self) -> Optional[str]:
        """Get firmware version."""
        return await self._get_command("RVM")

    # Baud Rate

    async def get_pc_baudrate(self) -> Optional[BaudRate]:
        """Get PC port baud rate setting."""
        response = await self._get_command("BRP")
        if response:
            return BaudRate(int(response))
        return None

    async def set_pc_baudrate(self, rate: BaudRate) -> bool:
        """Set PC port baud rate."""
        return await self._set_command("BRP", str(rate.value))

    async def get_xcvr_baudrate(self) -> Optional[BaudRate]:
        """Get transceiver port baud rate setting."""
        response = await self._get_command("BRX")
        if response:
            return BaudRate(int(response))
        return None

    async def set_xcvr_baudrate(self, rate: BaudRate) -> bool:
        """Set transceiver port baud rate."""
        return await self._set_command("BRX", str(rate.value))

    # Radio Interface

    async def get_radio_interface(self) -> Optional[RadioInterface]:
        """Get radio interface selection."""
        response = await self._get_command("XI")
        if response:
            return RadioInterface(int(response))
        return None

    async def set_radio_interface(self, interface: RadioInterface) -> bool:
        """Set radio interface selection."""
        return await self._set_command("XI", str(interface.value))

    # Standby on Band Change

    async def get_standby_on_band_change(self) -> Optional[bool]:
        """Get standby on band change setting."""
        response = await self._get_command("BC")
        if response:
            return response == "1"
        return None

    async def set_standby_on_band_change(self, enabled: bool) -> bool:
        """Set standby on band change."""
        return await self._set_command("BC", "1" if enabled else "0")

    # Connection Management

    async def close(self) -> None:
        """Close the serial connection."""
        self._writer.close()
        await self._writer.wait_closed()

    async def ping(self) -> bool:
        """
        Ping the KPA500 to check if it's responding.

        Returns:
            True if device responds, False otherwise
        """
        # Send null command (just semicolon) - KPA500 echoes it back
        async with self._lock:
            self._writer.write(b';')
            await self._writer.drain()
            try:
                response = await asyncio.wait_for(
                    self._reader.read(1),
                    timeout=self._timeout
                )
                return response == b';'
            except asyncio.TimeoutError:
                return False


