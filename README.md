# V2X UWB — CAM over Ultra-Wideband

Proof-of-concept V2X (Vehicle-to-Everything) system that encodes ETSI ITS CAM messages
and transmits them over a DW3000-based UWB radio link between two ESP32 boards.

## Architecture

```
[Raspberry Pi — TX side]          [PC/Laptop — RX side]
  GPS HAT ──► MainTx.py            MainRx.py
              GenerateCAM.py         ├─ receive_cam (Django management command)
              GenerateGPS.py         └─ Django dashboard  http://127.0.0.1:8000/
              activateGPS.py
                  │ hex over serial        │ hex over serial
              ESP32 TX (ex_01a)  ──UWB──►  ESP32 RX (ex_02a)
```

- **`MainTx.py`** — Raspberry Pi only. Reads GPS, encodes CAM payloads (ASN.1 UPER),
  and sends them to the TX ESP32 as newline-terminated hex strings.
- **`MainRx.py`** — Windows and Linux. Reads decoded UWB frames from the RX ESP32,
  stores them in SQLite, and starts the Django dashboard.
- **`GenerateCAM.py`** — Builds and ASN.1-encodes a ETSI EN 302 637-2 CoopAwareness PDU.
- **`GenerateGPS.py`** — Reads NMEA from the GPS HAT serial port, converts to ITS coordinates.
- **`activateGPS.py`** — Sends `AT+CGPS=1` to a SIM7600-series 4G/GPS HAT to enable the
  GPS receiver. Adapt or replace for other GPS modules.

## Hardware

This is what the system was built and measured on. Any Linux SBC and any
ESP32+DW3000 board pair should work, but the serial port numbering and the GPS
HAT AT commands are specific to the parts below.

| Qty | Part | Role |
|---:|---|---|
| 1 | Raspberry Pi (any model with USB) | Runs `MainTx.py` |
| 1 | Waveshare SIM7600-series 4G/GPS HAT | GPS source for the TX side |
| 2 | ESP32 + DW3000 UWB board (e.g. Makerfabs ESP32 UWB DW3000) | The UWB radio link — one TX, one RX |
| 1 | Laptop / PC (Windows or Linux) | Runs `MainRx.py` and the dashboard |

The GPS HAT is only needed for live position data. `GenerateGPS.MockGPS()`
supplies fixed coordinates instead, and the test transmitters accept
`--mock-gps`, so **you can bring up and measure the CAM-over-UWB link with just
the two ESP32 boards** before any GPS hardware arrives:

```bash
python over_air_loss_tx.py --mock-gps --test-id 1 --rates 10 --packets-per-rate 300
```

`MainTx.py` itself has no mock path — it activates the HAT and waits for a real
fix, so run it only once the GPS hardware is attached.

See [TECHNICAL.md](TECHNICAL.md) for default serial port assignments and the
DW3000 radio configuration (channel 5, 6.8 Mbit/s).

## Prerequisites

### ASN.1 schema files

The encoder/decoder needs two ETSI ASN.1 files placed in the project root.
Download them free of charge from the ETSI Forge GitLab:

| File | Source |
|---|---|
| `ETSI-ITS-CDD.asn` | ETSI TS 102 894-2 (ITS Common Data Dictionary) |
| `CAM-PDU-Descriptions.asn` | ETSI EN 302 637-2 (CAM standard) |

> These files are excluded from the repository (`.gitignore`) because they are
> published under an ETSI copyright notice.

### Python dependencies

```bash
python -m pip install -r requirements.txt
```

A virtual environment is recommended:

```bash
python -m venv venv
# Linux / macOS
source venv/bin/activate
# Windows
.\venv\Scripts\activate

pip install -r requirements.txt
```

### ESP32 firmware

Flash `ex_01a_simple_tx` to the TX board and `ex_02a_simple_rx` to the RX board
using Arduino IDE or `arduino-cli`:

```bash
arduino-cli compile --fqbn esp32:esp32:esp32 ex_01a_simple_tx
arduino-cli compile --fqbn esp32:esp32:esp32 ex_02a_simple_rx
```

All sketches require the [Decawave DW3000 Arduino library](https://github.com/Makerfabs/Makerfabs-ESP32-UWB-DW3000).

There are three sketches — flash the right one:

| Sketch | Board | When |
|---|---|---|
| `ex_01a_simple_tx` | TX | Normal operation |
| `ex_01a_simple_tx_telemetry` | TX | Stress testing — same TX behaviour plus per-packet timing telemetry back over serial |
| `ex_02a_simple_rx` | RX | Always |

## Transmitter (Raspberry Pi — Linux only)

```bash
python MainTx.py
```

Serial ports used by default (edit `MainTx.py` / `GenerateGPS.py` if yours differ):

| Port | Purpose |
|---|---|
| `/dev/ttyUSB2` | SIM7600 GPS HAT — AT command port |
| `/dev/ttyUSB1` | SIM7600 GPS HAT — NMEA port |
| `/dev/ttyUSB4` | TX ESP32 board |

### Run as a systemd service (auto-start on boot)

An install script handles paths automatically. From the project directory on the Pi:

```bash
bash install_service.sh
```

This writes the service file with the correct paths, enables it, and starts it immediately.
From that point the transmitter starts automatically whenever the Pi boots, as soon as
all three USB serial devices appear.

Useful commands after installation:

```bash
journalctl -u cam_transmitter -f          # follow live logs
sudo systemctl status cam_transmitter     # service status
sudo systemctl restart cam_transmitter    # restart manually
sudo systemctl disable cam_transmitter    # disable auto-start
```

If you need to override the user or Python path:

```bash
SERVICE_USER=myuser PYTHON=/usr/bin/python3 bash install_service.sh
```

## Receiver Dashboard (Windows and Linux)

**Linux:**

```bash
python MainRx.py --port /dev/ttyUSB0
```

**Windows** (use the COM port shown in Device Manager):

```powershell
python MainRx.py --port COM3
```

The script auto-detects the default port (`/dev/ttyUSB0` on Linux, `COM3` on Windows).

### Options

| Flag | Default | Description |
|---|---|---|
| `--port` | `/dev/ttyUSB0` / `COM3` | RX ESP32 serial port |
| `--baud` | `115200` | Baud rate |
| `--encoding` | `auto` | Frame encoding: `auto`, `hex`, or `binary` |
| `--host` | `127.0.0.1` | Dashboard bind address |
| `--web-port` | `8000` | Dashboard HTTP port |
| `--raw` | off | Print every raw serial line |
| `--no-receiver` | off | Start dashboard only (no serial reading) |

Open the dashboard at **http://127.0.0.1:8000/**.

The dashboard stores received CAM messages in `cam_messages.sqlite3` and updates
every second. Map tiles are fetched from CartoCDN on demand and cached locally in
`static/tile_cache/` so subsequent loads are offline.

## Measurements and Experiments

### Recorded data

`measurements/2026-07-14_indoor_range/` contains a full set of sequenced indoor
packet-delivery tests (2.5–8 m, LOS/NLOS, body and glass obstruction) with a
[README](measurements/2026-07-14_indoor_range/README.md) documenting the
conditions and per-test loss rates. Useful as a baseline to compare your own
runs against.

The short version: the link is lossless at 2.5 m in every orientation tested,
and near 8 m it becomes unstable enough that small changes around the antennas
dominate the result. Do not read a single "UWB range" number out of this data.

### Test tooling

| Script | Purpose |
|---|---|
| `stress_test_tx.py` | TX-rate sweep to find the transmitter's saturation point — see [STRESSTEST_QUICKSTART.md](STRESSTEST_QUICKSTART.md) |
| `plot_stress_results.py` | Plots the stress-test CSV |
| `over_air_loss_tx.py` / `over_air_loss_rx.py` | Sequenced over-the-air packet-loss measurement — see [OVER_AIR_LOSS_TEST.md](OVER_AIR_LOSS_TEST.md) |
| `run_over_air_loss_test.py` | Orchestrates a full over-air run over SSH (needs an SSH alias `pi` for the transmitter) |
| `field_distance_tx.py` | Autonomous TX for outdoor range tests, when SSH to the Pi is not available |
| `analyze_over_air_loss.py` / `analyze_field_distance_loss.py` | Turn TX+RX CSV pairs into PDR summaries |
| `rx_range_indicator.py` | Large live RECEIVING / NO SIGNAL display — makes walking a range test alone practical |
| `serial_ports.py` | Serial port helpers and platform defaults |

### Figures

```bash
venv/bin/python figures/generate_indoor_range_figures.py  # from measurements/ — works out of the box
venv/bin/python figures/generate_figures.py               # from cam_messages.sqlite3 — needs your own run
```

Both write `.pdf` (vector) and `.png` (preview) into `figures/`. The generated
files are gitignored — rerun the scripts to recreate them. To also copy figures
into another directory, set `V2X_FIGURE_OUT_DIRS=/path/to/figures`.

`generate_figures.py` reads the dashboard's SQLite database, which is runtime
state and is **not** in the repository. Record your own messages with
`MainRx.py` first; the script needs a populated `cam_messages.sqlite3` in the
project root. `generate_indoor_range_figures.py` needs nothing extra — it reads
the committed CSVs under `measurements/`.

> Note: `generate_figures.py` and the indoor figure labels are in German.

## Documentation

| File | Purpose |
|---|---|
| [TECHNICAL.md](TECHNICAL.md) | Engineering reference: architecture, pipelines, frame format, data model, REST API, and a debugging history of two real throughput bugs |
| [STRESSTEST_QUICKSTART.md](STRESSTEST_QUICKSTART.md) | Transmitter-side stress-test procedure |
| [OVER_AIR_LOSS_TEST.md](OVER_AIR_LOSS_TEST.md) | Over-the-air packet-loss and distance-test workflow |

If you are picking this project up from scratch, read TECHNICAL.md — the
"Stresstest: Known Issues and Fixes" section in particular will save you time.
The transmitter's real ceiling is ~45 Hz and it is serial-bound, not radio-bound.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DJANGO_SECRET_KEY` | `local-cam-dashboard-dev-key` | Django secret key (override for non-local use) |
| `V2X_FIGURE_OUT_DIRS` | *(unset)* | Extra output directories for generated figures, `os.pathsep`-separated |

The dashboard ships with `DEBUG = True` and `ALLOWED_HOSTS = ["*"]`. That is
fine for a lab tool on `127.0.0.1`; set a real `DJANGO_SECRET_KEY` and turn
`DEBUG` off before exposing it on any network you do not control.

## License

MIT — see [LICENSE](LICENSE). Note that the bundled Leaflet build, the ETSI
ASN.1 schemas, the DW3000 Arduino library and the CARTO map tiles each carry
their own terms; these are listed at the bottom of the LICENSE file.
