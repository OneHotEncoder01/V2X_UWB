# Technical Reference

## Table of Contents

1. [Project Structure](#project-structure)
2. [Hardware](#hardware)
3. [Standards](#standards)
4. [TX Pipeline (Raspberry Pi)](#tx-pipeline-raspberry-pi)
5. [UWB Radio Link](#uwb-radio-link)
6. [RX Pipeline (Laptop / PC)](#rx-pipeline-laptop--pc)
7. [Django Dashboard](#django-dashboard)
8. [Data Model](#data-model)
9. [REST API](#rest-api)
10. [Serial Frame Format](#serial-frame-format)
11. [CAM Encoding Details](#cam-encoding-details)
12. [Service and Process Management](#service-and-process-management)
13. [Stresstest: Known Issues and Fixes](#stresstest-known-issues-and-fixes)
14. [Dependencies](#dependencies)

---

## Project Structure

```
V2X_UWB/
│
├── MainTx.py               # TX entry point — orchestrates GPS + CAM + serial TX
├── MainRx.py               # RX entry point — runs Django migrate, receiver, web server
├── GenerateCAM.py          # ASN.1 CAM encoder
├── GenerateGPS.py          # GPS serial reader and NMEA-to-ITS converter
├── activateGPS.py          # Sends AT+CGPS=1 to enable the GPS HAT
│
├── ex_01a_simple_tx/
│   └── ex_01a_simple_tx.ino   # ESP32 firmware — reads hex from serial, transmits via UWB
├── ex_02a_simple_rx/
│   └── ex_02a_simple_rx.ino   # ESP32 firmware — receives UWB frame, prints hex to serial
│
├── cam_dashboard/          # Django project package
│   ├── settings.py         # DB, installed apps, static files config
│   ├── urls.py             # URL routing
│   └── wsgi.py
│
├── messages/               # Django app — storage and decoding
│   ├── models.py           # CamMessage database model
│   ├── views.py            # HTML views + JSON API + map tile proxy
│   ├── serial_decode.py    # ASN.1 decoder, frame parsing, CAM flattener
│   ├── management/
│   │   └── commands/
│   │       └── receive_cam.py  # Django management command — reads serial, stores to DB
│   └── migrations/         # Django schema migrations
│
├── templates/
│   └── messages/
│       ├── dashboard.html      # Overview page — all stations, live map
│       └── station_detail.html # Per-station page — history table + path on map
│
├── static/
│   └── vendor/leaflet/     # Bundled Leaflet.js (no CDN required)
│
├── cam_transmitter.service # systemd service unit for the TX side
├── install_service.sh      # One-command service installer for the Pi
├── requirements.txt        # Python dependencies
└── manage.py               # Django management entry point
```

---

## Hardware

### Transmitter (Raspberry Pi)

| Component | Role | Default port |
|---|---|---|
| Raspberry Pi (any model with USB) | Runs `MainTx.py` | — |
| Waveshare SIM7600-series 4G/GPS HAT | Provides GPS NMEA sentences | `/dev/ttyUSB1` (NMEA) |
| SIM7600 AT command port | Enable GPS receiver on boot | `/dev/ttyUSB2` |
| ESP32 + DW3000 UWB board | Transmits CAM payload over UWB | `/dev/ttyUSB4` |

### Receiver (Laptop / PC — Windows or Linux)

| Component | Role | Default port |
|---|---|---|
| ESP32 + DW3000 UWB board | Receives UWB frames, outputs hex to serial | `/dev/ttyUSB0` (Linux) / `COM3` (Windows) |
| PC / Laptop | Runs `MainRx.py` and the Django dashboard | — |

---

## Standards

### ETSI EN 302 637-2 — Cooperative Awareness Message (CAM)

A CAM is a V2X broadcast message that a vehicle sends periodically (typically 1–10 Hz)
to announce its presence and kinematic state to nearby road users.

The message is encoded using **ASN.1 Unaligned Packed Encoding Rules (UPER)**, which
produces very compact binary output — a full CAM typically fits in ~30 bytes.

The schema is split across two ASN.1 files:

| File | Standard | Contents |
|---|---|---|
| `ETSI-ITS-CDD.asn` | ETSI TS 102 894-2 | Common Data Dictionary — shared ITS types (coordinates, speed, heading, …) |
| `CAM-PDU-Descriptions.asn` | ETSI EN 302 637-2 | CAM PDU structure (`CoopAwareness`, `CamParameters`, containers) |

### ITS Timestamp

ITS time is measured in **milliseconds since 2004-01-01 00:00:00 UTC** (not Unix epoch).
The CAM field `generationDeltaTime` is this value modulo 65536 (fits in 16 bits, wraps
roughly every 65 seconds). This is enough for receivers to order messages and detect gaps.

### ITS Coordinate Encoding

| Field | Unit | Unavailable sentinel |
|---|---|---|
| Latitude | 10⁻⁷ degrees (integer) | `900 000 001` |
| Longitude | 10⁻⁷ degrees (integer) | `1 800 000 001` |
| Altitude | centimetres (integer) | `800 001` |
| Speed | 0.01 m/s (integer) | `16 383` |
| Heading | 0.1 degrees (integer) | `3 601` |

---

## TX Pipeline (Raspberry Pi)

`MainTx.py` uses Python `multiprocessing` to run three worker processes in parallel,
communicating through single-slot `Queue` objects (dropping stale data):

```
[GPS Worker]  stream_gps() → gps_queue (maxsize=1)
                                   │
                            [CAM Worker]  GenerateCamMessage() → msg_queue (maxsize=1)
                                                                        │
                                                               [TX Worker]  serial.write()
```

### GPS Worker — `GenerateGPS.stream_gps()`

- Keeps `/dev/ttyUSB1` open continuously with a 1-second read timeout
- Parses incoming NMEA sentences using `pynmea2`
- Waits for both a **GGA** sentence (altitude + HDOP) and an **RMC** sentence (position + speed + heading, status `A` = active fix)
- Combines them into an ITS-encoded fix dict and yields it
- On serial error, waits 5 seconds and reconnects automatically
- Logs every raw NMEA sentence until the first valid fix (useful for debugging GPS module startup)

### CAM Worker — `GenerateCAM.GenerateCamMessage()`

- Pops a GPS fix from `gps_queue`
- Calls `asn1tools.compile_files()` (result is `lru_cache`d — only compiled once)
- Builds the full `CoopAwareness` payload dict and encodes it with UPER
- Derives `driveDirection` from speed: `forward` if speed > 0, `unavailable` otherwise
- Pushes the encoded bytes to `msg_queue`

### TX Worker — `MainTx.sendCAM()`

- Opens `/dev/ttyUSB4` at 115200 baud
- Pops encoded bytes from `msg_queue`
- Sends them as a **hex ASCII string followed by `\n`**
  e.g. `00 14 3c a0 … \n` → `"00143ca0…\n"`
- Reads any response from the ESP32 (e.g. `TX 34`) and logs it

---

## UWB Radio Link

### ESP32 TX firmware (`ex_01a_simple_tx.ino`)

- Waits for a newline-terminated hex string on the USB serial port
- Decodes hex to raw bytes
- Writes the bytes into the DW3000 TX buffer (`dwt_writetxdata`)
- Triggers an immediate transmission (`DWT_START_TX_IMMEDIATE`)
- Polls `SYS_STATUS_TXFRS` until the frame is sent, then confirms with `TX <len>` on serial

### ESP32 RX firmware (`ex_02a_simple_rx.ino`)

- Calls `dwt_rxenable(DWT_START_RX_IMMEDIATE)` to arm the receiver
- Polls `SYS_STATUS_RXFCG` (good frame) or `SYS_STATUS_ALL_RX_ERR` (error)
- On a good frame: reads the payload with `dwt_readrxdata`, prints each byte as
  two uppercase hex characters, terminates with `\n`
- On error: prints `RX ERROR: 0x<status>` and clears the error flags

### DW3000 radio configuration

Both boards use identical RF config (mismatched config = no link):

| Parameter | Value |
|---|---|
| Channel | 5 (6.5 GHz band) |
| Data rate | 6.8 Mbps |
| Preamble length | 128 symbols |
| PAC size | 8 |
| Preamble code | 9 |
| SFD | Non-standard 8-symbol |
| PHY header mode | Standard |
| STS | Off |
| PDOA | Off |
| Max payload | 100 bytes (TX) / 127 bytes (RX) |

---

## RX Pipeline (Laptop / PC)

`MainRx.py` is the entry point on the receiver side. It:

1. Calls `python manage.py migrate --noinput` as a subprocess to ensure the DB schema is up to date
2. Checks that the chosen web port is free (fails fast with a clear message if not)
3. Spawns `python manage.py receive_cam` as a background subprocess (the serial reader)
4. Spawns `python manage.py runserver --noreload` as a background subprocess (the web server)
5. Monitors both processes and exits if either dies, propagating the exit code
6. Handles `SIGINT` (Ctrl-C) and `SIGTERM` (Linux only) to terminate both subprocesses cleanly

### `receive_cam` management command

- Opens the RX ESP32 serial port with a 1-second timeout
- Reads lines and passes them to `serial_decode.decode_serial_line()`
- Stores decoded messages as `CamMessage` rows in SQLite

### `serial_decode.py` — frame decoding

The decoder handles three possible encodings from the RX board:

| Mode | Detection | Processing |
|---|---|---|
| `hex` | All bytes are valid hex ASCII and even length | `bytes.fromhex(line)` |
| `hex-ascii` | Hex-decoded result is itself valid hex | Double-decode |
| `binary` | Not valid hex | Treat bytes as raw payload |

In `auto` mode (default) it tries all applicable candidates and returns the first
that decodes successfully as a valid CAM. This makes the receiver tolerant of
different ESP32 firmware output formats.

The `decode_cam_payload()` function tries decoding as `CoopAwareness` first (payload
only, no ITS-PDU header), then falls back to the full `CAM` wrapper if that fails and
extracts `stationId` from the header.

---

## Django Dashboard

The dashboard is a minimal Django 6 project with no authentication (local use only).
It has no JavaScript framework — all interactivity is vanilla JS with `fetch` polling.

### Pages

| URL | View | Description |
|---|---|---|
| `/` | `dashboard` | Overview — station cards + live map of all stations |
| `/station/<key>/` | `station_detail` | Single station — metrics + message history + path |

### Polling

Both pages poll their respective JSON API endpoints every **2 seconds** using `setInterval`.
No WebSockets or server-sent events are used — the round-trip latency of 2 s is
sufficient for V2X situational awareness demonstration.

### Map

Leaflet.js is bundled locally under `static/vendor/leaflet/` — no CDN call needed.
Map tiles are served through a Django **tile proxy** at `/tiles/{z}/{x}/{y}.png` which:

1. Checks a local cache at `static/tile_cache/{z}/{x}/{y}.png`
2. If missing, fetches from CartoCDN (`a.basemaps.cartocdn.com/light_all/`)
3. Writes the PNG to the cache for future requests
4. Falls back to an inline SVG grid placeholder if the fetch fails

This means the first zoom level loads tiles from the internet, but subsequent loads
and any zoom level already visited work fully offline.

---

## Data Model

A single table `messages_cammessage` stores every received CAM:

| Column | Type | Notes |
|---|---|---|
| `id` | `BIGINT` PK | Auto-increment |
| `received_at` | `DATETIME` | Set on insert, indexed |
| `station_id` | `BIGINT` nullable | From ITS-PDU header; `NULL` when payload-only |
| `generation_delta_time` | `INTEGER` | CAM timestamp mod 65536 |
| `station_type` | `INTEGER` nullable | ETSI station type code (5 = passenger car, etc.) |
| `latitude` | `FLOAT` nullable | Decimal degrees; `NULL` = unavailable |
| `longitude` | `FLOAT` nullable | Decimal degrees; `NULL` = unavailable |
| `altitude_m` | `FLOAT` nullable | Metres |
| `speed_mps` | `FLOAT` nullable | m/s |
| `heading_deg` | `FLOAT` nullable | Degrees (0–360) |
| `drive_direction` | `VARCHAR(32)` | `forward`, `backward`, or `unavailable` |
| `raw_hex` | `TEXT` | Original hex string as received |
| `decoded` | `JSON` | Full decoded CAM dict from asn1tools |

The database is SQLite (`cam_messages.sqlite3`), stored in the project root.

---

## REST API

All endpoints return JSON. No authentication.

### `GET /api/stations/`

Returns the latest message for each unique `station_id`, plus a message count.

```json
{
  "stations": [
    {
      "station_key": "42",
      "station_id": 42,
      "station_type": 5,
      "station_type_label": "Passenger Car",
      "message_count": 137,
      "latest": { ...message dict... }
    }
  ]
}
```

### `GET /api/messages/?station=<key>&limit=<n>`

Returns up to `limit` (max 500, default 100) messages, newest first.
Filter by `station=<station_key>` or `station=unknown` for messages with no station ID.

### `GET /api/latest/`

Returns only the single most recent message across all stations.

### Message dict fields

```json
{
  "id": 42,
  "received_at": "2026-06-28T14:23:01.123456+00:00",
  "station_id": 1,
  "station_key": "1",
  "station_type": 5,
  "station_type_label": "Passenger Car",
  "generation_delta_time": 12345,
  "latitude": 48.835012,
  "longitude": 10.103567,
  "altitude_m": 482.5,
  "speed_mps": 8.33,
  "speed_kmh": 29.99,
  "heading_deg": 270.5,
  "drive_direction": "forward",
  "raw_hex": "00143ca0..."
}
```

---

## Serial Frame Format

```
TX side (Pi → ESP32):    <hex_string>\n
                          e.g.  00143ca0ff…\n   (one byte = two hex chars)

RX side (ESP32 → PC):    <HEX_STRING>\n
                          e.g.  00143CA0FF…\n   (uppercase, same structure)
```

The TX ESP32 validates the hex string (rejects odd length, non-hex chars, payload > 100 bytes)
and responds with `TX <n>` on success or `ERR: <reason>` on failure.

The RX ESP32 strips the 2-byte FCS that the DW3000 appends before printing, so the
received hex is identical to what was transmitted.

---

## CAM Encoding Details

`GenerateCAM.GenerateCamMessage()` constructs a `CoopAwareness` PDU (no ITS-PDU wrapper).
Fixed/unavailable values are used for fields that require additional sensors not present
in this prototype:

| Field | Value used | Reason |
|---|---|---|
| `vehicleLengthValue` | `1023` | Unavailable |
| `vehicleWidth` | `62` | Unavailable |
| `longitudinalAccelerationValue` | `161` | Unavailable |
| `curvatureValue` | `1023` | Unavailable |
| `yawRateValue` | `32767` | Unavailable |
| `headingConfidence` | `127` | Unavailable |
| `speedConfidence` | `127` | Unavailable |

Live fields populated from GPS: `latitude`, `longitude`, `altitude`, `speed`, `heading`,
`positionConfidenceEllipse` (derived from HDOP), `driveDirection`, `generationDeltaTime`.

---

## Service and Process Management

### TX side — systemd

`cam_transmitter.service` configures the TX as a systemd service:

- Declares `Wants=` on the three USB device units so systemd starts the service only
  after the GPS HAT and TX ESP32 appear on the bus
- `Restart=on-failure` with `RestartSec=10` — automatic recovery from crashes
- `KillSignal=SIGINT` — triggers Python's `KeyboardInterrupt` handler so worker
  processes are terminated cleanly before SIGKILL
- `TimeoutStopSec=15` — hard kill after 15 seconds if cleanup stalls
- `User=pi`, `Group=dialout` — least-privilege, serial port access via group membership

### RX side — process supervision in `MainRx.py`

Two subprocesses (`receive_cam` + `runserver`) are supervised in a tight polling loop.
If either exits for any reason the other is terminated and `MainRx.py` exits with the
failed process's return code, making it straightforward to wrap in a process supervisor
or run from a terminal and catch failures.

---

## Stresstest: Known Issues and Fixes

`stress_test_tx.py` decouples CAM transmission rate from GPS update rate (it caches one
GPS fix and re-encodes it with fresh timestamps) to sweep target rates and find where
the system saturates. A run on 2026-07-10 initially showed **achieved throughput flat
at ~0.41 Hz for every requested rate from 1–50 Hz**, 100% success — i.e. the system
never scaled with the requested rate at all. Two independent, compounding bugs on the
*deployed* Raspberry Pi were responsible; neither was a UWB radio or hardware limit.
`plot_stress_results.py`'s auto-summary only flags saturation as a success-rate drop
below 100%, so it reported "No saturation observed" on this data — misleading, since a
flat achieved-vs-target curve is itself the saturation signal. Read the raw
`achieved_hz` vs `target_hz` columns directly rather than trusting that summary line.

### Bug 1 — stale deployed `GenerateCAM.py` (no ASN.1 schema caching)

The Pi's deployed copy of `GenerateCAM.py` predated the `lru_cache`-wrapped
`_compile_standards()` helper described in [CAM Worker](#cam-worker--generatecamgeneratecammessage)
above — it called `asn1tools.compile_files()` fresh inside `GenerateCamMessage()` on
**every** call. Direct profiling on the Pi isolated the cost: `compile_files()` alone
takes ~2.5s regardless of how many times it's called; `.encode()` on an
already-compiled spec takes 0.1–0.3ms. This ~2.5s-per-message cost is exactly what
capped the stresstest at 0.41 Hz, and it matched the *live production* service's own
journal — `cam_transmitter.service` was independently observed generating one CAM
roughly every 2–3s, confirming this wasn't a stresstest artifact: production itself
was silently running at ~0.4 Hz for as long as the stale file was deployed.

This repo's tracked `GenerateCAM.py` already had the caching fix from an earlier
refactor — it had simply never been redeployed to the Pi (the Pi's copy at
`/home/sinan/CAM_Broadcaster` has generally diverged from this repo; see
[Service and Process Management](#service-and-process-management)).

**Fix:** back up the stale deployed file, redeploy the repo's already-correct
`GenerateCAM.py`. No source change was needed in this repository.

### Bug 2 — intermittent `multiprocessing` fork race stalls the CAM worker after message 1

After fixing Bug 1 and restarting `cam_transmitter.service`, the CAM-generator worker
produced **exactly one** message and then stalled forever — the GPS worker kept
running and logging fixes normally, but no further `[CAM] Generated…` lines ever
appeared. `is_alive()` didn't catch it: the process was still alive, just blocked
forever inside a queue `.get()`/lock, not crashed.

Root-caused by writing an instrumented reproduction of the exact
`GetGps` / `getCAM` / `sendCAM` three-process pipeline (including real serial I/O to
the ESP32) and running it under `systemd-run` with progressively fewer sandboxing
flags. The first hypothesis — that `PrivateTmp=yes` was responsible — turned out to
be **wrong**: disabling it appeared to fix things in two short (~30s) verification
windows, but the exact same hang later recurred with `PrivateTmp=no` confirmed
active, and even under a bare `systemd-run` unit with *no* hardening directives at
all (no `PrivateTmp`, no `NoNewPrivileges`, nothing). Across repeated trials of that
bare unit the pipeline hung after message 1 about 2 times in 3, and ran perfectly
for a full 25s straight the other time — i.e. it is a genuinely **intermittent,
timing-dependent race**, not something toggled by a specific systemd directive.
This is consistent with Python's well-known fork-safety hazard: `multiprocessing`'s
`Queue`/`Lock` machinery can be forked mid-operation and leave a child holding a
lock state with no thread able to release it. It did not reproduce when the same
code was run interactively (plain script, or `cam_transmitter_wrapper.sh` invoked
directly from a shell) in dozens of trials — only under `systemd`-managed process
start, which apparently perturbs fork/scheduling timing enough to hit the window
noticeably more often. It never manifested before Bug 1 was fixed, because the
~2.5s-per-message pace left so much idle time between queue operations that the
race window was rarely (if ever) hit.

**Fix:** since the race can't be reliably eliminated by toggling systemd flags, made
the service self-healing instead. `MainTx.py`'s `getCAM`/`sendCAM` workers now take
an optional `multiprocessing.Value('d', ...)` heartbeat and stamp it with `time.time()`
after every successful queue `put()`. The main process's existing watchdog loop
(previously only checked `is_alive()`) now also treats a heartbeat that has gone
stale for more than `STALL_TIMEOUT_S = 15` seconds as a failure, logs it, and exits
non-zero — which `cam_transmitter.service`'s existing `Restart=on-failure` /
`RestartSec=5` picks up automatically. A `NO_PROGRESS_TIMEOUT_S = 90` fallback also
catches the (unobserved but possible) case where a worker never produces a single
message at all, since the heartbeat would otherwise stay at its `0.0` sentinel
forever. Applied to both this repo's `MainTx.py` and the Pi's deployed copy
(diverged in port-resolution code only — see [Service and Process Management](#service-and-process-management)
— the same heartbeat/watchdog change was ported to each). `PrivateTmp=no` was left
in place on the deployed unit (harmless either way) but is **not** the actual fix.

Empirically, 9 consecutive `systemctl restart` cycles after deploying the watchdog
all ran cleanly with no stall — inconclusive on whether the heartbeat `Value()`
objects themselves shift fork timing enough to reduce the race's frequency, but the
watchdog is defense-in-depth regardless: if the race recurs, recovery is automatic
within ~15–20s instead of a silent, permanent stall.

### Diagnosing a repeat of either bug

- **Flat achieved-Hz regardless of target, no crash:** suspect Bug 1's signature
  (stale/uncached `GenerateCAM.py`). Profile `GenerateCAM.GenerateCamMessage()` directly
  on the Pi — if repeated calls in a loop don't drop to sub-millisecond after the first,
  the deployed file is missing the caching.
- **Exactly one CAM message, then silence, GPS worker still ticking:** Bug 2's
  signature. Check `journalctl -u cam_transmitter` for `"stalled"` — if the watchdog
  is doing its job you'll see it detect and restart within ~15–20s on its own. If it
  doesn't recover, confirm `MainTx.py` on the Pi actually has the heartbeat/watchdog
  code (`grep -n heartbeat MainTx.py`) — a redeploy of an older file would silently
  drop the fix, same pattern as Bug 1.

### Post-fix validation

Final rate sweep after both fixes, `stress_test_tx.py --rates 1,10,20,30,40,45,50,55,60,70,80,100 --duration 120`
(120s per rate, ~24 min total, full run — not the shorter early validation pass):

| Target Hz | Achieved Hz | Success | Avg latency | Min–max latency |
|---|---|---|---|---|
| 1 | 1.0 | 100% (120/120) | 18.3 ms | 13.6–22.6 ms |
| 10 | 10.0 | 100% (1200/1200) | 17.6 ms | 12.9–22.3 ms |
| 20 | 20.0 | 100% (2400/2400) | 16.9 ms | 12.1–22.6 ms |
| 30 | 30.0 | 100% (3600/3600) | 17.7 ms | 12.3–23.4 ms |
| 40 | 40.0 | 100% (4800/4800) | 17.5 ms | 12.2–23.3 ms |
| 45 | 45.0 | 100% (5400/5400) | 17.7 ms | 12.3–23.2 ms |
| **50** | **45.5** | 100% (5455/5455) | **21.6 ms** | 13.6–23.2 ms |
| 55 | 45.5 | 100% (5455/5455) | 21.6 ms | 19.5–23.2 ms |
| 60 | 45.5 | 100% (5455/5455) | 21.6 ms | 19.4–23.0 ms |
| 70 | 45.5 | 100% (5455/5455) | 21.6 ms | 19.8–23.0 ms |
| 80 | 45.5 | 100% (5455/5455) | 21.6 ms | 19.5–22.5 ms |
| 100 | 45.5 | 100% (5455/5455) | 21.6 ms | 19.9–22.7 ms |

Rate tracks the target exactly through 45 Hz. Between 45 and 50 Hz the system hits a
hard, deterministic ceiling: achieved throughput plateaus at **45.5 Hz** for every
target from 50 Hz up to 100 Hz, never higher, never lower, always at 100% "success"
(no serial errors — the client-side success check only verifies it got a valid `TX`
acknowledgement from the ESP32, not that it hit the requested rate, so a saturated
run still reads 100%). 45.5 Hz corresponds almost exactly to 1000 ⁄ 22 — i.e. the
system has settled into a fixed ~22ms-per-message cadence once it's permanently
"catching up" instead of sleeping between sends, which is also why `min_latency_ms`
converges upward (12–14ms below saturation → 19–20ms above it: below saturation the
loop is idle most of the time and catches the *best-case* round trip; above it, it's
always mid-transmission and reports something closer to the *typical* round trip).

That ~22ms plateau is consistent with the serial link, not the DW3000 radio itself.
The DW3000's over-the-air time for a ~35-byte frame at 6.8 Mbps with a 128-symbol
preamble is well under 1ms — nowhere near the bottleneck. A 35-byte CAM message
becomes 70 hex ASCII characters plus a newline (71 bytes) written at 115200 baud
(~6.2ms for the write alone), and the ESP32's ~40-character text ack
(`"TX 35 seq=… rx_latency=…ms tx_dur=…ms\r\n"`) costs another ~3.5ms back — roughly
10ms of pure serial transfer time before accounting for the CP210x USB-UART bridge's
own latency/buffering overhead, which plausibly accounts for the rest. In short: the
practical ceiling here is the **hex-over-serial link to the ESP32**, not CAM
generation (fixed in Bug 1) and not the UWB radio. A binary (non-hex) serial framing
or a higher baud rate would be the next place to look for headroom beyond ~45 Hz —
well above the ETSI CAM spec's own 1–10 Hz range, so not a practical concern for
compliant operation, only relevant if this rig is pushed as a synthetic load
generator.

---

## Dependencies

| Package | Used by | Purpose |
|---|---|---|
| `django` | RX | Web framework, ORM, management commands |
| `pyserial` | TX + RX | Serial port I/O on all platforms |
| `asn1tools` | TX + RX | ASN.1 compile + UPER encode/decode |
| `pynmea2` | TX | NMEA sentence parser |
