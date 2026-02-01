# Elecraft Power Combo CLI (EPCC)

A Python Textual TUI application for combined control of Elecraft KPA500 amplifier and KAT500 antenna tuner via serial ports.

## Design Philosophy

The KPA500 and KAT500 are treated as a single "combo" unit:
- **Combined power control**: Power button turns both devices on/off together
- **Synchronized state**: If one device is powered on at startup, the other is automatically powered on
- **Smart polling**: KAT500 sleeps during receive to save power, wakes during transmit

## Project Structure

```
src/
├── epcc.py      # Main TUI application with custom widgets
├── epcc.tcss    # Textual CSS styling (theming)
├── kpa500.py    # KPA500 async serial interface module
├── kat500.py    # KAT500 async serial interface module
└── model.py     # Application model bridging TUI and hardware
tests/
├── conftest.py         # pytest configuration with CLI options
├── test_kpa500.py      # Unit tests for KPA500 module
├── test_kat500.py      # Unit tests for KAT500 module
├── kpa500_live_test.py # Live hardware integration tests
└── kat500_live_test.py # Live hardware integration tests
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
- Fault detection and clearing

### KAT500 Antenna Tuner Control
- Auto/Manual/Bypass mode switching
- Antenna selection (1/2/3)
- Full tune with automatic KPA500 standby
- Real-time monitoring: SWR, Bypass SWR, Forward/Reflected power
- Sleep mode management for power saving
- Fault detection and clearing

### Combined Features
- Unified power button controls both devices
- Segmented bar graphs with color thresholds for Power and SWR (KPA and KAT)
- Shared fault indicator with per-device fault text
- Tune button: puts KPA in standby, initiates KAT full tune

## KAT500 Sleep Strategy

To conserve power, the KAT500 uses sleep mode intelligently:
- Sleep mode is enabled on connection
- KAT500 is polled:
  1. Once on startup
  2. Every 30 seconds (configurable) as background refresh
  3. At the KPA poll rate, but **only when transmitting** (KPA SWR > 1.0)
- This allows the KAT500 to sleep during receive periods

## How to Run

```bash
# Activate virtual environment
source bin/activate

# Run with both devices
python src/epcc.py --kpa-port /dev/ttyUSB0 --kat-port /dev/ttyUSB1

# Run with KPA500 only
python src/epcc.py --kpa-port /dev/ttyUSB0

# Run with KAT500 only
python src/epcc.py --kat-port /dev/ttyUSB1

# Custom baud rate (default: 38400)
python src/epcc.py --kpa-port /dev/ttyUSB0 --kat-port /dev/ttyUSB1 --baudrate 38400

# Custom poll intervals
python src/epcc.py --kpa-port /dev/ttyUSB0 --kat-port /dev/ttyUSB1 \
    --kpa-poll-interval 0.25 \
    --kat-poll-interval 30
```

### Command Line Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--kpa-port` | `-k` | None | KPA500 serial port |
| `--kat-port` | `-t` | None | KAT500 serial port |
| `--baudrate` | `-b` | 38400 | Serial baud rate |
| `--kpa-poll-interval` | | 0.25 | KPA500 poll interval (seconds) |
| `--kat-poll-interval` | | 30.0 | KAT500 background poll interval (seconds) |

Press `Ctrl-Q` to quit.

## Testing

### Unit Tests

Run the full test suite (no hardware required):

```bash
pytest tests/ -v
```

### Live Hardware Tests

Run integration tests with actual hardware:

```bash
# KPA500 live tests
pytest tests/kpa500_live_test.py --serial-port /dev/ttyUSB0 -v

# KAT500 live tests
pytest tests/kat500_live_test.py --serial-port /dev/ttyUSB1 -v

# Custom baud rate
pytest tests/kpa500_live_test.py --serial-port /dev/ttyUSB0 --baudrate 38400
```

Live tests are skipped automatically if `--serial-port` is not provided.

## UI Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│               Elecraft Power Combo (KPA/KAT500)                     │
├────────────────────┬────────────────────────────────────────────────┤
│  Power: 350W       │  KPA Mode:                                     │
│  Temp: 45°C        │  ○ Standby  ● Operate                          │
│  Current: 12.5A    │  KAT Mode:                                     │
│  HV: 53.2V         │  ● Auto  ○ Manual  ○ Bypass                    │
│  Band: 20M         │  Antenna:                                      │
│  FWD: 1234         │  ● 1  ○ 2  ○ 3                                 │
│  RFL: 56           │                                                │
│  Bypass SWR: 1.05  │  Power   ████████████░░░░░░░░░░░░░░░░░░ 350    │
│                    │  KPA SWR ██████░░░░░░░░░░░░░░░░░░░░░░░░ 1.3    │
│                    │  KAT SWR ████░░░░░░░░░░░░░░░░░░░░░░░░░░ 1.1    │
│                    │                                                │
│                    │  [ POWER ]  [ TUNE ]                           │
├────────────────────┴────────────────────────────────────────────────┤
│  [ FAULT ]  KPA Fault: None                                         │
│             KAT Fault: None                                         │
└─────────────────────────────────────────────────────────────────────┘
                            Ctrl-Q to quit
```

- **Readings panel** (left): Yellow background when powered on, dark when off
- **Power bar graph**: Green (0-500W), yellow (500-600W), red (600-700W)
- **SWR bar graphs**: Green (1.0-1.5), yellow (1.5-2.0), red (2.0-3.0)
  - Bar clamps at 3.0 but displays actual value if higher
- **Radio buttons**: Dark green when inactive, bright green when active
- **Power button**: Dark green when off, bright green when on
- **Tune button**: White on black normally, inverts while tuning
- **Fault button**: Dark red normally, bright red when fault active (click to clear)

## Serial Protocols

### KPA500 Commands

Commands use `^` prefix (e.g., `^ON;`):

| Command | Description |
|---------|-------------|
| `^ON;` | Get/set power state |
| `^OS;` | Get/set operating mode (Standby/Operate) |
| `^BN;` | Get/set band |
| `^WS;` | Get power (W) and SWR |
| `^TM;` | Get temperature |
| `^VI;` | Get voltage and current |
| `^FL;` | Get/clear fault code |

When KPA500 is in bootloader mode (powered off), send `P` to power on, then poll until responsive.

### KAT500 Commands

Commands have no prefix (e.g., `PS;`):

| Command | Description |
|---------|-------------|
| `PS;` | Get/set power state |
| `MD;` | Get/set mode (Auto/Manual/Bypass) |
| `AN;` | Get/set antenna |
| `FT;` | Initiate full tune |
| `TP;` | Get tuning in progress status |
| `VSWR;` | Get VSWR |
| `VSWRB;` | Get bypass VSWR |
| `VFWD;` | Get forward voltage |
| `VRFL;` | Get reflected voltage |
| `FLT;` | Get fault code |
| `FLTC;` | Clear fault |
| `SL;` | Get/set sleep mode enabled |

Send `;` (semicolons) to wake KAT500 from sleep mode.
