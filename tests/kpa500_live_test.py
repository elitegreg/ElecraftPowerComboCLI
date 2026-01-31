#!/usr/bin/env python3
"""
KPA500 Live Integration Test

This test requires a real KPA500 connected via serial port.
It is NOT run automatically with pytest - must be run explicitly.

Usage:
    python -m pytest tests/kpa500_live_test.py --serial-port /dev/ttyUSB0 -v -s
    python -m pytest tests/kpa500_live_test.py --serial-port /dev/ttyUSB0 --baudrate 9600 -v -s

Or run directly:
    python tests/kpa500_live_test.py /dev/ttyUSB0
    python tests/kpa500_live_test.py /dev/ttyUSB0 --baudrate 9600
"""

import asyncio
import sys
from typing import Optional

import pytest

from kpa500 import (
    KPA500,
    Band,
    BaudRate,
    Fault,
    FanSpeed,
    OperatingMode,
    PowerState,
    RadioInterface,
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
async def kpa500_connection(serial_port, baudrate) -> KPA500:
    """Create and return a KPA500 connection."""
    print(f"\n{'='*60}")
    print(f"Connecting to KPA500 on {serial_port} at {baudrate} baud...")
    print(f"{'='*60}\n")

    kpa = await KPA500.from_serial_port(serial_port, baudrate=baudrate)
    yield kpa
    await kpa.close()
    print("\nConnection closed.")


class TestKPA500Live:
    """Live integration tests for KPA500."""

    @pytest.mark.asyncio
    async def test_00_prepare_device(self, serial_port, baudrate):
        """Prepare: Ask user to power off the KPA500."""
        print("\n" + "="*60)
        print("KPA500 LIVE INTEGRATION TEST")
        print("="*60)
        print(f"\nSerial port: {serial_port}")
        print(f"Baud rate: {baudrate}")
        print("\n*** PREPARATION ***")
        print("Please ensure the KPA500 rear panel power switch is ON,")
        print("but the amplifier is in STANDBY/OFF state (not powered up).")
        print("\nPress ENTER when ready...")
        input()

    @pytest.mark.asyncio
    async def test_01_power_on_from_bootloader(self, serial_port, baudrate):
        """Test powering on from bootloader mode."""
        print("\n" + "-"*60)
        print("TEST: Power on from bootloader mode")
        print("-"*60)

        kpa = await KPA500.from_serial_port(serial_port, baudrate=baudrate, timeout=2.0)

        print(f"Initial power state detected: {kpa.is_powered_on}")

        if kpa.is_powered_on:
            print("Device is already on - powering off first...")
            await kpa.power_off()
            await asyncio.sleep(2)
            print("Please wait for device to fully power down...")
            await asyncio.sleep(3)
            # Reconnect
            await kpa.close()
            kpa = await KPA500.from_serial_port(serial_port, baudrate=baudrate, timeout=2.0)

        print("Sending power-on command (bootloader mode)...")
        result = await kpa.power_on()
        print(f"Power on result: {result}")

        if result:
            print("Waiting for device to fully initialize...")
            await asyncio.sleep(2)

            state = await kpa.get_power_state()
            print(f"Power state after power-on: {state}")
            assert state == PowerState.ON, "Device should be ON"
        else:
            pytest.fail("Failed to power on device")

        await kpa.close()

    @pytest.mark.asyncio
    async def test_02_query_device_info(self, serial_port, baudrate):
        """Query and display device information."""
        print("\n" + "-"*60)
        print("TEST: Query device information")
        print("-"*60)

        kpa = await KPA500.from_serial_port(serial_port, baudrate=baudrate, timeout=2.0)

        serial_number = await kpa.get_serial_number()
        print(f"Serial Number: {serial_number}")

        firmware = await kpa.get_firmware_version()
        print(f"Firmware Version: {firmware}")

        assert serial_number is not None, "Should get serial number"
        assert firmware is not None, "Should get firmware version"

        await kpa.close()

    @pytest.mark.asyncio
    async def test_03_cycle_all_bands(self, serial_port, baudrate):
        """Cycle through all bands."""
        print("\n" + "-"*60)
        print("TEST: Cycle through all bands")
        print("-"*60)

        kpa = await KPA500.from_serial_port(serial_port, baudrate=baudrate, timeout=2.0)

        # Ensure we're in standby for safety
        await kpa.set_standby()
        await asyncio.sleep(1)

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
            result = await kpa.set_band(band)
            await asyncio.sleep(1)
            current = await kpa.get_band()
            status = "OK" if current == band else "FAIL"
            print(f"  Set {band.name}: {status} (read back: {current.name if current else 'None'})")
            assert current == band, f"Band mismatch: expected {band}, got {current}"

        print("All bands cycled successfully!")
        await kpa.close()

    @pytest.mark.asyncio
    async def test_04_toggle_operating_mode(self, serial_port, baudrate):
        """Toggle between Standby and Operate modes."""
        print("\n" + "-"*60)
        print("TEST: Toggle operating mode (Standby/Operate)")
        print("-"*60)

        kpa = await KPA500.from_serial_port(serial_port, baudrate=baudrate, timeout=2.0)

        # Test Standby
        print("Setting STANDBY mode...")
        result = await kpa.set_standby()
        await asyncio.sleep(1)
        mode = await kpa.get_operating_mode()
        print(f"  Result: {result}, Current mode: {mode}")
        assert mode == OperatingMode.STANDBY, "Should be in STANDBY"

        # Test Operate
        print("Setting OPERATE mode...")
        result = await kpa.set_operate()
        await asyncio.sleep(1)
        mode = await kpa.get_operating_mode()
        print(f"  Result: {result}, Current mode: {mode}")
        assert mode == OperatingMode.OPERATE, "Should be in OPERATE"

        # Return to Standby for safety
        print("Returning to STANDBY mode...")
        await kpa.set_standby()
        await asyncio.sleep(1)

        print("Operating mode toggle successful!")
        await kpa.close()

    @pytest.mark.asyncio
    async def test_05_query_all_parameters(self, serial_port, baudrate):
        """Query and display all readable parameters."""
        print("\n" + "-"*60)
        print("TEST: Query all parameters")
        print("-"*60)

        kpa = await KPA500.from_serial_port(serial_port, baudrate=baudrate, timeout=2.0)

        print("\n  --- Power & Mode ---")
        power_state = await kpa.get_power_state()
        print(f"  Power State: {power_state.name if power_state else 'N/A'}")

        op_mode = await kpa.get_operating_mode()
        print(f"  Operating Mode: {op_mode.name if op_mode else 'N/A'}")

        band = await kpa.get_band()
        print(f"  Band: {band.name if band else 'N/A'}")

        print("\n  --- Readings ---")
        power_swr = await kpa.get_power_swr()
        if power_swr:
            print(f"  Power: {power_swr.power_watts}W, SWR: {power_swr.swr}")
        else:
            print("  Power/SWR: N/A")

        temp = await kpa.get_temperature()
        print(f"  Temperature: {temp}°C" if temp else "  Temperature: N/A")

        vi = await kpa.get_voltage_current()
        if vi:
            print(f"  Voltage: {vi.voltage}V, Current: {vi.current}A")
        else:
            print("  Voltage/Current: N/A")

        print("\n  --- Settings ---")
        alc = await kpa.get_alc()
        print(f"  ALC Threshold: {alc}" if alc is not None else "  ALC: N/A")

        fan = await kpa.get_fan_speed()
        print(f"  Fan Speed: {fan.name if fan else 'N/A'}")

        speaker = await kpa.get_speaker()
        print(f"  Speaker: {'ON' if speaker else 'OFF'}" if speaker is not None else "  Speaker: N/A")

        tr_delay = await kpa.get_tr_delay()
        print(f"  T/R Delay: {tr_delay}ms" if tr_delay is not None else "  T/R Delay: N/A")

        bc = await kpa.get_standby_on_band_change()
        print(f"  Standby on Band Change: {'YES' if bc else 'NO'}" if bc is not None else "  Standby on Band Change: N/A")

        print("\n  --- Fault Status ---")
        fault = await kpa.get_fault()
        print(f"  Fault: {fault.name if fault else 'N/A'}")

        print("\n  --- Communication ---")
        pc_baud = await kpa.get_pc_baudrate()
        print(f"  PC Baud Rate: {pc_baud.name if pc_baud else 'N/A'}")

        xcvr_baud = await kpa.get_xcvr_baudrate()
        print(f"  XCVR Baud Rate: {xcvr_baud.name if xcvr_baud else 'N/A'}")

        radio_if = await kpa.get_radio_interface()
        print(f"  Radio Interface: {radio_if.name if radio_if else 'N/A'}")

        print("\nAll parameters queried successfully!")
        await kpa.close()

    @pytest.mark.asyncio
    async def test_06_power_off(self, serial_port, baudrate):
        """Power off the device."""
        print("\n" + "-"*60)
        print("TEST: Power off")
        print("-"*60)

        kpa = await KPA500.from_serial_port(serial_port, baudrate=baudrate, timeout=2.0)

        # Ensure we're in standby first
        await kpa.set_standby()
        await asyncio.sleep(1)

        print("Powering off...")
        result = await kpa.power_off()
        print(f"Power off command sent: {result}")

        await asyncio.sleep(1)

        print("\n" + "="*60)
        print("LIVE TEST COMPLETE")
        print("="*60)

        await kpa.close()


# =============================================================================
# Direct execution support
# =============================================================================

async def run_all_tests(serial_port: str, baudrate: int = 38400):
    """Run all tests directly without pytest."""
    print("\n" + "="*60)
    print("KPA500 LIVE INTEGRATION TEST (Direct Mode)")
    print("="*60)
    print(f"\nSerial port: {serial_port}")
    print(f"Baud rate: {baudrate}")

    # Preparation
    print("\n*** PREPARATION ***")
    print("Please ensure the KPA500 rear panel power switch is ON,")
    print("but the amplifier is in STANDBY/OFF state (not powered up).")
    print("\nPress ENTER when ready...")
    input()

    try:
        # Test 1: Power on from bootloader
        print("\n" + "-"*60)
        print("TEST 1: Power on from bootloader mode")
        print("-"*60)

        kpa = await KPA500.from_serial_port(serial_port, baudrate=baudrate, timeout=2.0)
        print(f"Initial power state detected: {kpa.is_powered_on}")

        if not kpa.is_powered_on:
            print("Sending power-on command (bootloader mode)...")
            result = await kpa.power_on()
            print(f"Power on result: {result}")
            if not result:
                print("ERROR: Failed to power on device")
                return
            print("Waiting for device to initialize...")
            await asyncio.sleep(2)

        # Test 2: Device info
        print("\n" + "-"*60)
        print("TEST 2: Query device information")
        print("-"*60)

        serial_number = await kpa.get_serial_number()
        print(f"Serial Number: {serial_number}")

        firmware = await kpa.get_firmware_version()
        print(f"Firmware Version: {firmware}")

        # Test 3: Cycle bands
        print("\n" + "-"*60)
        print("TEST 3: Cycle through all bands")
        print("-"*60)

        await kpa.set_standby()
        await asyncio.sleep(1)

        bands = list(Band)
        for band in bands:
            await kpa.set_band(band)
            await asyncio.sleep(1)
            current = await kpa.get_band()
            status = "OK" if current == band else "FAIL"
            print(f"  {band.name}: {status}")

        # Test 4: Operating mode
        print("\n" + "-"*60)
        print("TEST 4: Toggle operating mode")
        print("-"*60)

        print("Setting STANDBY...")
        await kpa.set_standby()
        await asyncio.sleep(1)
        mode = await kpa.get_operating_mode()
        print(f"  Mode: {mode.name if mode else 'N/A'}")

        print("Setting OPERATE...")
        await kpa.set_operate()
        await asyncio.sleep(1)
        mode = await kpa.get_operating_mode()
        print(f"  Mode: {mode.name if mode else 'N/A'}")

        await kpa.set_standby()
        await asyncio.sleep(1)

        # Test 5: Query all
        print("\n" + "-"*60)
        print("TEST 5: Query all parameters")
        print("-"*60)

        print(f"  Power State: {await kpa.get_power_state()}")
        print(f"  Operating Mode: {await kpa.get_operating_mode()}")
        print(f"  Band: {await kpa.get_band()}")

        ps = await kpa.get_power_swr()
        print(f"  Power/SWR: {ps.power_watts}W / {ps.swr}" if ps else "  Power/SWR: N/A")

        print(f"  Temperature: {await kpa.get_temperature()}°C")

        vi = await kpa.get_voltage_current()
        print(f"  Voltage/Current: {vi.voltage}V / {vi.current}A" if vi else "  Voltage/Current: N/A")

        print(f"  ALC: {await kpa.get_alc()}")
        print(f"  Fan Speed: {await kpa.get_fan_speed()}")
        print(f"  Speaker: {await kpa.get_speaker()}")
        print(f"  T/R Delay: {await kpa.get_tr_delay()}ms")
        print(f"  Standby on Band Change: {await kpa.get_standby_on_band_change()}")
        print(f"  Fault: {await kpa.get_fault()}")
        print(f"  PC Baud: {await kpa.get_pc_baudrate()}")
        print(f"  XCVR Baud: {await kpa.get_xcvr_baudrate()}")
        print(f"  Radio Interface: {await kpa.get_radio_interface()}")

        # Test 6: Power off
        print("\n" + "-"*60)
        print("TEST 6: Power off")
        print("-"*60)

        await kpa.set_standby()
        await asyncio.sleep(1)
        print("Powering off...")
        await kpa.power_off()

        await kpa.close()

        print("\n" + "="*60)
        print("ALL TESTS COMPLETE")
        print("="*60)

    except Exception as e:
        print(f"\nERROR: {e}")
        raise


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="KPA500 Live Integration Test")
    parser.add_argument("serial_port", help="Serial port (e.g., /dev/ttyUSB0)")
    parser.add_argument("--baudrate", type=int, default=38400,
                        help="Baud rate (default: 38400)")

    args = parser.parse_args()
    asyncio.run(run_all_tests(args.serial_port, args.baudrate))
