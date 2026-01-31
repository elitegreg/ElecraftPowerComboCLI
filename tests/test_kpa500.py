"""Tests for KPA500 module."""

import asyncio
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
    PowerSWR,
    RadioInterface,
    VoltageCurrentReading,
)


# =============================================================================
# Mock Classes
# =============================================================================


class MockStreamReader:
    """Mock async stream reader for testing."""

    def __init__(self):
        self._responses: list[bytes] = []
        self._read_calls = 0
        self._ping_response: Optional[bytes] = None

    def add_response(self, response: str) -> None:
        """Queue a response to be returned."""
        self._responses.append(response.encode('ascii'))

    def set_ping_response(self, response: str) -> None:
        """Set the response for ping (single byte read)."""
        self._ping_response = response.encode('ascii')

    async def read(self, n: int) -> bytes:
        """Read for buffer clearing or ping."""
        self._read_calls += 1
        if n == 1 and self._ping_response is not None:
            resp = self._ping_response
            self._ping_response = None
            return resp
        raise asyncio.TimeoutError()

    async def readline(self) -> bytes:
        if not self._responses:
            raise asyncio.TimeoutError()
        return self._responses.pop(0)

    async def readuntil(self, separator: bytes) -> bytes:
        if not self._responses:
            raise asyncio.TimeoutError()
        return self._responses.pop(0)


class MockStreamWriter:
    """Mock async stream writer for testing."""

    def __init__(self):
        self._written: list[bytes] = []
        self._closed = False

    def write(self, data: bytes) -> None:
        self._written.append(data)

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        self._closed = True

    async def wait_closed(self) -> None:
        pass

    def get_last_command(self) -> str:
        if self._written:
            return self._written[-1].decode('ascii')
        return ""

    def get_all_written(self) -> list[bytes]:
        return self._written.copy()


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def mock_reader():
    return MockStreamReader()


@pytest.fixture
def mock_writer():
    return MockStreamWriter()


@pytest.fixture
def kpa500(mock_reader, mock_writer):
    return KPA500(mock_reader, mock_writer, timeout=0.1)


@pytest.fixture
def kpa500_powered_on(mock_reader, mock_writer):
    """KPA500 instance that thinks it's already powered on."""
    kpa = KPA500(mock_reader, mock_writer, timeout=0.1)
    kpa._power_on = True
    return kpa


# =============================================================================
# Enum Tests
# =============================================================================


class TestEnums:
    def test_band_values(self):
        assert Band.BAND_160M == 0
        assert Band.BAND_80M == 1
        assert Band.BAND_6M == 10

    def test_operating_mode_values(self):
        assert OperatingMode.STANDBY == 0
        assert OperatingMode.OPERATE == 1

    def test_power_state_values(self):
        assert PowerState.OFF == 0
        assert PowerState.ON == 1

    def test_fault_values(self):
        assert Fault.NONE == 0
        assert Fault.SWR == 4

    def test_baud_rate_values(self):
        assert BaudRate.BAUD_4800 == 0
        assert BaudRate.BAUD_38400 == 3


# =============================================================================
# Data Class Tests
# =============================================================================


class TestDataClasses:
    def test_power_swr(self):
        ps = PowerSWR(power_watts=350, swr=1.5)
        assert ps.power_watts == 350
        assert ps.swr == 1.5

    def test_voltage_current(self):
        vc = VoltageCurrentReading(voltage=52.5, current=12.0)
        assert vc.voltage == 52.5
        assert vc.current == 12.0


# =============================================================================
# KPA500 Tests
# =============================================================================


class TestKPA500:
    @pytest.mark.asyncio
    async def test_get_power_state_on(self, mock_reader, mock_writer, kpa500):
        mock_reader.add_response("^ON1;")
        state = await kpa500.get_power_state()
        assert state == PowerState.ON
        assert "^ON;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_get_power_state_off(self, mock_reader, kpa500):
        mock_reader.add_response("^ON0;")
        state = await kpa500.get_power_state()
        assert state == PowerState.OFF

    @pytest.mark.asyncio
    async def test_set_power_on_when_already_on(self, mock_reader, mock_writer, kpa500_powered_on):
        """When already powered on, use normal ^ON1; command."""
        mock_reader.add_response("^ON1;")
        result = await kpa500_powered_on.power_on()
        assert result
        assert "^ON1;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_set_power_off(self, mock_reader, mock_writer, kpa500_powered_on):
        mock_reader.add_response("^ON0;")
        result = await kpa500_powered_on.power_off()
        assert result
        assert "^ON0;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_get_operating_mode_standby(self, mock_reader, kpa500):
        mock_reader.add_response("^OS0;")
        mode = await kpa500.get_operating_mode()
        assert mode == OperatingMode.STANDBY

    @pytest.mark.asyncio
    async def test_get_operating_mode_operate(self, mock_reader, kpa500):
        mock_reader.add_response("^OS1;")
        mode = await kpa500.get_operating_mode()
        assert mode == OperatingMode.OPERATE

    @pytest.mark.asyncio
    async def test_set_standby(self, mock_reader, mock_writer, kpa500):
        mock_reader.add_response("^OS0;")
        result = await kpa500.set_standby()
        assert result
        assert "^OS0;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_set_operate(self, mock_reader, mock_writer, kpa500):
        mock_reader.add_response("^OS1;")
        result = await kpa500.set_operate()
        assert result
        assert "^OS1;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_get_band(self, mock_reader, kpa500):
        mock_reader.add_response("^BN05;")
        band = await kpa500.get_band()
        assert band == Band.BAND_20M

    @pytest.mark.asyncio
    async def test_set_band(self, mock_reader, mock_writer, kpa500):
        mock_reader.add_response("^BN03;")
        result = await kpa500.set_band(Band.BAND_40M)
        assert result
        assert "^BN03;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_get_alc(self, mock_reader, kpa500):
        mock_reader.add_response("^AL150;")
        alc = await kpa500.get_alc()
        assert alc == 150

    @pytest.mark.asyncio
    async def test_set_alc(self, mock_reader, mock_writer, kpa500):
        mock_reader.add_response("^AL100;")
        result = await kpa500.set_alc(100)
        assert result
        assert "^AL100;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_set_alc_invalid(self, kpa500):
        with pytest.raises(ValueError):
            await kpa500.set_alc(300)

    @pytest.mark.asyncio
    async def test_get_fan_speed(self, mock_reader, kpa500):
        mock_reader.add_response("^FC1;")
        speed = await kpa500.get_fan_speed()
        assert speed == FanSpeed.MEDIUM

    @pytest.mark.asyncio
    async def test_set_fan_speed(self, mock_reader, mock_writer, kpa500):
        mock_reader.add_response("^FC2;")
        result = await kpa500.set_fan_speed(FanSpeed.HIGH)
        assert result
        assert "^FC2;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_get_speaker(self, mock_reader, kpa500):
        mock_reader.add_response("^SP1;")
        speaker = await kpa500.get_speaker()
        assert speaker is True

    @pytest.mark.asyncio
    async def test_set_speaker_on(self, mock_reader, mock_writer, kpa500):
        mock_reader.add_response("^SP1;")
        result = await kpa500.set_speaker(True)
        assert result
        assert "^SP1;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_set_speaker_off(self, mock_reader, mock_writer, kpa500):
        mock_reader.add_response("^SP0;")
        result = await kpa500.set_speaker(False)
        assert result
        assert "^SP0;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_get_tr_delay(self, mock_reader, kpa500):
        mock_reader.add_response("^TR25;")
        delay = await kpa500.get_tr_delay()
        assert delay == 25

    @pytest.mark.asyncio
    async def test_set_tr_delay(self, mock_reader, mock_writer, kpa500):
        mock_reader.add_response("^TR30;")
        result = await kpa500.set_tr_delay(30)
        assert result
        assert "^TR30;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_set_tr_delay_invalid(self, kpa500):
        with pytest.raises(ValueError):
            await kpa500.set_tr_delay(100)

    @pytest.mark.asyncio
    async def test_get_fault_none(self, mock_reader, kpa500):
        mock_reader.add_response("^FL00;")
        fault = await kpa500.get_fault()
        assert fault == Fault.NONE

    @pytest.mark.asyncio
    async def test_get_fault_swr(self, mock_reader, kpa500):
        mock_reader.add_response("^FL04;")
        fault = await kpa500.get_fault()
        assert fault == Fault.SWR

    @pytest.mark.asyncio
    async def test_clear_fault(self, mock_reader, mock_writer, kpa500):
        mock_reader.add_response("^FL00;")
        result = await kpa500.clear_fault()
        assert result
        assert "^FLC;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_get_power_swr(self, mock_reader, kpa500):
        mock_reader.add_response("^WS035015;")
        ps = await kpa500.get_power_swr()
        assert ps.power_watts == 350
        assert ps.swr == 1.5

    @pytest.mark.asyncio
    async def test_get_temperature(self, mock_reader, kpa500):
        mock_reader.add_response("^TM045;")
        temp = await kpa500.get_temperature()
        assert temp == 45

    @pytest.mark.asyncio
    async def test_get_voltage_current(self, mock_reader, kpa500):
        mock_reader.add_response("^VI525120;")
        vc = await kpa500.get_voltage_current()
        assert vc.voltage == 52.5
        assert vc.current == 12.0

    @pytest.mark.asyncio
    async def test_get_serial_number(self, mock_reader, kpa500):
        mock_reader.add_response("^SN12345;")
        sn = await kpa500.get_serial_number()
        assert sn == "12345"

    @pytest.mark.asyncio
    async def test_get_firmware_version(self, mock_reader, kpa500):
        mock_reader.add_response("^RVM01.45;")
        version = await kpa500.get_firmware_version()
        assert version == "01.45"

    @pytest.mark.asyncio
    async def test_get_pc_baudrate(self, mock_reader, kpa500):
        mock_reader.add_response("^BRP3;")
        rate = await kpa500.get_pc_baudrate()
        assert rate == BaudRate.BAUD_38400

    @pytest.mark.asyncio
    async def test_set_pc_baudrate(self, mock_reader, mock_writer, kpa500):
        mock_reader.add_response("^BRP2;")
        result = await kpa500.set_pc_baudrate(BaudRate.BAUD_19200)
        assert result
        assert "^BRP2;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_get_radio_interface(self, mock_reader, kpa500):
        mock_reader.add_response("^XI0;")
        interface = await kpa500.get_radio_interface()
        assert interface == RadioInterface.RS232

    @pytest.mark.asyncio
    async def test_set_radio_interface(self, mock_reader, mock_writer, kpa500):
        mock_reader.add_response("^XI1;")
        result = await kpa500.set_radio_interface(RadioInterface.AUX)
        assert result
        assert "^XI1;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_get_standby_on_band_change(self, mock_reader, kpa500):
        mock_reader.add_response("^BC1;")
        enabled = await kpa500.get_standby_on_band_change()
        assert enabled is True

    @pytest.mark.asyncio
    async def test_set_standby_on_band_change(self, mock_reader, mock_writer, kpa500):
        mock_reader.add_response("^BC0;")
        result = await kpa500.set_standby_on_band_change(False)
        assert result
        assert "^BC0;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_ping_success(self, mock_reader, kpa500):
        mock_reader.set_ping_response(";")
        result = await kpa500.ping()
        assert result is True

    @pytest.mark.asyncio
    async def test_ping_timeout(self, kpa500):
        result = await kpa500.ping()
        assert result is False

    @pytest.mark.asyncio
    async def test_close(self, mock_writer, kpa500):
        await kpa500.close()
        assert mock_writer._closed is True

    @pytest.mark.asyncio
    async def test_no_response_returns_none(self, kpa500):
        state = await kpa500.get_power_state()
        assert state is None


# =============================================================================
# Power State Detection Tests
# =============================================================================


class TestKPA500DetectPowerState:
    @pytest.mark.asyncio
    async def test_detect_power_on_state_1(self):
        """Device responds with ON1 (powered on)."""
        reader = MockStreamReader()
        writer = MockStreamWriter()
        reader.add_response("^ON1;")

        kpa = KPA500(reader, writer, timeout=0.1)
        await kpa._detect_power_state()

        assert kpa.is_powered_on is True

    @pytest.mark.asyncio
    async def test_detect_power_on_state_0(self):
        """Device responds with ON0 (powered on but in standby)."""
        reader = MockStreamReader()
        writer = MockStreamWriter()
        reader.add_response("^ON0;")

        kpa = KPA500(reader, writer, timeout=0.1)
        await kpa._detect_power_state()

        assert kpa.is_powered_on is True

    @pytest.mark.asyncio
    async def test_detect_power_off_no_response(self):
        """No response indicates bootloader mode."""
        reader = MockStreamReader()
        writer = MockStreamWriter()

        kpa = KPA500(reader, writer, timeout=0.1)
        await kpa._detect_power_state()

        assert kpa.is_powered_on is False

    @pytest.mark.asyncio
    async def test_detect_power_off_echo(self):
        """Echo of command (just 'ON') should be treated as not powered on."""
        reader = MockStreamReader()
        writer = MockStreamWriter()
        reader.add_response("^ON;")  # Echo - no 0 or 1

        kpa = KPA500(reader, writer, timeout=0.1)
        await kpa._detect_power_state()

        assert kpa.is_powered_on is False


# =============================================================================
# Bootloader Power On Tests
# =============================================================================


class TestKPA500BootloaderPowerOn:
    @pytest.mark.asyncio
    async def test_power_on_from_bootloader_sends_P(self, mock_reader, mock_writer):
        """When in bootloader mode, power_on should send b'P' first."""
        kpa = KPA500(mock_reader, mock_writer, timeout=0.01)
        kpa._power_on = False  # Simulate bootloader mode

        # Queue a response for the polling phase
        mock_reader.add_response("^ON1;")

        result = await kpa.power_on()

        # Check that 'P' was sent
        written = mock_writer.get_all_written()
        assert b'P' in written
        assert result is True
        assert kpa.is_powered_on is True

    @pytest.mark.asyncio
    async def test_power_on_from_bootloader_polls_until_response(self, mock_reader, mock_writer):
        """Power on should poll multiple times until device responds."""
        kpa = KPA500(mock_reader, mock_writer, timeout=0.01)
        kpa._power_on = False

        # No response queued - will fail after polling
        result = await kpa.power_on()

        assert result is False
        # Should have sent 'P' followed by multiple ^ON; queries
        written = mock_writer.get_all_written()
        assert b'P' in written
