# UWB CAM Communication Test Setup

## Roles

- `MainTx.py` runs on the Raspberry Pi transmitter side. It reads GPS, generates CAM payloads, and sends them to the TX ESP32 as newline-terminated hex.
- `MainRx.py` runs on the receiver computer. It reads decoded UWB serial frames, stores them in SQLite, and starts the Django dashboard.
- `DecodeCAM.py` is a simple terminal decoder for debugging only.

## Setup

Install Python dependencies:

```bash
./venv/bin/python -m pip install -r requirements.txt
```

Flash the ESP32 sketches:

```bash
arduino-cli compile --fqbn esp32:esp32:esp32 ex_01a_simple_tx
arduino-cli compile --fqbn esp32:esp32:esp32 ex_02a_simple_rx
```

Use `ex_01a_simple_tx` on the TX board and `ex_02a_simple_rx` on the RX board.

## Transmitter

On the Raspberry Pi:

```bash
python3 MainTx.py
```

The TX log should show board responses like:

```text
[TX Board] b'TX 35\r\n'
```

## Receiver Dashboard

On the receiver computer:

```bash
./venv/bin/python MainRx.py --port /dev/ttyUSB0 --raw
```

Open:

```text
http://127.0.0.1:8000/
```

The dashboard stores received CAM messages in `cam_messages.sqlite3` and updates once per second. The map is local/offline, so it does not request external map tiles.

To run only the dashboard without reading serial:

```bash
./venv/bin/python MainRx.py --no-receiver
```
