#!/usr/bin/env python3
"""
KAT500 Automatic Antenna Tuner Serial Interface Module

Async interface for controlling the Elecraft KAT500 antenna tuner via serial port.
Based on KAT500 Serial Command Reference documentation.
"""

import asyncio
import logging
from enum import IntEnum, Enum
from dataclasses import dataclass
from typing import Optional, Self
import serial_asyncio_fast

logger = logging.getLogger(__name__)


class Band(IntEnum):
    """KAT500 band selection values."""
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


class Mode(Enum):
    """KAT500 operating mode."""
    BYPASS = "B"
    MANUAL = "M"
    AUTO = "A"


class PowerState(IntEnum):
    """KAT500 power state."""
    OFF = 0
    ON = 1


class BaudRate(IntEnum):
    """Serial baud rate settings."""
    BAUD_4800 = 0
    BAUD_9600 = 1
    BAUD_19200 = 2
    BAUD_38400 = 3


class Fault(IntEnum):
    """KAT500 fault codes."""
    NONE = 0
    NO_MATCH = 1
    POWER_ABOVE_DESIGN_LIMIT = 2
    POWER_ABOVE_RELAY_SWITCH_LIMIT = 3


class Antenna(IntEnum):
    """Antenna selection."""
    ANT1 = 1
    ANT2 = 2
    ANT3 = 3


class Side(Enum):
    """Tuner network topology."""
    TRANSMITTER = "T"  # CL network (capacitor on transmitter side)
    ANTENNA = "A"      # LC network (inductor on transmitter side)


class BypassState(Enum):
    """Bypass relay state."""
    NOT_BYPASSED = "N"
    BYPASSED = "B"


@dataclass
class VSWRReading:
    """VSWR reading from the KAT500."""
    vswr: float


@dataclass
class CouplerReading:
    """Forward and reflected coupler voltage readings."""
    forward: int   # ADC count 0-4095
    reflected: int  # ADC count 0-4095


class KAT500:
    """
    Async interface for the Elecraft KAT500 automatic antenna tuner.

    This class provides methods to control and monitor the KAT500 tuner
    via its serial command protocol.
    """

    DEFAULT_BAUDRATE = 38400
    DEFAULT_TIMEOUT = 0.1
    DEFAULT_RETRY_COUNT = 3
    DEFAULT_RETRY_INTERVAL = 0.1
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
        Initialize KAT500 interface with async streams.

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
        Create KAT500 interface from a serial port.

        Args:
            port: Serial port path (e.g., '/dev/ttyUSB0' or 'COM3')
            baudrate: Baud rate (default 38400)
            timeout: Command timeout in seconds
            retry_count: Number of retries for set commands
            retry_interval: Interval between retries in seconds

        Returns:
            Configured KAT500 instance
        """
        reader, writer = await serial_asyncio_fast.open_serial_connection(
            url=port,
            baudrate=baudrate,
            bytesize=8,
            parity='N',
            stopbits=1
        )

        return cls(reader, writer, timeout, retry_count, retry_interval)

    async def _send_command(
        self,
        command: str,
        data: str = "",
        timeout: Optional[float] = None
    ) -> Optional[str]:
        """
        Send a command to the KAT500 and optionally wait for response.

        Args:
            command: Command (e.g., "PS", "BN")
            data: Optional data to append to command
            timeout: Override default timeout

        Returns:
            Response string without terminator, or None if no response
        """
        timeout = timeout if timeout is not None else self._timeout
        full_command = f"{command}{data}{self.COMMAND_TERMINATOR}"

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
            logger.debug("KAT500 TX: %s", full_command)
            self._writer.write(full_command.encode('ascii'))
            await self._writer.drain()

            # Wait for response
            try:
                response = await asyncio.wait_for(
                    self._reader.readuntil(b';'),
                    timeout=timeout
                )
                response_str = response.decode('ascii').strip()
                logger.debug("KAT500 RX: %s", response_str)
                if response_str.endswith(self.COMMAND_TERMINATOR):
                    response_str = response_str[:-1]
                return response_str
            except asyncio.TimeoutError:
                logger.debug("KAT500 RX: <timeout>")
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

        Retries up to retry_count times with retry_interval delay between attempts.
        """
        expected = f"{command}{data}"
        for attempt in range(self._retry_count):
            response = await self._send_command(command, data)
            if response == expected:
                return True
            if attempt < self._retry_count - 1:
                await asyncio.sleep(self._retry_interval)
        return False

    # =========================================================================
    # Power Control
    # =========================================================================

    async def get_power_state(self) -> Optional[PowerState]:
        """Get current power state."""
        response = await self._get_command("PS")
        if response:
            return PowerState(int(response))
        return None

    async def set_power_state(self, state: PowerState) -> bool:
        """Set power state (turn on/off)."""
        return await self._set_command("PS", str(state.value))

    async def power_on(self) -> bool:
        """Turn the KAT500 on."""
        return await self.set_power_state(PowerState.ON)

    async def power_off(self) -> bool:
        """Turn the KAT500 off."""
        return await self.set_power_state(PowerState.OFF)

    async def get_initial_power_state(self) -> Optional[PowerState]:
        """Get power state at startup (PSI)."""
        response = await self._get_command("PSI")
        if response:
            return PowerState(int(response))
        return None

    async def set_initial_power_state(self, state: PowerState) -> bool:
        """Set power state at startup (PSI)."""
        return await self._set_command("PSI", str(state.value))

    # =========================================================================
    # Mode Control
    # =========================================================================

    async def get_mode(self) -> Optional[Mode]:
        """Get current operating mode (Bypass/Manual/Auto)."""
        response = await self._get_command("MD")
        if response:
            return Mode(response)
        return None

    async def set_mode(self, mode: Mode) -> bool:
        """Set operating mode."""
        return await self._set_command("MD", mode.value)

    async def set_bypass_mode(self) -> bool:
        """Set tuner to bypass mode."""
        return await self.set_mode(Mode.BYPASS)

    async def set_manual_mode(self) -> bool:
        """Set tuner to manual mode."""
        return await self.set_mode(Mode.MANUAL)

    async def set_auto_mode(self) -> bool:
        """Set tuner to automatic mode."""
        return await self.set_mode(Mode.AUTO)

    # =========================================================================
    # Band Control
    # =========================================================================

    async def get_band(self) -> Optional[Band]:
        """Get current band selection."""
        response = await self._get_command("BN")
        if response:
            return Band(int(response))
        return None

    async def set_band(self, band: Band) -> bool:
        """Set band selection."""
        return await self._set_command("BN", f"{band.value:02d}")

    # =========================================================================
    # Antenna Control
    # =========================================================================

    async def get_antenna(self) -> Optional[Antenna]:
        """Get current antenna selection."""
        response = await self._get_command("AN")
        if response:
            return Antenna(int(response))
        return None

    async def set_antenna(self, antenna: Antenna) -> bool:
        """Set antenna selection."""
        return await self._set_command("AN", str(antenna.value))

    async def next_antenna(self) -> bool:
        """Advance to next enabled antenna (simulates ANT button press)."""
        response = await self._send_command("AN", "0")
        return response is not None

    async def get_antenna_preference(self, band: Band) -> Optional[int]:
        """
        Get preferred antenna for a band.

        Returns:
            0 = last used, 1-3 = specific antenna
        """
        response = await self._send_command("AP", f"{band.value:02d}")
        if response and response.startswith("AP"):
            # Response format: APbba where bb=band, a=antenna
            return int(response[-1])
        return None

    async def set_antenna_preference(self, band: Band, antenna: int) -> bool:
        """
        Set preferred antenna for a band.

        Args:
            band: Band to configure
            antenna: 0 = last used, 1-3 = specific antenna
        """
        if not 0 <= antenna <= 3:
            raise ValueError("Antenna preference must be 0-3")
        response = await self._send_command("AP", f"{band.value:02d}{antenna}")
        expected = f"AP{band.value:02d}{antenna}"
        return response == expected

    async def get_antenna_enabled(self, band: Band, antenna: Antenna) -> Optional[bool]:
        """Check if antenna is enabled for a band."""
        response = await self._send_command("AE", f"{band.value:02d}{antenna.value}")
        if response and response.startswith("AE"):
            # Response format: AEbba0 or AEbba1
            return response[-1] == "1"
        return None

    async def set_antenna_enabled(
        self, band: Band, antenna: Antenna, enabled: bool
    ) -> bool:
        """Enable or disable antenna for a band."""
        value = "1" if enabled else "0"
        response = await self._send_command(
            "AE", f"{band.value:02d}{antenna.value}{value}"
        )
        expected = f"AE{band.value:02d}{antenna.value}{value}"
        return response == expected

    # =========================================================================
    # Bypass Control
    # =========================================================================

    async def get_bypass(self) -> Optional[BypassState]:
        """Get bypass relay state."""
        response = await self._get_command("BYP")
        if response:
            return BypassState(response)
        return None

    async def set_bypass(self, state: BypassState) -> bool:
        """Set bypass relay state."""
        return await self._set_command("BYP", state.value)

    # =========================================================================
    # Tuning Control
    # =========================================================================

    async def tune(self) -> bool:
        """
        Start a tune operation (equivalent to pressing TUNE button).

        Returns:
            True if tune was initiated successfully
        """
        await self._send_command("T")
        # Verify tuning actually started
        return await self.is_tuning()

    async def is_tuning(self) -> bool:
        """
        Check if currently tuning.

        Returns:
            True if tuning in progress
        """
        response = await self._get_command("TP")
        return response == "1"

    async def full_tune(self) -> bool:
        """
        Start a full tune (searches for best match).

        Returns:
            True if full tune was initiated successfully
        """
        await self._send_command("FT")
        # Verify tuning actually started
        return await self.is_tuning()

    async def memory_tune(self, frequency_khz: Optional[int] = None) -> bool:
        """
        Start a memory recall tune.

        Args:
            frequency_khz: Frequency in kHz, or None for last transmit frequency
        """
        if frequency_khz is not None:
            data = f" {frequency_khz}"
        else:
            data = ""
        response = await self._send_command("MT", data)
        return response is not None

    async def set_frequency(self, frequency_khz: int) -> bool:
        """
        Recall tuner settings for a frequency without transmitting.

        Args:
            frequency_khz: Frequency in kHz
        """
        response = await self._send_command("F", f" {frequency_khz}")
        return response is not None

    async def get_frequency(self) -> Optional[int]:
        """Get last transmit frequency in kHz."""
        response = await self._get_command("F")
        if response:
            return int(response.strip())
        return None

    async def save_memory(self, frequency_khz: Optional[int] = None) -> bool:
        """
        Save current tuner settings to memory.

        Args:
            frequency_khz: Frequency in kHz, or None for last transmit frequency
        """
        if frequency_khz is not None:
            data = f" {frequency_khz}"
        else:
            data = ""
        response = await self._send_command("SM", data)
        return response is not None

    # =========================================================================
    # Tuner Network Control
    # =========================================================================

    async def get_side(self) -> Optional[Side]:
        """Get tuner network topology (transmitter or antenna side)."""
        response = await self._get_command("SIDE")
        if response:
            return Side(response)
        return None

    async def set_side(self, side: Side) -> bool:
        """Set tuner network topology."""
        return await self._set_command("SIDE", side.value)

    async def get_inductors(self) -> Optional[int]:
        """
        Get current inductor selection as hex value.

        Returns:
            Hex value 0x00-0xFF representing inductor relay states
        """
        response = await self._get_command("L")
        if response:
            return int(response, 16)
        return None

    async def set_inductors(self, value: int) -> bool:
        """
        Set inductor selection.

        Args:
            value: Hex value 0x00-0xFF for inductor relay states
        """
        if not 0 <= value <= 0xFF:
            raise ValueError("Inductor value must be 0x00-0xFF")
        return await self._set_command("L", f"{value:02X}")

    async def get_capacitors(self) -> Optional[int]:
        """
        Get current capacitor selection as hex value.

        Returns:
            Hex value 0x00-0xFF representing capacitor relay states
        """
        response = await self._get_command("C")
        if response:
            return int(response, 16)
        return None

    async def set_capacitors(self, value: int) -> bool:
        """
        Set capacitor selection.

        Args:
            value: Hex value 0x00-0xFF for capacitor relay states
        """
        if not 0 <= value <= 0xFF:
            raise ValueError("Capacitor value must be 0x00-0xFF")
        return await self._set_command("C", f"{value:02X}")

    # =========================================================================
    # Fault Handling
    # =========================================================================

    async def get_fault(self) -> Optional[Fault]:
        """Get current fault code."""
        response = await self._get_command("FLT")
        if response:
            return Fault(int(response))
        return None

    async def clear_fault(self) -> bool:
        """Clear current fault."""
        response = await self._send_command("FLTC")
        return response is not None

    # =========================================================================
    # VSWR and Power Readings
    # =========================================================================

    async def get_vswr(self) -> Optional[float]:
        """Get current VSWR reading."""
        response = await self._get_command("VSWR")
        if response:
            return float(response.strip())
        return None

    async def get_vswr_bypass(self) -> Optional[float]:
        """Get VSWR measured in bypass mode (no tuner in circuit)."""
        response = await self._get_command("VSWRB")
        if response:
            return float(response.strip())
        return None

    async def get_forward_voltage(self) -> Optional[int]:
        """Get forward coupler voltage ADC count (0-4095)."""
        response = await self._get_command("VFWD")
        if response:
            return int(response.strip())
        return None

    async def get_reflected_voltage(self) -> Optional[int]:
        """Get reflected coupler voltage ADC count (0-4095)."""
        response = await self._get_command("VRFL")
        if response:
            return int(response.strip())
        return None

    # =========================================================================
    # SWR Thresholds
    # =========================================================================

    async def get_auto_tune_threshold(self, band: Band) -> Optional[float]:
        """Get auto tune VSWR threshold for a band."""
        response = await self._send_command("ST", f"{band.value:02d}A")
        if response and response.startswith("ST"):
            # Response format: STbbAn.nn
            return float(response[5:])
        return None

    async def set_auto_tune_threshold(self, band: Band, vswr: float) -> bool:
        """
        Set auto tune VSWR threshold for a band.

        Args:
            band: Band to configure
            vswr: VSWR threshold (minimum 1.5, default 1.8)
        """
        if vswr < 1.5:
            raise ValueError("Auto tune threshold minimum is 1.5")
        response = await self._send_command("ST", f"{band.value:02d}A{vswr:.2f}")
        return response is not None

    async def get_bypass_threshold(self, band: Band) -> Optional[float]:
        """Get bypass VSWR threshold for a band."""
        response = await self._send_command("ST", f"{band.value:02d}B")
        if response and response.startswith("ST"):
            return float(response[5:])
        return None

    async def set_bypass_threshold(self, band: Band, vswr: float) -> bool:
        """Set bypass VSWR threshold for a band."""
        response = await self._send_command("ST", f"{band.value:02d}B{vswr:.2f}")
        return response is not None

    async def get_key_interrupt_threshold(self, band: Band) -> Optional[float]:
        """Get amplifier key interrupt VSWR threshold for a band."""
        response = await self._send_command("ST", f"{band.value:02d}K")
        if response and response.startswith("ST"):
            return float(response[5:])
        return None

    async def set_key_interrupt_threshold(self, band: Band, vswr: float) -> bool:
        """Set amplifier key interrupt VSWR threshold for a band."""
        response = await self._send_command("ST", f"{band.value:02d}K{vswr:.2f}")
        return response is not None

    # =========================================================================
    # Amplifier Key Interrupt
    # =========================================================================

    async def get_amp_key_interrupt_power(self) -> Optional[int]:
        """Get amplifier key interrupt power threshold in watts."""
        response = await self._get_command("AKIP")
        if response:
            return int(response.strip().split("W")[0])
        return None

    async def set_amp_key_interrupt_power(self, watts: int) -> bool:
        """
        Set amplifier key interrupt power threshold.

        Args:
            watts: Power threshold in watts (1500 = unlimited for KPA500)
        """
        response = await self._send_command("AKIP", f" {watts}")
        return response is not None

    async def get_amp_key_interrupt(self) -> Optional[bool]:
        """Get amplifier key line interrupt state."""
        response = await self._get_command("AMPI")
        if response:
            return response == "1"
        return None

    async def set_amp_key_interrupt(self, interrupted: bool) -> bool:
        """
        Set amplifier key line interrupt state.

        Args:
            interrupted: True to interrupt (disconnect) amplifier key line
        """
        return await self._set_command("AMPI", "1" if interrupted else "0")

    # =========================================================================
    # Attenuator Control
    # =========================================================================

    async def get_attenuator(self) -> Optional[bool]:
        """Get attenuator enabled state."""
        response = await self._get_command("ATTN")
        if response:
            return response == "1"
        return None

    async def set_attenuator(self, enabled: bool) -> bool:
        """Set attenuator enabled state."""
        return await self._set_command("ATTN", "1" if enabled else "0")

    # =========================================================================
    # Memory Control
    # =========================================================================

    async def erase_memory(self, band: Band, antenna: int = 0) -> bool:
        """
        Erase frequency memory for a band.

        Args:
            band: Band to erase
            antenna: 0 = all antennas, 1-3 = specific antenna
        """
        if not 0 <= antenna <= 3:
            raise ValueError("Antenna must be 0-3")
        response = await self._send_command("EM", f"{band.value:02d}{antenna}")
        return response is not None

    async def erase_all_memory(self) -> bool:
        """Erase all configuration and frequency memories (EEINIT)."""
        response = await self._send_command("EEINIT")
        return response is not None

    # =========================================================================
    # Memory Tune Settings
    # =========================================================================

    async def get_auto_memory_tune(self) -> Optional[bool]:
        """Get automatic memory recall tune in AUTO mode setting."""
        response = await self._get_command("MTA")
        if response:
            return response == "1"
        return None

    async def set_auto_memory_tune(self, enabled: bool) -> bool:
        """Set automatic memory recall tune in AUTO mode."""
        return await self._set_command("MTA", "1" if enabled else "0")

    async def get_manual_memory_tune(self) -> Optional[bool]:
        """Get automatic memory recall tune in MAN mode setting."""
        response = await self._get_command("MTM")
        if response:
            return response == "1"
        return None

    async def set_manual_memory_tune(self, enabled: bool) -> bool:
        """Set automatic memory recall tune in MAN mode."""
        return await self._set_command("MTM", "1" if enabled else "0")

    # =========================================================================
    # Sleep Control
    # =========================================================================

    async def get_sleep_enabled(self) -> Optional[bool]:
        """Get sleep when idle setting."""
        response = await self._get_command("SL")
        if response:
            return response == "1"
        return None

    async def set_sleep_enabled(self, enabled: bool) -> bool:
        """Set sleep when idle setting."""
        return await self._set_command("SL", "1" if enabled else "0")

    # =========================================================================
    # Device Information
    # =========================================================================

    async def get_serial_number(self) -> Optional[str]:
        """Get device serial number."""
        response = await self._get_command("SN")
        if response:
            return response.strip()
        return None

    async def get_firmware_version(self) -> Optional[str]:
        """Get firmware version."""
        response = await self._get_command("RV")
        if response:
            return response
        return None

    async def identify(self) -> Optional[str]:
        """Get device identification string."""
        response = await self._get_command("I")
        if response:
            return response
        return None

    # =========================================================================
    # Baud Rate
    # =========================================================================

    async def get_baudrate(self) -> Optional[BaudRate]:
        """Get serial port baud rate setting."""
        response = await self._get_command("BR")
        if response:
            return BaudRate(int(response))
        return None

    async def set_baudrate(self, rate: BaudRate) -> bool:
        """Set serial port baud rate."""
        return await self._set_command("BR", str(rate.value))

    # =========================================================================
    # Reset
    # =========================================================================

    async def reset(self, save_state: bool = True) -> bool:
        """
        Reset the microcontroller.

        Args:
            save_state: If True, save current state to EEPROM before reset
        """
        response = await self._send_command("RST", "1" if save_state else "0")
        return response is not None

    # =========================================================================
    # Connection Management
    # =========================================================================

    async def close(self) -> None:
        """Close the serial connection."""
        self._writer.close()
        await self._writer.wait_closed()

    async def ping(self) -> bool:
        """
        Ping the KAT500 to check if it's responding.

        Returns:
            True if device responds, False otherwise
        """
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

    async def wake(self) -> bool:
        """
        Wake the KAT500 from sleep mode by sending semicolons.

        Returns:
            True if device responds, False otherwise
        """
        for _ in range(10):
            if await self.ping():
                return True
            await asyncio.sleep(0.1)
        return False
