#!/usr/bin/env python3
"""
KAT500 Live Integration Test

This test requires a real KAT500 connected via serial port.
It is NOT run automatically with pytest - must be run explicitly.

Usage:
    python -m pytest tests/kat500_live_test.py --serial-port /dev/ttyUSB0 -v -s
    python -m pytest tests/kat500_live_test.py --serial-port /dev/ttyUSB0 --baudrate 9600 -v -s

Or run directly:
    python tests/kat500_live_test.py /dev/ttyUSB0
    python tests/kat500_live_test.py /dev/ttyUSB0 --baudrate 9600
"""

import asyncio
import sys
from typing import Optional

import pytest

from kat500 import (
    KAT500,
    Antenna,
    Band,
    BaudRate,
    BypassState,
    Fault,
    Mode,
    PowerState,
    Side,
)


# Mark all tests in this module to be skipped unless --serial-port is provided
pytestmark = pytest.mark.live


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "live: mark test as requiring live hardware"
    )


@pytest.fixture(scope="module")
def serial_port(request) -> str:
    """Get serial port from command line."""
    port = request.config.getoption("--serial-port", default=None)
    if port is None:
        pytest.skip("--serial-port not provided, skipping live tests")
    return port


@pytest.fixture(scope="module")
def baudrate(request) -> int:
    """Get baud rate from command line."""
    return request.config.getoption("--baudrate", default=38400)


@pytest.fixture(scope="module")
async def kat500_connection(serial_port, baudrate) -> KAT500:
    """Create and return a KAT500 connection."""
    print(f"\n{'='*60}")
    print(f"Connecting to KAT500 on {serial_port} at {baudrate} baud...")
    print(f"{'='*60}\n")

    kat = await KAT500.from_serial_port(serial_port, baudrate=baudrate)
    yield kat
    await kat.close()
    print("\nConnection closed.")


class TestKAT500Live:
    """Live integration tests for KAT500."""

    @pytest.mark.asyncio
    async def test_00_prepare_device(self, serial_port, baudrate):
        """Prepare: Ask user to power on the KAT500."""
        print("\n" + "="*60)
        print("KAT500 LIVE INTEGRATION TEST")
        print("="*60)
        print(f"\nSerial port: {serial_port}")
        print(f"Baud rate: {baudrate}")
        print("\n*** PREPARATION ***")
        print("Please ensure the KAT500 is powered on and connected.")
        print("\nPress ENTER when ready...")
        input()

    @pytest.mark.asyncio
    async def test_01_ping_and_identify(self, serial_port, baudrate):
        """Test basic connectivity."""
        print("\n" + "-"*60)
        print("TEST: Ping and identify device")
        print("-"*60)

        kat = await KAT500.from_serial_port(serial_port, baudrate=baudrate, timeout=2.0)

        print("Pinging device...")
        result = await kat.ping()
        print(f"Ping result: {'OK' if result else 'FAILED'}")
        assert result, "Device should respond to ping"

        print("Identifying device...")
        ident = await kat.identify()
        print(f"Device identification: {ident}")
        assert ident is not None, "Should get device identification"
        assert "KAT500" in ident.upper(), "Should identify as KAT500"

        await kat.close()

    @pytest.mark.asyncio
    async def test_02_query_device_info(self, serial_port, baudrate):
        """Query and display device information."""
        print("\n" + "-"*60)
        print("TEST: Query device information")
        print("-"*60)

        kat = await KAT500.from_serial_port(serial_port, baudrate=baudrate, timeout=2.0)

        serial_number = await kat.get_serial_number()
        print(f"Serial Number: {serial_number}")

        firmware = await kat.get_firmware_version()
        print(f"Firmware Version: {firmware}")

        assert serial_number is not None, "Should get serial number"
        assert firmware is not None, "Should get firmware version"

        await kat.close()

    @pytest.mark.asyncio
    async def test_03_power_control(self, serial_port, baudrate):
        """Test power on/off control."""
        print("\n" + "-"*60)
        print("TEST: Power control")
        print("-"*60)

        kat = await KAT500.from_serial_port(serial_port, baudrate=baudrate, timeout=2.0)

        power_state = await kat.get_power_state()
        print(f"Current power state: {power_state.name if power_state else 'N/A'}")

        if power_state == PowerState.OFF:
            print("Powering on...")
            result = await kat.power_on()
            await asyncio.sleep(1)
            power_state = await kat.get_power_state()
            print(f"Power state after power_on: {power_state.name if power_state else 'N/A'}")
            assert power_state == PowerState.ON, "Should be ON"

        await kat.close()

    @pytest.mark.asyncio
    async def test_04_mode_control(self, serial_port, baudrate):
        """Test mode switching (Bypass/Manual/Auto)."""
        print("\n" + "-"*60)
        print("TEST: Mode control (Bypass/Manual/Auto)")
        print("-"*60)

        kat = await KAT500.from_serial_port(serial_port, baudrate=baudrate, timeout=2.0)

        # Test Bypass mode
        print("Setting BYPASS mode...")
        result = await kat.set_bypass_mode()
        await asyncio.sleep(0.5)
        mode = await kat.get_mode()
        print(f"  Result: {result}, Current mode: {mode.value if mode else 'N/A'}")
        assert mode == Mode.BYPASS, "Should be in BYPASS"

        # Test Manual mode
        print("Setting MANUAL mode...")
        result = await kat.set_manual_mode()
        await asyncio.sleep(0.5)
        mode = await kat.get_mode()
        print(f"  Result: {result}, Current mode: {mode.value if mode else 'N/A'}")
        assert mode == Mode.MANUAL, "Should be in MANUAL"

        # Test Auto mode
        print("Setting AUTO mode...")
        result = await kat.set_auto_mode()
        await asyncio.sleep(0.5)
        mode = await kat.get_mode()
        print(f"  Result: {result}, Current mode: {mode.value if mode else 'N/A'}")
        assert mode == Mode.AUTO, "Should be in AUTO"

        print("Mode control test successful!")
        await kat.close()

    @pytest.mark.asyncio
    async def test_05_cycle_all_bands(self, serial_port, baudrate):
        """Cycle through all bands."""
        print("\n" + "-"*60)
        print("TEST: Cycle through all bands")
        print("-"*60)

        kat = await KAT500.from_serial_port(serial_port, baudrate=baudrate, timeout=2.0)

        bands = [
            Band.BAND_160M,
            Band.BAND_80M,
            Band.BAND_60M,
            Band.BAND_40M,
            Band.BAND_30M,
            Band.BAND_20M,
            Band.BAND_17M,
            Band.BAND_15M,
            Band.BAND_12M,
            Band.BAND_10M,
            Band.BAND_6M,
        ]

        for band in bands:
            result = await kat.set_band(band)
            await asyncio.sleep(0.5)
            current = await kat.get_band()
            status = "OK" if current == band else "FAIL"
            print(f"  Set {band.name}: {status} (read back: {current.name if current else 'None'})")
            assert current == band, f"Band mismatch: expected {band}, got {current}"

        print("All bands cycled successfully!")
        await kat.close()

    @pytest.mark.asyncio
    async def test_06_antenna_control(self, serial_port, baudrate):
        """Test antenna selection."""
        print("\n" + "-"*60)
        print("TEST: Antenna control")
        print("-"*60)

        kat = await KAT500.from_serial_port(serial_port, baudrate=baudrate, timeout=2.0)

        for ant in [Antenna.ANT1, Antenna.ANT2, Antenna.ANT3]:
            result = await kat.set_antenna(ant)
            await asyncio.sleep(0.5)
            current = await kat.get_antenna()
            status = "OK" if current == ant else "FAIL"
            print(f"  Set {ant.name}: {status} (read back: {current.name if current else 'None'})")

        print("Testing next_antenna()...")
        initial = await kat.get_antenna()
        await kat.next_antenna()
        await asyncio.sleep(0.5)
        after = await kat.get_antenna()
        print(f"  Before: {initial.name if initial else 'N/A'}, After: {after.name if after else 'N/A'}")

        print("Antenna control test successful!")
        await kat.close()

    @pytest.mark.asyncio
    async def test_07_query_all_parameters(self, serial_port, baudrate):
        """Query and display all readable parameters."""
        print("\n" + "-"*60)
        print("TEST: Query all parameters")
        print("-"*60)

        kat = await KAT500.from_serial_port(serial_port, baudrate=baudrate, timeout=2.0)

        print("\n  --- Power & Mode ---")
        power_state = await kat.get_power_state()
        print(f"  Power State: {power_state.name if power_state else 'N/A'}")

        mode = await kat.get_mode()
        print(f"  Mode: {mode.value if mode else 'N/A'}")

        band = await kat.get_band()
        print(f"  Band: {band.name if band else 'N/A'}")

        antenna = await kat.get_antenna()
        print(f"  Antenna: {antenna.name if antenna else 'N/A'}")

        print("\n  --- Tuner State ---")
        bypass = await kat.get_bypass()
        print(f"  Bypass: {bypass.value if bypass else 'N/A'}")

        side = await kat.get_side()
        print(f"  Side: {side.value if side else 'N/A'}")

        inductors = await kat.get_inductors()
        print(f"  Inductors: 0x{inductors:02X}" if inductors is not None else "  Inductors: N/A")

        capacitors = await kat.get_capacitors()
        print(f"  Capacitors: 0x{capacitors:02X}" if capacitors is not None else "  Capacitors: N/A")

        print("\n  --- VSWR Readings ---")
        vswr = await kat.get_vswr()
        print(f"  VSWR: {vswr:.2f}" if vswr is not None else "  VSWR: N/A")

        vswr_bypass = await kat.get_vswr_bypass()
        print(f"  VSWR (Bypass): {vswr_bypass:.2f}" if vswr_bypass is not None else "  VSWR (Bypass): N/A")

        vfwd = await kat.get_forward_voltage()
        print(f"  Forward Voltage: {vfwd}" if vfwd is not None else "  Forward Voltage: N/A")

        vrfl = await kat.get_reflected_voltage()
        print(f"  Reflected Voltage: {vrfl}" if vrfl is not None else "  Reflected Voltage: N/A")

        print("\n  --- Settings ---")
        freq = await kat.get_frequency()
        print(f"  Last Frequency: {freq} kHz" if freq is not None else "  Last Frequency: N/A")

        attenuator = await kat.get_attenuator()
        print(f"  Attenuator: {'ON' if attenuator else 'OFF'}" if attenuator is not None else "  Attenuator: N/A")

        sleep = await kat.get_sleep_enabled()
        print(f"  Sleep Enabled: {'YES' if sleep else 'NO'}" if sleep is not None else "  Sleep Enabled: N/A")

        psi = await kat.get_initial_power_state()
        print(f"  Initial Power State: {psi.name if psi else 'N/A'}")

        print("\n  --- Amplifier Key Interrupt ---")
        akip = await kat.get_amp_key_interrupt_power()
        print(f"  AKI Power Threshold: {akip}W" if akip is not None else "  AKI Power Threshold: N/A")

        ampi = await kat.get_amp_key_interrupt()
        print(f"  AKI State: {'Interrupted' if ampi else 'Connected'}" if ampi is not None else "  AKI State: N/A")

        print("\n  --- Fault Status ---")
        fault = await kat.get_fault()
        print(f"  Fault: {fault.name if fault else 'N/A'}")

        print("\n  --- Communication ---")
        br = await kat.get_baudrate()
        print(f"  Baud Rate: {br.name if br else 'N/A'}")

        print("\nAll parameters queried successfully!")
        await kat.close()

    @pytest.mark.asyncio
    async def test_08_cleanup(self, serial_port, baudrate):
        """Clean up and finish."""
        print("\n" + "-"*60)
        print("TEST: Cleanup")
        print("-"*60)

        kat = await KAT500.from_serial_port(serial_port, baudrate=baudrate, timeout=2.0)

        # Return to a safe state
        print("Setting AUTO mode...")
        await kat.set_auto_mode()
        await asyncio.sleep(0.5)

        await kat.close()

        print("\n" + "="*60)
        print("LIVE TEST COMPLETE")
        print("="*60)


# =============================================================================
# Direct execution support
# =============================================================================

async def run_all_tests(serial_port: str, baudrate: int = 38400):
    """Run all tests directly without pytest."""
    print("\n" + "="*60)
    print("KAT500 LIVE INTEGRATION TEST (Direct Mode)")
    print("="*60)
    print(f"\nSerial port: {serial_port}")
    print(f"Baud rate: {baudrate}")

    # Preparation
    print("\n*** PREPARATION ***")
    print("Please ensure the KAT500 is powered on and connected.")
    print("\nPress ENTER when ready...")
    input()

    try:
        # Test 1: Ping and identify
        print("\n" + "-"*60)
        print("TEST 1: Ping and identify device")
        print("-"*60)

        kat = await KAT500.from_serial_port(serial_port, baudrate=baudrate, timeout=2.0)

        print("Pinging device...")
        result = await kat.ping()
        print(f"Ping result: {'OK' if result else 'FAILED'}")

        print("Identifying device...")
        ident = await kat.identify()
        print(f"Device identification: {ident}")

        # Test 2: Device info
        print("\n" + "-"*60)
        print("TEST 2: Query device information")
        print("-"*60)

        serial_number = await kat.get_serial_number()
        print(f"Serial Number: {serial_number}")

        firmware = await kat.get_firmware_version()
        print(f"Firmware Version: {firmware}")

        # Test 3: Power control
        print("\n" + "-"*60)
        print("TEST 3: Power control")
        print("-"*60)

        power_state = await kat.get_power_state()
        print(f"Current power state: {power_state.name if power_state else 'N/A'}")

        # Test 4: Mode control
        print("\n" + "-"*60)
        print("TEST 4: Mode control")
        print("-"*60)

        for mode_func, mode_name in [(kat.set_bypass_mode, "BYPASS"),
                                       (kat.set_manual_mode, "MANUAL"),
                                       (kat.set_auto_mode, "AUTO")]:
            print(f"Setting {mode_name}...")
            await mode_func()
            await asyncio.sleep(0.5)
            mode = await kat.get_mode()
            print(f"  Current mode: {mode.value if mode else 'N/A'}")

        # Test 5: Cycle bands
        print("\n" + "-"*60)
        print("TEST 5: Cycle through all bands")
        print("-"*60)

        bands = list(Band)
        for band in bands:
            await kat.set_band(band)
            await asyncio.sleep(0.5)
            current = await kat.get_band()
            status = "OK" if current == band else "FAIL"
            print(f"  {band.name}: {status}")

        # Test 6: Antenna control
        print("\n" + "-"*60)
        print("TEST 6: Antenna control")
        print("-"*60)

        for ant in [Antenna.ANT1, Antenna.ANT2, Antenna.ANT3]:
            await kat.set_antenna(ant)
            await asyncio.sleep(0.5)
            current = await kat.get_antenna()
            status = "OK" if current == ant else "FAIL"
            print(f"  {ant.name}: {status}")

        # Test 7: Query all
        print("\n" + "-"*60)
        print("TEST 7: Query all parameters")
        print("-"*60)

        print(f"  Power State: {await kat.get_power_state()}")
        print(f"  Mode: {await kat.get_mode()}")
        print(f"  Band: {await kat.get_band()}")
        print(f"  Antenna: {await kat.get_antenna()}")
        print(f"  Bypass: {await kat.get_bypass()}")
        print(f"  Side: {await kat.get_side()}")

        inductors = await kat.get_inductors()
        print(f"  Inductors: 0x{inductors:02X}" if inductors else "  Inductors: N/A")

        capacitors = await kat.get_capacitors()
        print(f"  Capacitors: 0x{capacitors:02X}" if capacitors else "  Capacitors: N/A")

        print(f"  VSWR: {await kat.get_vswr()}")
        print(f"  VSWR (Bypass): {await kat.get_vswr_bypass()}")
        print(f"  Forward Voltage: {await kat.get_forward_voltage()}")
        print(f"  Reflected Voltage: {await kat.get_reflected_voltage()}")
        print(f"  Last Frequency: {await kat.get_frequency()} kHz")
        print(f"  Attenuator: {await kat.get_attenuator()}")
        print(f"  Sleep Enabled: {await kat.get_sleep_enabled()}")
        print(f"  Initial Power State: {await kat.get_initial_power_state()}")
        print(f"  AKI Power Threshold: {await kat.get_amp_key_interrupt_power()}W")
        print(f"  AKI State: {await kat.get_amp_key_interrupt()}")
        print(f"  Fault: {await kat.get_fault()}")
        print(f"  Baud Rate: {await kat.get_baudrate()}")

        # Cleanup
        print("\n" + "-"*60)
        print("TEST 8: Cleanup")
        print("-"*60)

        print("Setting AUTO mode...")
        await kat.set_auto_mode()

        await kat.close()

        print("\n" + "="*60)
        print("ALL TESTS COMPLETE")
        print("="*60)

    except Exception as e:
        print(f"\nERROR: {e}")
        raise


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="KAT500 Live Integration Test")
    parser.add_argument("serial_port", help="Serial port (e.g., /dev/ttyUSB0)")
    parser.add_argument("--baudrate", type=int, default=38400,
                        help="Baud rate (default: 38400)")

    args = parser.parse_args()
    asyncio.run(run_all_tests(args.serial_port, args.baudrate))
