"""Pytest configuration for KPA500 tests."""

import pytest


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--serial-port",
        action="store",
        default=None,
        help="Serial port for live KPA500 tests (e.g., /dev/ttyUSB0)"
    )
    parser.addoption(
        "--baudrate",
        action="store",
        default=38400,
        type=int,
        help="Baud rate for serial connection (default: 38400)"
    )


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "live: mark test as requiring live hardware (requires --serial-port)"
    )


def pytest_collection_modifyitems(config, items):
    """Skip live tests unless --serial-port is provided."""
    if config.getoption("--serial-port"):
        # --serial-port given, don't skip live tests
        return

    skip_live = pytest.mark.skip(reason="need --serial-port option to run")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)
