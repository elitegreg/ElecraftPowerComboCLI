#!/usr/bin/env python3
"""
Elecraft Power Combo CLI - TUI Application

Control interface for KPA500 amplifier and KAT500 antenna tuner.
"""

import argparse
import asyncio
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Static, Button, RadioButton, RadioSet
from textual.message import Message
from rich.text import Text
from rich.style import Style

from model import KPA500Model, KPA500State
from kpa500 import Band, Fault, OperatingMode


class StateUpdated(Message):
    """Message posted when KPA500 state changes."""
    def __init__(self, state: KPA500State) -> None:
        self.state = state
        super().__init__()


class SegmentedBarGraph(Static):
    """A horizontal bar graph with colored segments based on value thresholds."""

    value: reactive[float] = reactive(0.0)

    def __init__(
        self,
        min_value: float,
        max_value: float,
        segments: list[tuple[float, str, str]],
        width: int = 30,
        label: str = "",
        clamp_display: bool = False,
        value_format: str = ".0f",
        **kwargs
    ):
        super().__init__(**kwargs)
        self.min_value = min_value
        self.max_value = max_value
        self.segments = segments
        self.bar_width = width
        self.label = label
        self.clamp_display = clamp_display
        self.value_format = value_format

    def render(self) -> Text:
        text = Text()
        if self.label:
            text.append(f"{self.label}: ", style="bold white")

        # Clamp value for bar display but keep actual for text
        display_value = min(self.value, self.max_value) if self.clamp_display else self.value

        total_range = self.max_value - self.min_value
        current_pos = 0

        for i, (threshold, dark_color, lit_color) in enumerate(self.segments):
            prev_threshold = self.segments[i - 1][0] if i > 0 else self.min_value
            segment_range = threshold - prev_threshold
            segment_chars = int((segment_range / total_range) * self.bar_width)

            if i == len(self.segments) - 1:
                segment_chars = self.bar_width - current_pos

            lit_threshold = (display_value - prev_threshold) / segment_range if segment_range > 0 else 0
            lit_chars = int(lit_threshold * segment_chars) if display_value > prev_threshold else 0
            lit_chars = min(lit_chars, segment_chars)

            if display_value >= threshold:
                lit_chars = segment_chars

            for j in range(segment_chars):
                if j < lit_chars:
                    text.append("█", style=Style(color=lit_color))
                else:
                    text.append("░", style=Style(color=dark_color))

            current_pos += segment_chars

        # Show actual value (not clamped)
        text.append(f" {self.value:{self.value_format}}", style="bold white")
        return text

    def watch_value(self, value: float) -> None:
        self.refresh()


class FaultIndicator(Static):
    """A fault indicator that shows dark red normally, bright red when active."""

    active: reactive[bool] = reactive(False)

    def render(self) -> Text:
        if self.active:
            return Text(" FAULT ", style=Style(color="white", bgcolor="#ff0000", bold=True))
        else:
            return Text(" FAULT ", style=Style(color="#880000", bgcolor="#400000"))

    def watch_active(self, active: bool) -> None:
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
        if self.on:
            return Text(" POWER ", style=Style(color="white", bgcolor="#00aa00", bold=True))
        else:
            return Text(" POWER ", style=Style(color="#666666", bgcolor="#003300"))

    def on_click(self) -> None:
        self.post_message(self.Toggled(not self.on))

    def watch_on(self, on: bool) -> None:
        self.refresh()


class ReadingValue(Static):
    """A reading display with label and value."""

    value: reactive[str] = reactive("")

    def __init__(self, label: str, **kwargs):
        super().__init__(**kwargs)
        self.label = label

    def render(self) -> Text:
        text = Text()
        text.append(f"{self.label}: ", style="bold")
        text.append(self.value or "---")
        return text

    def watch_value(self, value: str) -> None:
        self.refresh()


class ElecraftPowerComboApp(App):
    """Elecraft KPA500/KAT500 Control Application."""

    CSS_PATH = "epcc.tcss"

    def __init__(
        self,
        serial_port: Optional[str] = None,
        baudrate: int = 38400,
        poll_interval: float = 0.25,
        **kwargs
    ):
        super().__init__(**kwargs)
        self._serial_port = serial_port
        self._baudrate = baudrate
        self._poll_interval = poll_interval
        self._model: Optional[KPA500Model] = None
        self._updating_from_model = False  # Prevent feedback loops

    def compose(self) -> ComposeResult:
        # KPA500 Amplifier Section
        with Container(id="amplifier"):
            yield Static("Elecraft KPA500 Amplifier", id="amp-title")
            with Horizontal(id="amp-content"):
                # Left: Readings panel
                with Container(id="readings"):
                    yield ReadingValue("Power", id="reading-power")
                    yield ReadingValue("SWR", id="reading-swr")
                    yield ReadingValue("Temp", id="reading-temp")
                    yield ReadingValue("Current", id="reading-current")
                    yield ReadingValue("HV", id="reading-hv")
                    yield ReadingValue("Band", id="reading-band")

                # Right: Controls panel
                with Container(id="controls"):
                    with Horizontal(id="control-row"):
                        yield PowerToggle(id="power-toggle")
                        with RadioSet(id="mode-select"):
                            yield RadioButton("Standby", id="mode-standby", value=True)
                            yield RadioButton("Operate", id="mode-operate")
                        yield FaultIndicator(id="fault")

                    # Power bar graph (0-700W)
                    yield SegmentedBarGraph(
                        min_value=0,
                        max_value=700,
                        segments=[
                            (500, "#004400", "#00ff00"),
                            (600, "#444400", "#ffff00"),
                            (700, "#440000", "#ff0000"),
                        ],
                        width=40,
                        label="Power",
                        id="power-bar",
                    )

                    # SWR bar graph (1.0-3.0, clamped display but shows actual value)
                    yield SegmentedBarGraph(
                        min_value=1.0,
                        max_value=3.0,
                        segments=[
                            (1.5, "#004400", "#00ff00"),  # Green: 1.0-1.5
                            (2.0, "#444400", "#ffff00"),  # Yellow: 1.5-2.0
                            (3.0, "#440000", "#ff0000"),  # Red: 2.0-3.0
                        ],
                        width=40,
                        label="SWR",
                        clamp_display=True,
                        value_format=".1f",
                        id="swr-bar",
                    )

        # KAT500 Antenna Tuner Section (placeholder for now)
        with Container(id="tuner"):
            yield Static("Elecraft KAT500 Antenna Tuner", id="tuner-title")
            with Vertical(id="tuner-content"):
                with Horizontal(id="tuner-row1"):
                    with RadioSet(id="tuner-mode"):
                        yield RadioButton("Auto", value=True)
                        yield RadioButton("Manual")
                        yield RadioButton("Bypass")
                    yield Button("Tune", id="tune-btn", variant="primary")
                    yield Static("SWR: 1.0", id="tuner-swr")

                with Horizontal(id="tuner-row2"):
                    with RadioSet(id="antenna-select"):
                        yield RadioButton("Antenna 1", value=True)
                        yield RadioButton("Antenna 2")
                        yield RadioButton("Antenna 3")

        yield Static("Ctrl-Q to quit", id="help-footer")

    async def on_mount(self) -> None:
        """Called when app is mounted. Connect to KPA500 if port specified."""
        if self._serial_port:
            self._model = KPA500Model(
                poll_interval=self._poll_interval,
                on_state_change=self._on_state_change
            )
            connected = await self._model.connect(self._serial_port, self._baudrate)
            if connected:
                await self._model.start_polling()
            else:
                self.notify("Failed to connect to KPA500", severity="error")

    async def on_unmount(self) -> None:
        """Called when app is unmounted. Disconnect from KPA500."""
        if self._model:
            await self._model.disconnect()

    def _on_state_change(self, state: KPA500State) -> None:
        """Called by model when state changes. Posts message to update UI."""
        self.post_message(StateUpdated(state))

    def on_state_updated(self, event: StateUpdated) -> None:
        """Handle state update message."""
        self._update_ui(event.state)

    def _update_ui(self, state: KPA500State) -> None:
        """Update all UI elements from state."""
        self._updating_from_model = True
        try:
            # Power toggle
            power_toggle = self.query_one("#power-toggle", PowerToggle)
            power_toggle.on = state.powered_on

            # Readings panel - yellow when powered on, dark when off
            readings = self.query_one("#readings")
            readings.set_class(state.powered_on, "powered-on")

            # Readings
            self.query_one("#reading-power", ReadingValue).value = f"{state.power_watts}W"
            self.query_one("#reading-swr", ReadingValue).value = f"{state.swr:.1f}"
            self.query_one("#reading-temp", ReadingValue).value = f"{state.temperature}°C" if state.temperature else "---"
            self.query_one("#reading-current", ReadingValue).value = f"{state.current:.1f}A" if state.current else "---"
            self.query_one("#reading-hv", ReadingValue).value = f"{state.voltage:.1f}V" if state.voltage else "---"
            self.query_one("#reading-band", ReadingValue).value = state.band.name.replace("BAND_", "") if state.band else "---"

            # Bar graphs
            self.query_one("#power-bar", SegmentedBarGraph).value = float(state.power_watts)
            self.query_one("#swr-bar", SegmentedBarGraph).value = state.swr

            # Operating mode radio buttons
            if state.operating_mode is not None:
                if state.operating_mode == OperatingMode.STANDBY:
                    self.query_one("#mode-standby", RadioButton).value = True
                else:
                    self.query_one("#mode-operate", RadioButton).value = True

            # Fault indicator
            fault_indicator = self.query_one("#fault", FaultIndicator)
            fault_indicator.active = state.fault is not None and state.fault != Fault.NONE
        finally:
            self._updating_from_model = False

    async def on_power_toggle_toggled(self, event: PowerToggle.Toggled) -> None:
        """Handle power toggle click."""
        if self._model:
            await self._model.toggle_power()

    async def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        """Handle radio button changes."""
        if not self._model or self._updating_from_model:
            return

        radio_set_id = event.radio_set.id

        if radio_set_id == "mode-select":
            if event.index == 0:
                await self._model.set_standby()
            else:
                await self._model.set_operate()


def main():
    parser = argparse.ArgumentParser(description="Elecraft Power Combo CLI")
    parser.add_argument("--port", "-p", help="Serial port (e.g., /dev/ttyUSB0)")
    parser.add_argument("--baudrate", "-b", type=int, default=38400, help="Baud rate (default: 38400)")
    parser.add_argument("--poll-interval", type=float, default=0.25, help="Poll interval in seconds (default: 0.25)")

    args = parser.parse_args()

    app = ElecraftPowerComboApp(
        serial_port=args.port,
        baudrate=args.baudrate,
        poll_interval=args.poll_interval
    )
    app.run()


if __name__ == "__main__":
    main()
