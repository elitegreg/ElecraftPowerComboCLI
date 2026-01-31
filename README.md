# Elecraft Power Combo CLI (EPCC)

A Python Textual TUI application for remote control of Elecraft KPA500 amplifier and KAT500 antenna tuner via serial port.

## Project Structure

```
src/
├── epcc.py      # Main TUI application with custom widgets
├── epcc.tcss    # Textual CSS styling
├── kpa500.py    # KPA500 async serial interface module
└── model.py     # Application model bridging TUI and hardware
tests/
├── conftest.py        # pytest configuration with CLI options
├── test_kpa500.py     # Unit tests for KPA500 module
└── kpa500_live_test.py # Live hardware integration tests
```

## Technology Stack

| Component | Details |
|-----------|---------|
| Python | 3.12+ |
| Textual | TUI framework |
| Rich | Terminal formatting |
| pyserial-asyncio-fast | Async serial communication |
| pytest | Testing framework |
| pytest-asyncio | Async test support |

## Features

### KPA500 Amplifier Control
- Power on/off (supports bootloader mode wake-up)
- Standby/Operate mode switching
- Real-time monitoring: Power (W), SWR, Temperature, Current, HV, Band
- Segmented bar graphs with color thresholds for Power and SWR
- Fault indicator

### KAT500 Antenna Tuner (Placeholder)
- UI framework in place for future implementation

## How to Run

```bash
# Activate virtual environment
source bin/activate

# Run without hardware (UI only)
python src/epcc.py

# Run with KPA500 connected
python src/epcc.py --port /dev/ttyUSB0

# Custom baud rate (default: 38400)
python src/epcc.py --port /dev/ttyUSB0 --baudrate 38400

# Custom poll interval in seconds (default: 0.25)
python src/epcc.py --port /dev/ttyUSB0 --poll-interval 0.5
```

Press `Ctrl-Q` to quit.

## Testing

### Unit Tests

Run the full test suite (no hardware required):

```bash
pytest tests/test_kpa500.py -v
```

### Live Hardware Tests

Run integration tests with actual KPA500 hardware:

```bash
# Basic run
pytest tests/kpa500_live_test.py --serial-port /dev/ttyUSB0

# Verbose output
pytest tests/kpa500_live_test.py --serial-port /dev/ttyUSB0 -v

# Custom baud rate
pytest tests/kpa500_live_test.py --serial-port /dev/ttyUSB0 --baudrate 38400
```

Live tests are skipped automatically if `--serial-port` is not provided.

## UI Layout

```
┌─────────────────────────────────────────────────────────────────┐
│              Elecraft KPA500 Amplifier                          │
├──────────────────┬──────────────────────────────────────────────┤
│  Power: 350W     │  [POWER]  ○ Standby  ○ Operate   [FAULT]    │
│  SWR: 1.3        │                                              │
│  Temp: 45°C      │  Power: ████████████░░░░░░░░░░░░░░ 350      │
│  Current: 12.5A  │                                              │
│  HV: 53.2V       │  SWR:   ██████░░░░░░░░░░░░░░░░░░░░ 1.3      │
│  Band: 20M       │                                              │
└──────────────────┴──────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│              Elecraft KAT500 Antenna Tuner                      │
├─────────────────────────────────────────────────────────────────┤
│  ○ Auto  ○ Manual  ○ Bypass    [Tune]    SWR: 1.0              │
│  ○ Antenna 1  ○ Antenna 2  ○ Antenna 3                          │
└─────────────────────────────────────────────────────────────────┘

                         Ctrl-Q to quit
```

- Status panel (left) shows yellow background when powered on, dark when off
- Power bar graph: green (0-500W), yellow (500-600W), red (600-700W)
- SWR bar graph: green (1.0-1.5), yellow (1.5-2.0), red (2.0-3.0)
  - Bar clamps at 3.0 but displays actual value if higher

## KPA500 Serial Protocol

The KPA500 module implements the Elecraft serial command protocol:

| Command | Description |
|---------|-------------|
| `^ON;` | Get/set power state |
| `^OS;` | Get/set operating mode (Standby/Operate) |
| `^BN;` | Get/set band |
| `^WS;` | Get power (W) and SWR |
| `^TM;` | Get temperature |
| `^VI;` | Get voltage and current |
| `^FL;` | Get/clear fault code |

When the KPA500 is in bootloader mode (powered off), send `P` to power on, then poll until responsive.
