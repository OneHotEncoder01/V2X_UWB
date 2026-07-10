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

Both sketches require the [Decawave DW3000 Arduino library](https://github.com/Makerfabs/Makerfabs-ESP32-UWB-DW3000).

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

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DJANGO_SECRET_KEY` | `local-cam-dashboard-dev-key` | Django secret key (override for non-local use) |
