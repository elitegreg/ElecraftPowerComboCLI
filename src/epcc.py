#!/usr/bin/env python3
"""
Elecraft Power Combo CLI - TUI Application

Control interface for KPA500 amplifier and KAT500 antenna tuner.
"""

import argparse
import logging
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Static, RadioButton, RadioSet
from textual.message import Message
from rich.text import Text

from model import ComboModel, ComboState
from kpa500 import OperatingMode
from kpa500 import Fault as KPAFault
from kat500 import Antenna, Mode as KATMode
from kat500 import Fault as KATFault


# =============================================================================
# Theme Colors (Rich text styles) - Edit these to change the color scheme
# =============================================================================
# Bar graph segment colors (green/yellow/red for low/medium/high)
BAR_SEGMENT_1_LIT = "#00ff00"   # Green lit
BAR_SEGMENT_1_DARK = "#004400"  # Green dark
BAR_SEGMENT_2_LIT = "#ffff00"   # Yellow lit
BAR_SEGMENT_2_DARK = "#444400"  # Yellow dark
BAR_SEGMENT_3_LIT = "#ff0000"   # Red lit
BAR_SEGMENT_3_DARK = "#440000"  # Red dark

# Fault text colors
FAULT_NONE_COLOR = "green"
FAULT_ERROR_COLOR = "bold red"


class StateUpdated(Message):
    """Message posted when state changes."""
    def __init__(self, state: ComboState) -> None:
        self.state = state
        super().__init__()


class SegmentedBarGraph(Static):
    """A horizontal bar graph with colored segments based on value thresholds."""

    value: reactive[float] = reactive(0.0)

    def __init__(
        self,
        thresholds: list[float],
        width: int = 30,
        label: str = "",
        clamp_display: bool = False,
        value_format: str = ".0f",
        **kwargs
    ):
        """
        Create a segmented bar graph.

        Args:
            thresholds: List of boundary values defining segments.
                        e.g., [100, 500, 600, 700] creates 3 segments:
                        [100-500), [500-600), [600-700]
            width: Total character width of the bar
            label: Optional label prefix
            clamp_display: If True, clamp display value to max threshold
            value_format: Format string for value display
        """
        super().__init__(**kwargs)
        self.thresholds = thresholds
        self.min_value = thresholds[0]
        self.max_value = thresholds[-1]
        self.num_segments = len(thresholds) - 1
        self.bar_width = width
        self.label = label
        self.clamp_display = clamp_display
        self.value_format = value_format

        # Calculate character widths proportional to segment ranges
        total_range = self.max_value - self.min_value
        self.segment_chars = []
        chars_allocated = 0
        for i in range(self.num_segments):
            segment_range = thresholds[i + 1] - thresholds[i]
            proportion = segment_range / total_range
            if i == self.num_segments - 1:
                # Last segment gets remaining chars to avoid rounding errors
                chars = self.bar_width - chars_allocated
            else:
                chars = int(proportion * self.bar_width)
            self.segment_chars.append(chars)
            chars_allocated += chars

    def render(self) -> Text:
        text = Text()
        if self.label:
            text.append(f"{self.label} ")

        # Clamp value for bar display but keep actual for text
        display_value = min(self.value, self.max_value) if self.clamp_display else self.value

        for i in range(self.num_segments):
            segment_start = self.thresholds[i]
            segment_end = self.thresholds[i + 1]
            segment_range = segment_end - segment_start
            chars_this_segment = self.segment_chars[i]

            # Calculate how many chars to light in this segment
            if display_value <= segment_start:
                lit_chars = 0
            elif display_value >= segment_end:
                lit_chars = chars_this_segment
            else:
                ratio = (display_value - segment_start) / segment_range
                lit_chars = int(ratio * chars_this_segment)

            # Get colors for this segment
            segment_colors = [
                (BAR_SEGMENT_1_LIT, BAR_SEGMENT_1_DARK),
                (BAR_SEGMENT_2_LIT, BAR_SEGMENT_2_DARK),
                (BAR_SEGMENT_3_LIT, BAR_SEGMENT_3_DARK),
            ]
            lit_color, dark_color = segment_colors[min(i, len(segment_colors) - 1)]

            for j in range(chars_this_segment):
                if j < lit_chars:
                    text.append("█", style=lit_color)
                else:
                    text.append("░", style=dark_color)

        # Show actual value (not clamped)
        text.append(f" {self.value:{self.value_format}}")
        return text

    def watch_value(self, value: float) -> None:
        self.refresh()


class PowerToggle(Static):
    """A power toggle button."""

    on: reactive[bool] = reactive(False)

    class Toggled(Message):
        """Emitted when power is toggled."""
        def __init__(self, value: bool) -> None:
            self.value = value
            super().__init__()

    def render(self) -> Text:
        # Style is controlled via CSS classes
        return Text(" POWER ")

    def on_click(self) -> None:
        self.post_message(self.Toggled(not self.on))

    def watch_on(self, on: bool) -> None:
        self.set_class(on, "power-on")
        self.refresh()


class TuneButton(Static):
    """A tune button that inverts while tuning."""

    tuning: reactive[bool] = reactive(False)

    class Pressed(Message):
        """Emitted when tune is pressed."""
        pass

    def render(self) -> Text:
        return Text(" TUNE ")

    def on_click(self) -> None:
        if not self.tuning:
            self.post_message(self.Pressed())

    def watch_tuning(self, tuning: bool) -> None:
        self.set_class(tuning, "tuning")
        self.refresh()


class FaultButton(Static):
    """A fault indicator button that can be clicked to clear faults."""

    active: reactive[bool] = reactive(False)

    class Pressed(Message):
        """Emitted when fault button is pressed."""
        pass

    def render(self) -> Text:
        return Text(" FAULT ")

    def on_click(self) -> None:
        if self.active:
            self.post_message(self.Pressed())

    def watch_active(self, active: bool) -> None:
        self.set_class(active, "fault-active")
        self.refresh()


class ReadingValue(Static):
    """A reading display with label and value."""

    value: reactive[str] = reactive("")

    def __init__(self, label: str, **kwargs):
        super().__init__(**kwargs)
        self.label = label

    def render(self) -> Text:
        text = Text()
        text.append(f"{self.label}: ")
        text.append(self.value or "---")
        return text

    def watch_value(self, value: str) -> None:
        self.refresh()


class FaultDisplay(Static):
    """A fault display showing device name and fault status."""

    fault_text: reactive[str] = reactive("None")

    def __init__(self, device_name: str, **kwargs):
        super().__init__(**kwargs)
        self.device_name = device_name

    def render(self) -> Text:
        text = Text()
        text.append(f"{self.device_name} Fault: ", style="bold white")
        if self.fault_text == "None":
            text.append(self.fault_text, style=FAULT_NONE_COLOR)
        else:
            text.append(self.fault_text, style=FAULT_ERROR_COLOR)
        return text

    def watch_fault_text(self, fault_text: str) -> None:
        self.refresh()


class ElecraftPowerComboApp(App):
    """Elecraft KPA500/KAT500 Control Application."""

    CSS_PATH = "epcc.tcss"

    def __init__(
        self,
        kpa_port: Optional[str] = None,
        kat_port: Optional[str] = None,
        baudrate: int = 38400,
        kpa_poll_interval: float = 0.25,
        kat_poll_interval: float = 30.0,
        **kwargs
    ):
        super().__init__(**kwargs)
        self._kpa_port = kpa_port
        self._kat_port = kat_port
        self._baudrate = baudrate
        self._kpa_poll_interval = kpa_poll_interval
        self._kat_poll_interval = kat_poll_interval
        self._model: Optional[ComboModel] = None

    def compose(self) -> ComposeResult:
        with Container(id="main"):
            # Title
            yield Static("Elecraft Power Combo (KPA/KAT500)", id="title")

            # Main content area
            with Horizontal(id="content"):
                # Left: Readings panel (yellow when powered on)
                with Container(id="readings"):
                    yield ReadingValue("Power", id="reading-power")
                    yield ReadingValue("Temp", id="reading-temp")
                    yield ReadingValue("Current", id="reading-current")
                    yield ReadingValue("HV", id="reading-hv")
                    yield ReadingValue("Band", id="reading-band")
                    yield ReadingValue("FWD", id="reading-fwd")
                    yield ReadingValue("RFL", id="reading-rfl")
                    yield ReadingValue("Bypass SWR", id="reading-bypass-swr")

                # Right: Controls and meters
                with Container(id="controls"):
                    # Mode selectors and antenna selector stacked
                    with Vertical(id="mode-antenna-section"):
                        yield Static("KPA Mode:", id="kpa-mode-label")
                        with RadioSet(id="mode-select"):
                            yield RadioButton("Standby", id="mode-standby", value=True)
                            yield RadioButton("Operate", id="mode-operate")
                        yield Static("KAT Mode:", id="kat-mode-label")
                        with RadioSet(id="kat-mode-select"):
                            yield RadioButton("Auto", id="kat-auto", value=True)
                            yield RadioButton("Manual", id="kat-manual")
                            yield RadioButton("Bypass", id="kat-bypass")
                        yield Static("Antenna:", id="antenna-label")
                        with RadioSet(id="antenna-select"):
                            yield RadioButton("1", id="ant-1", value=True)
                            yield RadioButton("2", id="ant-2")
                            yield RadioButton("3", id="ant-3")

                    # Power bar graph: [100-500) green, [500-600) yellow, [600-700] red
                    yield SegmentedBarGraph(
                        thresholds=[100, 500, 600, 700],
                        width=40,
                        label="Power  ",
                        id="power-bar",
                    )

                    # KPA SWR bar graph: [1.0-1.5) green, [1.5-2.0) yellow, [2.0-3.0] red
                    yield SegmentedBarGraph(
                        thresholds=[1.0, 1.5, 2.0, 3.0],
                        width=40,
                        label="KPA SWR",
                        clamp_display=True,
                        value_format=".1f",
                        id="kpa-swr-bar",
                    )

                    # KAT SWR bar graph: [1.0-1.5) green, [1.5-2.0) yellow, [2.0-3.0] red
                    yield SegmentedBarGraph(
                        thresholds=[1.0, 1.5, 2.0, 3.0],
                        width=40,
                        label="KAT SWR",
                        clamp_display=True,
                        value_format=".1f",
                        id="kat-swr-bar",
                    )

                    # Buttons row below meters
                    with Horizontal(id="button-row"):
                        yield PowerToggle(id="power-toggle")
                        yield TuneButton(id="tune-btn")

            # Fault section - indicator on left, text on right
            with Container(id="faults"):
                with Horizontal(id="faults-row"):
                    yield FaultButton(id="fault-btn")
                    with Vertical(id="fault-texts"):
                        yield FaultDisplay("KPA", id="kpa-fault")
                        yield FaultDisplay("KAT", id="kat-fault")

        yield Static("Ctrl-Q to quit", id="help-footer")

    async def on_mount(self) -> None:
        """Called when app is mounted. Connect to devices if ports specified."""
        if not self._kpa_port and not self._kat_port:
            self.exit(message="Error: No serial ports specified. Use --kpa-port and/or --kat-port.")
            return

        self._model = ComboModel(
            kpa_poll_interval=self._kpa_poll_interval,
            kat_poll_interval=self._kat_poll_interval,
            on_state_change=self._on_state_change
        )
        connected = await self._model.connect(
            kpa_port=self._kpa_port,
            kat_port=self._kat_port,
            baudrate=self._baudrate
        )
        if connected:
            await self._model.start_polling()
        else:
            # Build error message based on what failed
            errors = []
            if self._kpa_port and not self._model.state.kpa_connected:
                errors.append(f"KPA500 on {self._kpa_port}")
            if self._kat_port and not self._model.state.kat_connected:
                errors.append(f"KAT500 on {self._kat_port}")
            error_msg = f"Error: Failed to connect to {', '.join(errors)}"
            self.exit(message=error_msg)

    async def on_unmount(self) -> None:
        """Called when app is unmounted. Disconnect from devices."""
        if self._model:
            await self._model.disconnect()

    def _on_state_change(self, state: ComboState) -> None:
        """Called by model when state changes. Posts message to update UI."""
        self.post_message(StateUpdated(state))

    def on_state_updated(self, event: StateUpdated) -> None:
        """Handle state update message."""
        self._update_ui(event.state)

    def _update_ui(self, state: ComboState) -> None:
        """Update all UI elements from state."""
        # Power toggle (reflects combined power state)
        power_toggle = self.query_one("#power-toggle", PowerToggle)
        power_toggle.on = state.powered_on

        # Readings panel - yellow when powered on
        readings = self.query_one("#readings")
        readings.set_class(state.powered_on, "powered-on")

        # KPA500 Readings
        self.query_one("#reading-power", ReadingValue).value = f"{state.power_watts}W"
        self.query_one("#reading-temp", ReadingValue).value = f"{state.temperature}°C" if state.temperature else "---"
        self.query_one("#reading-current", ReadingValue).value = f"{state.current:.1f}A" if state.current else "---"
        self.query_one("#reading-hv", ReadingValue).value = f"{state.voltage:.1f}V" if state.voltage else "---"
        self.query_one("#reading-band", ReadingValue).value = state.band.name.replace("BAND_", "") if state.band else "---"

        # KAT500 Readings
        self.query_one("#reading-fwd", ReadingValue).value = f"{state.forward_power}" if state.forward_power is not None else "---"
        self.query_one("#reading-rfl", ReadingValue).value = f"{state.reflected_power}" if state.reflected_power is not None else "---"
        self.query_one("#reading-bypass-swr", ReadingValue).value = f"{state.kat_swr_bypass:.2f}" if state.kat_swr_bypass is not None else "---"

        # Bar graphs
        self.query_one("#power-bar", SegmentedBarGraph).value = float(state.power_watts)
        self.query_one("#kpa-swr-bar", SegmentedBarGraph).value = state.kpa_swr
        self.query_one("#kat-swr-bar", SegmentedBarGraph).value = state.kat_swr

        # Operating mode radio buttons (use RadioSet._selected for proper mutual exclusivity)
        if state.kpa_operating_mode is not None:
            mode_index = 0 if state.kpa_operating_mode == OperatingMode.STANDBY else 1
            self.query_one("#mode-select", RadioSet)._selected = mode_index

        # KAT mode selection
        if state.kat_mode is not None:
            kat_mode_map = {KATMode.AUTO: 0, KATMode.MANUAL: 1, KATMode.BYPASS: 2}
            if state.kat_mode in kat_mode_map:
                self.query_one("#kat-mode-select", RadioSet)._selected = kat_mode_map[state.kat_mode]

        # Antenna selection
        if state.antenna is not None:
            antenna_map = {Antenna.ANT1: 0, Antenna.ANT2: 1, Antenna.ANT3: 2}
            if state.antenna in antenna_map:
                self.query_one("#antenna-select", RadioSet)._selected = antenna_map[state.antenna]

        # Tune button state
        tune_btn = self.query_one("#tune-btn", TuneButton)
        tune_btn.tuning = state.is_tuning

        # Fault displays
        kpa_has_fault = state.kpa_fault is not None and state.kpa_fault != KPAFault.NONE
        kat_has_fault = state.kat_fault is not None and state.kat_fault != KATFault.NONE

        # Fault button - active if either device has a fault
        fault_btn = self.query_one("#fault-btn", FaultButton)
        fault_btn.active = kpa_has_fault or kat_has_fault

        kpa_fault_display = self.query_one("#kpa-fault", FaultDisplay)
        if kpa_has_fault:
            kpa_fault_display.fault_text = state.kpa_fault.name
        else:
            kpa_fault_display.fault_text = "None"

        kat_fault_display = self.query_one("#kat-fault", FaultDisplay)
        if kat_has_fault:
            kat_fault_display.fault_text = state.kat_fault.name
        else:
            kat_fault_display.fault_text = "None"

    async def on_power_toggle_toggled(self, event: PowerToggle.Toggled) -> None:
        """Handle power toggle click."""
        if self._model:
            await self._model.toggle_power()

    async def on_tune_button_pressed(self, event: TuneButton.Pressed) -> None:
        """Handle tune button click."""
        if self._model:
            await self._model.kat_full_tune()

    async def on_fault_button_pressed(self, event: FaultButton.Pressed) -> None:
        """Handle fault button click to clear faults."""
        if self._model:
            await self._model.kpa_clear_fault()
            await self._model.kat_clear_fault()

    async def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Handle radio button changes."""
        if not self._model:
            return

        radio_set_id = event.radio_set.id
        state = self._model.state

        if radio_set_id == "mode-select":
            # Only send command if different from current state
            if event.index == 0 and state.kpa_operating_mode != OperatingMode.STANDBY:
                await self._model.kpa_set_standby()
            elif event.index == 1 and state.kpa_operating_mode != OperatingMode.OPERATE:
                await self._model.kpa_set_operate()
        elif radio_set_id == "kat-mode-select":
            mode_map = {0: KATMode.AUTO, 1: KATMode.MANUAL, 2: KATMode.BYPASS}
            if event.index in mode_map and state.kat_mode != mode_map[event.index]:
                await self._model.kat_set_mode(mode_map[event.index])
        elif radio_set_id == "antenna-select":
            antenna_map = {0: Antenna.ANT1, 1: Antenna.ANT2, 2: Antenna.ANT3}
            if event.index in antenna_map and state.antenna != antenna_map[event.index]:
                await self._model.kat_set_antenna(antenna_map[event.index])


def main():
    parser = argparse.ArgumentParser(description="Elecraft Power Combo CLI")
    parser.add_argument("--kpa-port", "-k", help="KPA500 serial port (e.g., /dev/ttyUSB0)")
    parser.add_argument("--kat-port", "-t", help="KAT500 serial port (e.g., /dev/ttyUSB1)")
    parser.add_argument("--baudrate", "-b", type=int, default=38400, help="Baud rate (default: 38400)")
    parser.add_argument(
        "--kpa-poll-interval",
        type=float,
        default=0.25,
        help="KPA500 poll interval in seconds (default: 0.25)"
    )
    parser.add_argument(
        "--kat-poll-interval",
        type=float,
        default=30.0,
        help="KAT500 background poll interval in seconds (default: 30)"
    )
    parser.add_argument(
        "--log-file",
        type=str,
        default=None,
        help="Log file path (logging disabled if not specified)"
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Log level (default: INFO)"
    )

    args = parser.parse_args()

    # Configure logging if log file specified
    if args.log_file:
        logging.basicConfig(
            filename=args.log_file,
            level=getattr(logging, args.log_level),
            format="%(asctime)s %(name)s %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    app = ElecraftPowerComboApp(
        kpa_port=args.kpa_port,
        kat_port=args.kat_port,
        baudrate=args.baudrate,
        kpa_poll_interval=args.kpa_poll_interval,
        kat_poll_interval=args.kat_poll_interval,
    )
    app.run()


if __name__ == "__main__":
    main()
