"""Tests for KAT500 module."""

import asyncio
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
def kat500(mock_reader, mock_writer):
    return KAT500(mock_reader, mock_writer, timeout=0.1)


# =============================================================================
# Enum Tests
# =============================================================================


class TestEnums:
    def test_band_values(self):
        assert Band.BAND_160M == 0
        assert Band.BAND_80M == 1
        assert Band.BAND_6M == 10

    def test_mode_values(self):
        assert Mode.BYPASS.value == "B"
        assert Mode.MANUAL.value == "M"
        assert Mode.AUTO.value == "A"

    def test_power_state_values(self):
        assert PowerState.OFF == 0
        assert PowerState.ON == 1

    def test_fault_values(self):
        assert Fault.NONE == 0
        assert Fault.NO_MATCH == 1
        assert Fault.POWER_ABOVE_DESIGN_LIMIT == 2
        assert Fault.POWER_ABOVE_RELAY_SWITCH_LIMIT == 3

    def test_antenna_values(self):
        assert Antenna.ANT1 == 1
        assert Antenna.ANT2 == 2
        assert Antenna.ANT3 == 3

    def test_baud_rate_values(self):
        assert BaudRate.BAUD_4800 == 0
        assert BaudRate.BAUD_38400 == 3

    def test_side_values(self):
        assert Side.TRANSMITTER.value == "T"
        assert Side.ANTENNA.value == "A"

    def test_bypass_state_values(self):
        assert BypassState.NOT_BYPASSED.value == "N"
        assert BypassState.BYPASSED.value == "B"


# =============================================================================
# Power Control Tests
# =============================================================================


class TestPowerControl:
    @pytest.mark.asyncio
    async def test_get_power_state_on(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("PS1;")
        state = await kat500.get_power_state()
        assert state == PowerState.ON
        assert "PS;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_get_power_state_off(self, mock_reader, kat500):
        mock_reader.add_response("PS0;")
        state = await kat500.get_power_state()
        assert state == PowerState.OFF

    @pytest.mark.asyncio
    async def test_set_power_on(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("PS1;")
        result = await kat500.power_on()
        assert result
        assert "PS1;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_set_power_off(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("PS0;")
        result = await kat500.power_off()
        assert result
        assert "PS0;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_get_initial_power_state(self, mock_reader, kat500):
        mock_reader.add_response("PSI1;")
        state = await kat500.get_initial_power_state()
        assert state == PowerState.ON

    @pytest.mark.asyncio
    async def test_set_initial_power_state(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("PSI0;")
        result = await kat500.set_initial_power_state(PowerState.OFF)
        assert result
        assert "PSI0;" in mock_writer.get_last_command()


# =============================================================================
# Mode Control Tests
# =============================================================================


class TestModeControl:
    @pytest.mark.asyncio
    async def test_get_mode_bypass(self, mock_reader, kat500):
        mock_reader.add_response("MDB;")
        mode = await kat500.get_mode()
        assert mode == Mode.BYPASS

    @pytest.mark.asyncio
    async def test_get_mode_manual(self, mock_reader, kat500):
        mock_reader.add_response("MDM;")
        mode = await kat500.get_mode()
        assert mode == Mode.MANUAL

    @pytest.mark.asyncio
    async def test_get_mode_auto(self, mock_reader, kat500):
        mock_reader.add_response("MDA;")
        mode = await kat500.get_mode()
        assert mode == Mode.AUTO

    @pytest.mark.asyncio
    async def test_set_bypass_mode(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("MDB;")
        result = await kat500.set_bypass_mode()
        assert result
        assert "MDB;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_set_manual_mode(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("MDM;")
        result = await kat500.set_manual_mode()
        assert result
        assert "MDM;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_set_auto_mode(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("MDA;")
        result = await kat500.set_auto_mode()
        assert result
        assert "MDA;" in mock_writer.get_last_command()


# =============================================================================
# Band Control Tests
# =============================================================================


class TestBandControl:
    @pytest.mark.asyncio
    async def test_get_band(self, mock_reader, kat500):
        mock_reader.add_response("BN05;")
        band = await kat500.get_band()
        assert band == Band.BAND_20M

    @pytest.mark.asyncio
    async def test_set_band(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("BN03;")
        result = await kat500.set_band(Band.BAND_40M)
        assert result
        assert "BN03;" in mock_writer.get_last_command()


# =============================================================================
# Antenna Control Tests
# =============================================================================


class TestAntennaControl:
    @pytest.mark.asyncio
    async def test_get_antenna(self, mock_reader, kat500):
        mock_reader.add_response("AN1;")
        antenna = await kat500.get_antenna()
        assert antenna == Antenna.ANT1

    @pytest.mark.asyncio
    async def test_set_antenna(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("AN2;")
        result = await kat500.set_antenna(Antenna.ANT2)
        assert result
        assert "AN2;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_next_antenna(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("AN2;")
        result = await kat500.next_antenna()
        assert result
        assert "AN0;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_get_antenna_preference(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("AP053;")
        pref = await kat500.get_antenna_preference(Band.BAND_20M)
        assert pref == 3
        assert "AP05;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_set_antenna_preference(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("AP102;")
        result = await kat500.set_antenna_preference(Band.BAND_6M, 2)
        assert result
        assert "AP102;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_set_antenna_preference_invalid(self, kat500):
        with pytest.raises(ValueError):
            await kat500.set_antenna_preference(Band.BAND_20M, 5)

    @pytest.mark.asyncio
    async def test_get_antenna_enabled(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("AE0511;")
        enabled = await kat500.get_antenna_enabled(Band.BAND_20M, Antenna.ANT1)
        assert enabled is True

    @pytest.mark.asyncio
    async def test_set_antenna_enabled(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("AE0510;")
        result = await kat500.set_antenna_enabled(Band.BAND_20M, Antenna.ANT1, False)
        assert result
        assert "AE0510;" in mock_writer.get_last_command()


# =============================================================================
# Bypass Control Tests
# =============================================================================


class TestBypassControl:
    @pytest.mark.asyncio
    async def test_get_bypass_not_bypassed(self, mock_reader, kat500):
        mock_reader.add_response("BYPN;")
        state = await kat500.get_bypass()
        assert state == BypassState.NOT_BYPASSED

    @pytest.mark.asyncio
    async def test_get_bypass_bypassed(self, mock_reader, kat500):
        mock_reader.add_response("BYPB;")
        state = await kat500.get_bypass()
        assert state == BypassState.BYPASSED

    @pytest.mark.asyncio
    async def test_set_bypass(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("BYPB;")
        result = await kat500.set_bypass(BypassState.BYPASSED)
        assert result
        assert "BYPB;" in mock_writer.get_last_command()


# =============================================================================
# Tuning Control Tests
# =============================================================================


class TestTuningControl:
    @pytest.mark.asyncio
    async def test_tune(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("T;")  # Response to T command
        mock_reader.add_response("TP1;")  # Response to is_tuning check
        result = await kat500.tune()
        assert result

    @pytest.mark.asyncio
    async def test_full_tune(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("FT;")  # Response to FT command
        mock_reader.add_response("TP1;")  # Response to is_tuning check
        result = await kat500.full_tune()
        assert result

    @pytest.mark.asyncio
    async def test_is_tuning_true(self, mock_reader, kat500):
        mock_reader.add_response("TP1;")
        result = await kat500.is_tuning()
        assert result is True

    @pytest.mark.asyncio
    async def test_is_tuning_false(self, mock_reader, kat500):
        mock_reader.add_response("TP0;")
        result = await kat500.is_tuning()
        assert result is False

    @pytest.mark.asyncio
    async def test_memory_tune(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("MT;")
        result = await kat500.memory_tune()
        assert result
        assert "MT;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_memory_tune_with_frequency(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("MT;")
        result = await kat500.memory_tune(14200)
        assert result
        assert "MT 14200;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_set_frequency(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("F 14200;")
        result = await kat500.set_frequency(14200)
        assert result
        assert "F 14200;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_get_frequency(self, mock_reader, kat500):
        mock_reader.add_response("F 14200;")
        freq = await kat500.get_frequency()
        assert freq == 14200

    @pytest.mark.asyncio
    async def test_save_memory(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("SM;")
        result = await kat500.save_memory()
        assert result
        assert "SM;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_save_memory_with_frequency(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("SM;")
        result = await kat500.save_memory(14250)
        assert result
        assert "SM 14250;" in mock_writer.get_last_command()


# =============================================================================
# Tuner Network Control Tests
# =============================================================================


class TestTunerNetworkControl:
    @pytest.mark.asyncio
    async def test_get_side_transmitter(self, mock_reader, kat500):
        mock_reader.add_response("SIDET;")
        side = await kat500.get_side()
        assert side == Side.TRANSMITTER

    @pytest.mark.asyncio
    async def test_get_side_antenna(self, mock_reader, kat500):
        mock_reader.add_response("SIDEA;")
        side = await kat500.get_side()
        assert side == Side.ANTENNA

    @pytest.mark.asyncio
    async def test_set_side(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("SIDET;")
        result = await kat500.set_side(Side.TRANSMITTER)
        assert result
        assert "SIDET;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_get_inductors(self, mock_reader, kat500):
        mock_reader.add_response("L80;")
        inductors = await kat500.get_inductors()
        assert inductors == 0x80

    @pytest.mark.asyncio
    async def test_set_inductors(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("LFF;")
        result = await kat500.set_inductors(0xFF)
        assert result
        assert "LFF;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_set_inductors_invalid(self, kat500):
        with pytest.raises(ValueError):
            await kat500.set_inductors(0x100)

    @pytest.mark.asyncio
    async def test_get_capacitors(self, mock_reader, kat500):
        mock_reader.add_response("CC1;")
        capacitors = await kat500.get_capacitors()
        assert capacitors == 0xC1

    @pytest.mark.asyncio
    async def test_set_capacitors(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("C00;")
        result = await kat500.set_capacitors(0x00)
        assert result
        assert "C00;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_set_capacitors_invalid(self, kat500):
        with pytest.raises(ValueError):
            await kat500.set_capacitors(0x1FF)


# =============================================================================
# Fault Handling Tests
# =============================================================================


class TestFaultHandling:
    @pytest.mark.asyncio
    async def test_get_fault_none(self, mock_reader, kat500):
        mock_reader.add_response("FLT0;")
        fault = await kat500.get_fault()
        assert fault == Fault.NONE

    @pytest.mark.asyncio
    async def test_get_fault_no_match(self, mock_reader, kat500):
        mock_reader.add_response("FLT1;")
        fault = await kat500.get_fault()
        assert fault == Fault.NO_MATCH

    @pytest.mark.asyncio
    async def test_get_fault_power_design_limit(self, mock_reader, kat500):
        mock_reader.add_response("FLT2;")
        fault = await kat500.get_fault()
        assert fault == Fault.POWER_ABOVE_DESIGN_LIMIT

    @pytest.mark.asyncio
    async def test_get_fault_relay_switch_limit(self, mock_reader, kat500):
        mock_reader.add_response("FLT3;")
        fault = await kat500.get_fault()
        assert fault == Fault.POWER_ABOVE_RELAY_SWITCH_LIMIT

    @pytest.mark.asyncio
    async def test_clear_fault(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("FLTC;")
        result = await kat500.clear_fault()
        assert result
        assert "FLTC;" in mock_writer.get_last_command()


# =============================================================================
# VSWR and Power Readings Tests
# =============================================================================


class TestVSWRReadings:
    @pytest.mark.asyncio
    async def test_get_vswr(self, mock_reader, kat500):
        mock_reader.add_response("VSWR 1.50;")
        vswr = await kat500.get_vswr()
        assert vswr == 1.50

    @pytest.mark.asyncio
    async def test_get_vswr_bypass(self, mock_reader, kat500):
        mock_reader.add_response("VSWRB 2.50;")
        vswr = await kat500.get_vswr_bypass()
        assert vswr == 2.50

    @pytest.mark.asyncio
    async def test_get_forward_voltage(self, mock_reader, kat500):
        mock_reader.add_response("VFWD 2048;")
        voltage = await kat500.get_forward_voltage()
        assert voltage == 2048

    @pytest.mark.asyncio
    async def test_get_reflected_voltage(self, mock_reader, kat500):
        mock_reader.add_response("VRFL 512;")
        voltage = await kat500.get_reflected_voltage()
        assert voltage == 512


# =============================================================================
# SWR Threshold Tests
# =============================================================================


class TestSWRThresholds:
    @pytest.mark.asyncio
    async def test_get_auto_tune_threshold(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("ST05A1.80;")
        threshold = await kat500.get_auto_tune_threshold(Band.BAND_20M)
        assert threshold == 1.80

    @pytest.mark.asyncio
    async def test_set_auto_tune_threshold(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("ST05A1.75;")
        result = await kat500.set_auto_tune_threshold(Band.BAND_20M, 1.75)
        assert result
        assert "ST05A1.75;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_set_auto_tune_threshold_too_low(self, kat500):
        with pytest.raises(ValueError):
            await kat500.set_auto_tune_threshold(Band.BAND_20M, 1.2)

    @pytest.mark.asyncio
    async def test_get_bypass_threshold(self, mock_reader, kat500):
        mock_reader.add_response("ST05B1.20;")
        threshold = await kat500.get_bypass_threshold(Band.BAND_20M)
        assert threshold == 1.20

    @pytest.mark.asyncio
    async def test_set_bypass_threshold(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("ST05B1.30;")
        result = await kat500.set_bypass_threshold(Band.BAND_20M, 1.30)
        assert result

    @pytest.mark.asyncio
    async def test_get_key_interrupt_threshold(self, mock_reader, kat500):
        mock_reader.add_response("ST05K2.00;")
        threshold = await kat500.get_key_interrupt_threshold(Band.BAND_20M)
        assert threshold == 2.00

    @pytest.mark.asyncio
    async def test_set_key_interrupt_threshold(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("ST05K3.00;")
        result = await kat500.set_key_interrupt_threshold(Band.BAND_20M, 3.00)
        assert result


# =============================================================================
# Amplifier Key Interrupt Tests
# =============================================================================


class TestAmpKeyInterrupt:
    @pytest.mark.asyncio
    async def test_get_amp_key_interrupt_power(self, mock_reader, kat500):
        mock_reader.add_response("AKIP 30W VFWD 1234;")
        power = await kat500.get_amp_key_interrupt_power()
        assert power == 30

    @pytest.mark.asyncio
    async def test_set_amp_key_interrupt_power(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("AKIP 1500W VFWD 1234;")
        result = await kat500.set_amp_key_interrupt_power(1500)
        assert result
        assert "AKIP 1500;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_get_amp_key_interrupt(self, mock_reader, kat500):
        mock_reader.add_response("AMPI1;")
        interrupted = await kat500.get_amp_key_interrupt()
        assert interrupted is True

    @pytest.mark.asyncio
    async def test_set_amp_key_interrupt(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("AMPI0;")
        result = await kat500.set_amp_key_interrupt(False)
        assert result
        assert "AMPI0;" in mock_writer.get_last_command()


# =============================================================================
# Attenuator Control Tests
# =============================================================================


class TestAttenuatorControl:
    @pytest.mark.asyncio
    async def test_get_attenuator_on(self, mock_reader, kat500):
        mock_reader.add_response("ATTN1;")
        enabled = await kat500.get_attenuator()
        assert enabled is True

    @pytest.mark.asyncio
    async def test_get_attenuator_off(self, mock_reader, kat500):
        mock_reader.add_response("ATTN0;")
        enabled = await kat500.get_attenuator()
        assert enabled is False

    @pytest.mark.asyncio
    async def test_set_attenuator(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("ATTN1;")
        result = await kat500.set_attenuator(True)
        assert result
        assert "ATTN1;" in mock_writer.get_last_command()


# =============================================================================
# Memory Control Tests
# =============================================================================


class TestMemoryControl:
    @pytest.mark.asyncio
    async def test_erase_memory_all_antennas(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("EM050;")
        result = await kat500.erase_memory(Band.BAND_20M)
        assert result
        assert "EM050;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_erase_memory_specific_antenna(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("EM052;")
        result = await kat500.erase_memory(Band.BAND_20M, antenna=2)
        assert result
        assert "EM052;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_erase_memory_invalid_antenna(self, kat500):
        with pytest.raises(ValueError):
            await kat500.erase_memory(Band.BAND_20M, antenna=5)

    @pytest.mark.asyncio
    async def test_erase_all_memory(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("EEINIT;")
        result = await kat500.erase_all_memory()
        assert result
        assert "EEINIT;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_get_auto_memory_tune(self, mock_reader, kat500):
        mock_reader.add_response("MTA1;")
        enabled = await kat500.get_auto_memory_tune()
        assert enabled is True

    @pytest.mark.asyncio
    async def test_set_auto_memory_tune(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("MTA0;")
        result = await kat500.set_auto_memory_tune(False)
        assert result
        assert "MTA0;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_get_manual_memory_tune(self, mock_reader, kat500):
        mock_reader.add_response("MTM1;")
        enabled = await kat500.get_manual_memory_tune()
        assert enabled is True

    @pytest.mark.asyncio
    async def test_set_manual_memory_tune(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("MTM0;")
        result = await kat500.set_manual_memory_tune(False)
        assert result
        assert "MTM0;" in mock_writer.get_last_command()


# =============================================================================
# Sleep Control Tests
# =============================================================================


class TestSleepControl:
    @pytest.mark.asyncio
    async def test_get_sleep_enabled(self, mock_reader, kat500):
        mock_reader.add_response("SL1;")
        enabled = await kat500.get_sleep_enabled()
        assert enabled is True

    @pytest.mark.asyncio
    async def test_set_sleep_enabled(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("SL0;")
        result = await kat500.set_sleep_enabled(False)
        assert result
        assert "SL0;" in mock_writer.get_last_command()


# =============================================================================
# Device Information Tests
# =============================================================================


class TestDeviceInformation:
    @pytest.mark.asyncio
    async def test_get_serial_number(self, mock_reader, kat500):
        mock_reader.add_response("SN 12345;")
        sn = await kat500.get_serial_number()
        assert sn == "12345"

    @pytest.mark.asyncio
    async def test_get_firmware_version(self, mock_reader, kat500):
        mock_reader.add_response("RV02.16;")
        version = await kat500.get_firmware_version()
        assert version == "02.16"

    @pytest.mark.asyncio
    async def test_identify(self, mock_reader, kat500):
        mock_reader.add_response("IKAT500;")
        ident = await kat500.identify()
        assert ident == "KAT500"

    @pytest.mark.asyncio
    async def test_get_baudrate(self, mock_reader, kat500):
        mock_reader.add_response("BR3;")
        rate = await kat500.get_baudrate()
        assert rate == BaudRate.BAUD_38400

    @pytest.mark.asyncio
    async def test_set_baudrate(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("BR2;")
        result = await kat500.set_baudrate(BaudRate.BAUD_19200)
        assert result
        assert "BR2;" in mock_writer.get_last_command()


# =============================================================================
# Reset Tests
# =============================================================================


class TestReset:
    @pytest.mark.asyncio
    async def test_reset_with_save(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("RST1;")
        result = await kat500.reset(save_state=True)
        assert result
        assert "RST1;" in mock_writer.get_last_command()

    @pytest.mark.asyncio
    async def test_reset_without_save(self, mock_reader, mock_writer, kat500):
        mock_reader.add_response("RST0;")
        result = await kat500.reset(save_state=False)
        assert result
        assert "RST0;" in mock_writer.get_last_command()


# =============================================================================
# Connection Tests
# =============================================================================


class TestConnection:
    @pytest.mark.asyncio
    async def test_ping_success(self, mock_reader, kat500):
        mock_reader.set_ping_response(";")
        result = await kat500.ping()
        assert result is True

    @pytest.mark.asyncio
    async def test_ping_timeout(self, kat500):
        result = await kat500.ping()
        assert result is False

    @pytest.mark.asyncio
    async def test_close(self, mock_writer, kat500):
        await kat500.close()
        assert mock_writer._closed is True

    @pytest.mark.asyncio
    async def test_no_response_returns_none(self, kat500):
        state = await kat500.get_power_state()
        assert state is None
