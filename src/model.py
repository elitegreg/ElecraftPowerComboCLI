"""
Power Combo Application Model

Bridges the TUI with the KPA500 and KAT500 hardware interfaces.
Periodically polls the devices and updates state that the TUI observes.

KAT500 Sleep Strategy:
- KAT500 sleep mode is enabled on connection to save power
- KAT500 is only polled:
  1. Once on startup
  2. Every kat_poll_interval seconds (default 30s) as a background refresh
  3. At the KPA poll rate, but ONLY when KPA indicates transmission (SWR > 1.0)
- This allows KAT500 to sleep during receive periods
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Optional, Callable

logger = logging.getLogger(__name__)

from kpa500 import (
    KPA500,
    Band,
    OperatingMode,
    PowerState,
)
from kpa500 import Fault as KPAFault

from kat500 import (
    KAT500,
    Antenna,
    Mode as KATMode,
)
from kat500 import Fault as KATFault


@dataclass
class ComboState:
    """Current state of the KPA500/KAT500 combo."""
    # Connection state
    kpa_connected: bool = False
    kat_connected: bool = False

    # Combined power state (True if both devices are on)
    powered_on: bool = False

    # KPA500 state
    kpa_operating_mode: Optional[OperatingMode] = None
    band: Optional[Band] = None
    power_watts: int = 0
    kpa_swr: float = 1.0
    temperature: Optional[int] = None
    voltage: Optional[float] = None
    current: Optional[float] = None
    kpa_fault: Optional[KPAFault] = None

    # KAT500 state
    kat_mode: Optional[KATMode] = None
    antenna: Optional[Antenna] = None
    kat_swr: float = 1.0
    kat_swr_bypass: Optional[float] = None
    forward_power: Optional[int] = None
    reflected_power: Optional[int] = None
    kat_fault: Optional[KATFault] = None
    is_tuning: bool = False


class ComboModel:
    """
    Application model for KPA500/KAT500 combo control.

    Manages connections to both devices, periodic polling, and state updates.
    The TUI observes state changes via the on_state_change callback.
    """

    def __init__(
        self,
        kpa_poll_interval: float = 0.25,
        kat_poll_interval: float = 30.0,
        on_state_change: Optional[Callable[[ComboState], None]] = None
    ):
        """
        Initialize the model.

        Args:
            kpa_poll_interval: How often to poll KPA500 (seconds)
            kat_poll_interval: How often to poll KAT500 in background (seconds)
            on_state_change: Callback when state changes
        """
        self._kpa_poll_interval = kpa_poll_interval
        self._kat_poll_interval = kat_poll_interval
        self._on_state_change = on_state_change
        self._kpa: Optional[KPA500] = None
        self._kat: Optional[KAT500] = None
        self._state = ComboState()
        self._poll_task: Optional[asyncio.Task] = None
        self._running = False
        self._last_kat_poll: float = 0.0

    @property
    def state(self) -> ComboState:
        """Get current state."""
        return self._state

    def _notify_change(self) -> None:
        """Notify listener of state change."""
        if self._on_state_change:
            self._on_state_change(self._state)

    async def connect(
        self,
        kpa_port: Optional[str] = None,
        kat_port: Optional[str] = None,
        baudrate: int = 38400
    ) -> bool:
        """
        Connect to the KPA500 and/or KAT500.

        After connecting:
        - KAT500 sleep mode is enabled
        - If one device is powered on, the other is powered on too
        - Initial KAT500 state is queried

        Args:
            kpa_port: Serial port for KPA500 (None to skip)
            kat_port: Serial port for KAT500 (None to skip)
            baudrate: Baud rate

        Returns:
            True if at least one device connected successfully
        """
        kpa_powered = False
        kat_powered = False

        # Connect to KPA500
        if kpa_port:
            try:
                logger.info("Connecting to KPA500 on %s", kpa_port)
                self._kpa = await KPA500.from_serial_port(kpa_port, baudrate=baudrate)
                self._state.kpa_connected = True
                kpa_powered = self._kpa.is_powered_on or False
                logger.info("KPA500 connected, powered_on=%s", kpa_powered)
            except Exception as e:
                logger.error("KPA500 connection failed: %s", e)
                self._state.kpa_connected = False

        # Connect to KAT500
        if kat_port:
            try:
                logger.info("Connecting to KAT500 on %s", kat_port)
                self._kat = await KAT500.from_serial_port(kat_port, baudrate=baudrate)
                self._state.kat_connected = True

                # Enable sleep mode on KAT500
                await self._kat.wake()
                await self._kat.set_sleep_enabled(True)
                sleep_enabled = await self._kat.get_sleep_enabled()
                if not sleep_enabled:
                    logger.warning("Failed to enable KAT500 sleep mode")

                # Check power state
                power_state = await self._kat.get_power_state()
                kat_powered = power_state == PowerState.ON if power_state else False
                logger.info("KAT500 connected, powered_on=%s", kat_powered)

            except Exception as e:
                logger.error("KAT500 connection failed: %s", e)
                self._state.kat_connected = False

        # Synchronize power state: if one is on, turn both on
        if self._state.kpa_connected and self._state.kat_connected:
            if kpa_powered and not kat_powered:
                # KPA is on, turn on KAT
                await self._kat.power_on()
                kat_powered = True
            elif kat_powered and not kpa_powered:
                # KAT is on, turn on KPA
                await self._kpa.power_on()
                kpa_powered = True

        # Set combined power state
        if self._state.kpa_connected and self._state.kat_connected:
            self._state.powered_on = kpa_powered and kat_powered
        elif self._state.kpa_connected:
            self._state.powered_on = kpa_powered
        elif self._state.kat_connected:
            self._state.powered_on = kat_powered

        # Initial KAT500 poll if connected and powered
        if self._state.kat_connected and self._state.powered_on:
            await self._poll_kat()
            self._last_kat_poll = time.monotonic()

        self._notify_change()
        return self._state.kpa_connected or self._state.kat_connected

    async def disconnect(self) -> None:
        """Disconnect from both devices."""
        await self.stop_polling()
        if self._kpa:
            await self._kpa.close()
            self._kpa = None
        if self._kat:
            await self._kat.close()
            self._kat = None
        self._state = ComboState()
        self._notify_change()

    async def start_polling(self) -> None:
        """Start periodic polling of the devices."""
        if self._running:
            return
        self._running = True
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop_polling(self) -> None:
        """Stop periodic polling."""
        self._running = False
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

    async def _poll_loop(self) -> None:
        """Main polling loop."""
        while self._running:
            await self._poll_once()
            await asyncio.sleep(self._kpa_poll_interval)

    async def _poll_once(self) -> None:
        """Poll devices once and update state."""
        # Always poll KPA500
        await self._poll_kpa()

        # Determine if we should poll KAT500
        should_poll_kat = False
        now = time.monotonic()

        # Poll KAT if background interval has elapsed
        if now - self._last_kat_poll >= self._kat_poll_interval:
            should_poll_kat = True

        # Poll KAT if KPA indicates transmission (SWR > 1.0 means RF is present)
        if self._state.kpa_swr > 1.0:
            should_poll_kat = True

        if should_poll_kat and self._state.kat_connected and self._state.powered_on:
            await self._poll_kat()
            self._last_kat_poll = now

        self._notify_change()

    async def _poll_kpa(self) -> None:
        """Poll the KPA500 and update state."""
        if not self._kpa or not self._state.kpa_connected:
            return

        try:
            power_state = await self._kpa.get_power_state()
            if power_state is None:
                # No response - device may be off or in bootloader
                if self._state.powered_on:
                    self._state.powered_on = False
                return

            kpa_powered = power_state == PowerState.ON

            if not kpa_powered:
                if self._state.powered_on:
                    self._state.powered_on = False
                return

            # Update combined power state
            self._state.powered_on = True

            self._state.kpa_operating_mode = await self._kpa.get_operating_mode()
            self._state.band = await self._kpa.get_band()

            power_swr = await self._kpa.get_power_swr()
            if power_swr:
                self._state.power_watts = power_swr.power_watts
                self._state.kpa_swr = power_swr.swr

            self._state.temperature = await self._kpa.get_temperature()

            vi = await self._kpa.get_voltage_current()
            if vi:
                self._state.voltage = vi.voltage
                self._state.current = vi.current

            self._state.kpa_fault = await self._kpa.get_fault()

        except Exception as e:
            logger.debug("KPA500 poll error: %s", e)

    async def _poll_kat(self) -> None:
        """Poll the KAT500 and update state."""
        if not self._kat or not self._state.kat_connected:
            return

        try:
            # Wake KAT from sleep if needed (send semicolons)
            await self._kat.wake()

            self._state.kat_mode = await self._kat.get_mode()
            self._state.antenna = await self._kat.get_antenna()
            self._state.kat_swr = await self._kat.get_vswr() or 1.0
            self._state.kat_swr_bypass = await self._kat.get_vswr_bypass()
            self._state.forward_power = await self._kat.get_forward_voltage()
            self._state.reflected_power = await self._kat.get_reflected_voltage()
            self._state.kat_fault = await self._kat.get_fault()
            self._state.is_tuning = await self._kat.is_tuning()

        except Exception as e:
            logger.debug("KAT500 poll error: %s", e)

    # =========================================================================
    # Combined Power Control
    # =========================================================================

    async def power_on(self) -> bool:
        """Turn both devices on."""
        logger.info("Powering on devices")
        success = True

        if self._kpa and self._state.kpa_connected:
            logger.info("Powering on KPA500")
            if not await self._kpa.power_on():
                logger.error("Failed to power on KPA500")
                success = False

        if self._kat and self._state.kat_connected:
            logger.info("Powering on KAT500")
            # Wake from sleep first
            await self._kat.wake()
            if not await self._kat.power_on():
                logger.error("Failed to power on KAT500")
                success = False

        if success:
            logger.info("Devices powered on successfully")
            self._state.powered_on = True
            # Do initial KAT poll after power on
            if self._state.kat_connected:
                await self._poll_kat()
                self._last_kat_poll = time.monotonic()
            self._notify_change()

        return success

    async def power_off(self) -> bool:
        """Turn both devices off."""
        logger.info("Powering off devices")
        success = True

        if self._kpa and self._state.kpa_connected:
            logger.info("Powering off KPA500")
            # Put KPA in standby first
            await self._kpa.set_standby()
            if not await self._kpa.power_off():
                logger.error("Failed to power off KPA500")
                success = False

        if self._kat and self._state.kat_connected:
            logger.info("Powering off KAT500")
            if not await self._kat.power_off():
                logger.error("Failed to power off KAT500")
                success = False

        if success:
            logger.info("Devices powered off successfully")
            self._state.powered_on = False
            self._notify_change()

        return success

    async def toggle_power(self) -> bool:
        """Toggle combined power state."""
        if self._state.powered_on:
            return await self.power_off()
        else:
            return await self.power_on()

    # =========================================================================
    # KPA500 Control Methods
    # =========================================================================

    async def kpa_set_standby(self) -> bool:
        """Set KPA500 to standby mode."""
        if not self._kpa or not self._state.powered_on:
            return False
        logger.info("Setting KPA500 to standby")
        result = await self._kpa.set_standby()
        if result:
            self._state.kpa_operating_mode = OperatingMode.STANDBY
            self._notify_change()
        else:
            logger.error("Failed to set KPA500 to standby")
        return result

    async def kpa_set_operate(self) -> bool:
        """Set KPA500 to operate mode."""
        if not self._kpa or not self._state.powered_on:
            return False
        logger.info("Setting KPA500 to operate")
        result = await self._kpa.set_operate()
        if result:
            self._state.kpa_operating_mode = OperatingMode.OPERATE
            self._notify_change()
        else:
            logger.error("Failed to set KPA500 to operate")
        return result

    async def kpa_clear_fault(self) -> bool:
        """Clear KPA500 fault."""
        if not self._kpa or not self._state.powered_on:
            return False
        logger.info("Clearing KPA500 fault")
        result = await self._kpa.clear_fault()
        if result:
            self._state.kpa_fault = KPAFault.NONE
            self._notify_change()
        else:
            logger.error("Failed to clear KPA500 fault")
        return result

    # =========================================================================
    # KAT500 Control Methods
    # =========================================================================

    async def kat_set_mode(self, mode: KATMode) -> bool:
        """Set KAT500 operating mode (Auto/Manual/Bypass)."""
        if not self._kat or not self._state.powered_on:
            return False
        logger.info("Setting KAT500 mode to %s", mode.name)
        # Wake from sleep first if needed
        await self._kat.wake()
        result = await self._kat.set_mode(mode)
        if result:
            self._state.kat_mode = mode
            self._notify_change()
        else:
            logger.error("Failed to set KAT500 mode to %s", mode.name)
        return result

    async def kat_set_antenna(self, antenna: Antenna) -> bool:
        """Set KAT500 antenna."""
        if not self._kat or not self._state.powered_on:
            return False
        logger.info("Setting KAT500 antenna to %s", antenna.name)
        # Wake from sleep first if needed
        await self._kat.wake()
        result = await self._kat.set_antenna(antenna)
        if result:
            self._state.antenna = antenna
            self._notify_change()
        else:
            logger.error("Failed to set KAT500 antenna to %s", antenna.name)
        return result

    async def kat_full_tune(self) -> bool:
        """
        Start KAT500 full tune sequence.

        This puts the KPA500 in standby first, then initiates a full tune
        on the KAT500. The is_tuning state will be updated by polling.
        """
        logger.info("Starting full tune sequence")
        if not self._state.powered_on:
            logger.warning("Full tune aborted: devices not powered on")
            return False

        # Put KPA in standby first if connected
        if self._kpa and self._state.kpa_connected:
            logger.info("Setting KPA500 to standby before tune")
            standby_result = await self._kpa.set_standby()
            if not standby_result:
                logger.error("Failed to set KPA500 to standby")
                return False
            self._state.kpa_operating_mode = OperatingMode.STANDBY
            logger.debug("KPA500 standby complete")

        # Start KAT tune if connected
        if self._kat and self._state.kat_connected:
            logger.debug("Waking KAT500")
            # Wake from sleep first if needed
            await self._kat.wake()
            # Retry full_tune up to 3 times
            for attempt in range(3):
                logger.info("Initiating KAT500 full tune (attempt %d)", attempt + 1)
                result = await self._kat.full_tune()
                if result:
                    logger.info("Full tune started successfully")
                    self._state.is_tuning = True
                    self._notify_change()
                    return True
                if attempt < 2:
                    await asyncio.sleep(0.1)  # Brief delay before retry
            logger.error("Full tune failed after 3 attempts")
            return False

        return False

    async def kat_clear_fault(self) -> bool:
        """Clear KAT500 fault."""
        if not self._kat or not self._state.powered_on:
            return False
        logger.info("Clearing KAT500 fault")
        # Wake from sleep first if needed
        await self._kat.wake()
        result = await self._kat.clear_fault()
        if result:
            self._state.kat_fault = KATFault.NONE
            self._notify_change()
        else:
            logger.error("Failed to clear KAT500 fault")
        return result
