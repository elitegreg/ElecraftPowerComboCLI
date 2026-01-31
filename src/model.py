"""
KPA500 Application Model

Bridges the TUI with the KPA500 hardware interface.
Periodically polls the device and updates state that the TUI observes.
"""

import asyncio
from dataclasses import dataclass, field
from typing import Optional, Callable, Any

from kpa500 import (
    KPA500,
    Band,
    Fault,
    OperatingMode,
    PowerState,
    PowerSWR,
    VoltageCurrentReading,
)


@dataclass
class KPA500State:
    """Current state of the KPA500 amplifier."""
    connected: bool = False
    powered_on: bool = False
    operating_mode: Optional[OperatingMode] = None
    band: Optional[Band] = None
    power_watts: int = 0
    swr: float = 1.0
    temperature: Optional[int] = None
    voltage: Optional[float] = None
    current: Optional[int] = None
    fault: Optional[Fault] = None


class KPA500Model:
    """
    Application model for KPA500 control.

    Manages connection to the KPA500, periodic polling, and state updates.
    The TUI observes state changes via the on_state_change callback.
    """

    def __init__(
        self,
        poll_interval: float = 0.25,
        on_state_change: Optional[Callable[[KPA500State], None]] = None
    ):
        """
        Initialize the model.

        Args:
            poll_interval: How often to poll the device (seconds)
            on_state_change: Callback when state changes
        """
        self._poll_interval = poll_interval
        self._on_state_change = on_state_change
        self._kpa: Optional[KPA500] = None
        self._state = KPA500State()
        self._poll_task: Optional[asyncio.Task] = None
        self._running = False

    @property
    def state(self) -> KPA500State:
        """Get current state."""
        return self._state

    def _notify_change(self) -> None:
        """Notify listener of state change."""
        if self._on_state_change:
            self._on_state_change(self._state)

    async def connect(self, port: str, baudrate: int = 38400) -> bool:
        """
        Connect to the KPA500.

        Args:
            port: Serial port path
            baudrate: Baud rate

        Returns:
            True if connected successfully
        """
        try:
            self._kpa = await KPA500.from_serial_port(port, baudrate=baudrate)
            self._state.connected = True
            self._state.powered_on = self._kpa.is_powered_on or False
            self._notify_change()
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            self._state.connected = False
            self._notify_change()
            return False

    async def disconnect(self) -> None:
        """Disconnect from the KPA500."""
        await self.stop_polling()
        if self._kpa:
            await self._kpa.close()
            self._kpa = None
        self._state = KPA500State()
        self._notify_change()

    async def start_polling(self) -> None:
        """Start periodic polling of the KPA500."""
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
            await asyncio.sleep(self._poll_interval)

    async def _poll_once(self) -> None:
        """Poll the KPA500 once and update state."""
        if not self._kpa or not self._state.connected:
            return

        try:
            # Check if powered on first
            power_state = await self._kpa.get_power_state()
            if power_state is None:
                # No response - might be in bootloader mode
                self._state.powered_on = False
                self._notify_change()
                return

            self._state.powered_on = power_state == PowerState.ON

            if not self._state.powered_on:
                self._notify_change()
                return

            # Query all parameters when powered on
            self._state.operating_mode = await self._kpa.get_operating_mode()
            self._state.band = await self._kpa.get_band()

            power_swr = await self._kpa.get_power_swr()
            if power_swr:
                self._state.power_watts = power_swr.power_watts
                self._state.swr = power_swr.swr

            self._state.temperature = await self._kpa.get_temperature()

            vi = await self._kpa.get_voltage_current()
            if vi:
                self._state.voltage = vi.voltage
                self._state.current = vi.current

            self._state.fault = await self._kpa.get_fault()

            self._notify_change()

        except Exception as e:
            print(f"Poll error: {e}")

    # =========================================================================
    # Control Methods (called by TUI)
    # =========================================================================

    async def power_on(self) -> bool:
        """Turn the KPA500 on."""
        if not self._kpa:
            return False
        result = await self._kpa.power_on()
        if result:
            self._state.powered_on = True
            self._notify_change()
        return result

    async def power_off(self) -> bool:
        """Turn the KPA500 off."""
        if not self._kpa:
            return False
        result = await self._kpa.power_off()
        if result:
            self._state.powered_on = False
            self._notify_change()
        return result

    async def toggle_power(self) -> bool:
        """Toggle power state."""
        if self._state.powered_on:
            return await self.power_off()
        else:
            return await self.power_on()

    async def set_standby(self) -> bool:
        """Set to standby mode."""
        if not self._kpa or not self._state.powered_on:
            return False
        result = await self._kpa.set_standby()
        if result:
            self._state.operating_mode = OperatingMode.STANDBY
            self._notify_change()
        return result

    async def set_operate(self) -> bool:
        """Set to operate mode."""
        if not self._kpa or not self._state.powered_on:
            return False
        result = await self._kpa.set_operate()
        if result:
            self._state.operating_mode = OperatingMode.OPERATE
            self._notify_change()
        return result

    async def set_operating_mode(self, mode: OperatingMode) -> bool:
        """Set operating mode."""
        if mode == OperatingMode.STANDBY:
            return await self.set_standby()
        else:
            return await self.set_operate()

    async def set_band(self, band: Band) -> bool:
        """Set the band."""
        if not self._kpa or not self._state.powered_on:
            return False
        result = await self._kpa.set_band(band)
        if result:
            self._state.band = band
            self._notify_change()
        return result

    async def clear_fault(self) -> bool:
        """Clear any active fault."""
        if not self._kpa or not self._state.powered_on:
            return False
        result = await self._kpa.clear_fault()
        if result:
            self._state.fault = Fault.NONE
            self._notify_change()
        return result
