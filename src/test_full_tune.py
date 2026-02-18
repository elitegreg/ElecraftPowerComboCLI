#!/usr/bin/env python3
"""
Test tool for KPA500/KAT500 full tune functionality.

Usage:
    python test_full_tune.py --kpa-port /dev/ttyUSB0 --kat-port /dev/ttyUSB1

This script connects to a KPA500/KAT500 pair and initiates a full tune.
The KPA500 will be put in standby before tuning begins.
"""

import argparse
import asyncio
import logging
import sys

from model import ComboModel, ComboState


def state_changed(state: ComboState) -> None:
    """Print state changes for debugging."""
    print(f"  KPA connected: {state.kpa_connected}, KAT connected: {state.kat_connected}")
    print(f"  Powered on: {state.powered_on}")
    if state.kpa_operating_mode:
        print(f"  KPA mode: {state.kpa_operating_mode.name}")
    if state.is_tuning:
        print(f"  Tuning in progress...")
    if state.kat_swr:
        print(f"  KAT SWR: {state.kat_swr:.2f}")


async def run_full_tune(
    kpa_port: str | None,
    kat_port: str | None,
    baudrate: int,
    wait_for_tune: bool
) -> int:
    """Connect to devices and run full tune."""

    model = ComboModel(
        kpa_poll_interval=0.5,
        kat_poll_interval=5.0,
        on_state_change=state_changed
    )

    print(f"Connecting to KPA500 on {kpa_port}, KAT500 on {kat_port}...")

    try:
        connected = await model.connect(
            kpa_port=kpa_port,
            kat_port=kat_port,
            baudrate=baudrate
        )

        if not connected:
            print("Failed to connect to any device")
            return 1

        state = model.state
        print(f"Connected. KPA: {state.kpa_connected}, KAT: {state.kat_connected}")
        print(f"Power state: {'ON' if state.powered_on else 'OFF'}")

        if not state.powered_on:
            print("Devices not powered on. Powering on...")
            if not await model.power_on():
                print("Failed to power on devices")
                return 1
            print("Devices powered on")

        print("\nInitiating full tune...")
        result = await model.kat_full_tune()

        if not result:
            print("Failed to start full tune")
            return 1

        print("Full tune started successfully")

        if wait_for_tune:
            print("Waiting for tune to complete...")
            # Poll until tuning completes
            await model.start_polling()
            while model.state.is_tuning:
                await asyncio.sleep(0.5)
            await model.stop_polling()

            print(f"\nTune complete!")
            print(f"  Final SWR: {model.state.kat_swr:.2f}")
            if model.state.kat_fault and model.state.kat_fault.value != 0:
                print(f"  Fault: {model.state.kat_fault.name}")

        return 0

    except Exception as e:
        print(f"Error: {e}")
        return 1

    finally:
        print("\nDisconnecting...")
        await model.disconnect()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test KPA500/KAT500 full tune functionality"
    )
    parser.add_argument(
        "--kpa-port",
        help="Serial port for KPA500 (e.g., /dev/ttyUSB0)",
        default=None
    )
    parser.add_argument(
        "--kat-port",
        help="Serial port for KAT500 (e.g., /dev/ttyUSB1)",
        default=None
    )
    parser.add_argument(
        "--baudrate",
        type=int,
        default=38400,
        help="Serial baud rate (default: 38400)"
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="Wait for tune to complete and show results"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging for serial communication"
    )

    args = parser.parse_args()

    # Configure logging
    if args.debug:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s %(name)s %(levelname)s: %(message)s",
            datefmt="%H:%M:%S"
        )
    else:
        logging.basicConfig(level=logging.WARNING)

    if not args.kpa_port and not args.kat_port:
        print("Error: At least one of --kpa-port or --kat-port must be specified")
        parser.print_help()
        return 1

    return asyncio.run(run_full_tune(
        kpa_port=args.kpa_port,
        kat_port=args.kat_port,
        baudrate=args.baudrate,
        wait_for_tune=args.wait
    ))


if __name__ == "__main__":
    sys.exit(main())
