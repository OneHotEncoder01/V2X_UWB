# Over-the-Air Packet-Loss Test

This test measures real UWB delivery, not only TX-board serial acknowledgements.
The TX side sends full CAM frames with a monotonically increasing test sequence
encoded in the ITS-PDU `stationId`. The RX side decodes received UWB frames and
the analyzer compares unique RX sequence numbers against the TX CSV.

## Recommended 5000-Packet Sweep

Use higher rates for the UWB stress test. `1 Hz` is useful as a smoke test but
takes too long for a meaningful fixed-count run and does not stress the link.

```bash
venv/bin/python run_over_air_loss_test.py \
  --rates 10,20,30,40,45,50,60 \
  --packets-per-rate 5000
```

## Completed Run: 2026-07-10

Run directory:

```text
over_air_runs/uwb_5000_high_rates/
```

Summary file:

```text
over_air_runs/uwb_5000_high_rates/over_air_loss_summary_2181.csv
```

| Target Hz | TX OK | RX unique | Lost | Loss | Achieved TX Hz |
|---:|---:|---:|---:|---:|---:|
| 10 | 5000 | 5000 | 0 | 0.000% | 10.000 |
| 20 | 5000 | 5000 | 0 | 0.000% | 20.000 |
| 30 | 5000 | 5000 | 0 | 0.000% | 30.000 |
| 40 | 5000 | 5000 | 0 | 0.000% | 40.000 |
| 45 | 5000 | 5000 | 0 | 0.000% | 45.000 |
| 50 | 5000 | 5000 | 0 | 0.000% | 45.455 |
| 60 | 5000 | 5000 | 0 | 0.000% | 45.454 |

Total: **35000 / 35000 packets received**, **0.000% packet loss**,
no duplicate sequence numbers, no invalid RX frames, and no missing sequence
numbers in the full `1..35000` sequence span.

Interpretation: the link did not show measurable over-the-air packet loss in
this run. At `50 Hz` and `60 Hz`, the transmitter could not achieve the requested
rate and settled at about `45.45 Hz`, matching the earlier serial/TX-side
throughput ceiling. That is a throughput saturation limit before packet loss,
not a UWB packet-loss limit.

The runner:

1. Opens an SSH control connection to the Pi.
2. Starts `over_air_loss_rx.py` locally on the RX board.
3. Stops `cam_transmitter.service` on the Pi so the test has exclusive TX serial access.
4. Runs `over_air_loss_tx.py` on the Pi.
5. Restarts `cam_transmitter.service` when TX exits.
6. Fetches the Pi TX CSV with `scp`.
7. Runs `analyze_over_air_loss.py` and writes the summary CSV.

Results are written under `over_air_runs/<timestamp>_test<id>/`:

| File | Purpose |
|---|---|
| `over_air_tx_<id>.csv` | TX denominator: one row per attempted sequenced CAM |
| `over_air_rx_<id>.csv` | RX evidence: one row per decoded received CAM |
| `over_air_loss_summary_<id>.csv` | Per-rate packet delivery and loss percentage |
| `tx_console.log` / `rx_console.log` | Full console logs for troubleshooting |
| `run_metadata.json` | Test parameters used for the run |

## Why Fixed Packet Count

For packet loss, fixed count is the cleanest denominator:

```text
loss % = (TX OK packets - RX unique packets) / TX OK packets * 100
```

So a 5000-packet row can be reported directly, for example:

```text
40 Hz: 5000 TX OK, 4992 RX unique, 8 lost, 0.160% loss
```

Duration-based tests are still useful for soak testing, but they make the
denominator depend on achieved rate and saturation behavior.

## Problems Encountered and Fixes

| Problem | Solution |
|---|---|
| Existing `stress_test_tx.py` only measured TX serial acknowledgements. | Added sequenced over-the-air TX/RX/analyzer scripts so loss is measured at the receiver. |
| CAM payload-only frames had no stable packet sequence. | Added `GenerateWrappedCamMessage()` and encoded the test sequence in the full CAM `stationId`. |
| The normal Pi transmitter service occupied the TX serial board. | The automated runner stops `cam_transmitter.service` before the test and restarts it afterward. |
| SSH/scp would otherwise ask for passwords more than once. | The runner uses an SSH control connection and prepares `sudo` at the beginning. |
| Local sandbox serial enumeration initially showed no RX device. | Verified the real host sees the RX CP2104 board as `/dev/ttyUSB0`; the runner defaults through `serial_ports.rx_port()`. |

## Useful Variants

Short smoke test:

```bash
venv/bin/python run_over_air_loss_test.py \
  --rates 10,40,50 \
  --packets-per-rate 100 \
  --run-name smoke
```

Manual RX only:

```bash
venv/bin/python over_air_loss_rx.py \
  --port /dev/ttyUSB0 \
  --test-id 1001 \
  --duration 300 \
  --output over_air_rx_1001.csv
```

Manual Pi TX only:

```bash
ssh pi 'cd /home/sinan/CAM_Broadcaster && ./bin/python over_air_loss_tx.py \
  --test-id 1001 \
  --rates 10,20,30,40,45,50,60 \
  --packets-per-rate 5000 \
  --output over_air_tx_1001.csv'
```

## No-SSH Outdoor Distance Workflow

For outdoor range tests, do not rely on live SSH control. Use the autonomous
field transmitter. On the Pi itself, or over SSH while it is still reachable,
run:

```bash
cd /home/sinan/CAM_Broadcaster
./bin/python field_distance_tx.py \
  --plan field_distance_plan.csv \
  --test-id 1201 \
  --output field_distance_tx_1201.csv
```

The Pi reads `field_distance_plan.csv`, waits the configured setup delay before
each phase, sends the requested number of sequenced CAMs, and logs the TX
denominator locally. You can start this before walking outside; the Pi does not
need network access during the run.

At the laptop/RX side, start one long RX recording before the Pi begins
transmitting:

```bash
venv/bin/python over_air_loss_rx.py \
  --port /dev/ttyUSB0 \
  --test-id 1201 \
  --duration 1800 \
  --output field_distance_rx_1201.csv \
  --progress-interval 30
```

After the field run, return to Wi-Fi or plug the Pi back in, fetch the TX CSV,
and analyze by distance:

```bash
scp pi:/home/sinan/CAM_Broadcaster/field_distance_tx_1201.csv .

venv/bin/python analyze_field_distance_loss.py \
  field_distance_tx_1201.csv \
  field_distance_rx_1201.csv \
  --test-id 1201 \
  --output field_distance_summary_1201.csv
```

The included starter plan uses `1000` packets at `10 Hz` per distance because
that already takes about 100 seconds per point. For the final paper run, change
`packets` to `5000` for the most important distances, or keep `1000` for a
wide scouting sweep and repeat only the edge cases where loss starts to appear.

Recommended field strategy:

| Pass | Distances | Packets | Purpose |
|---|---|---:|---|
| Scout | 1, 5, 10, 20, 30, 40, 50 m LOS + one NLOS point | 1000 | Find where loss begins without spending too long |
| Final LOS | Near the loss threshold and one short-range baseline | 5000 | Strong paper-quality PDR numbers |
| Final NLOS | Wall/vehicle/body-blocked cases | 1000-5000 | Show realistic obstruction behavior |

Indoor tape-measure starter plan:

```csv
phase,distance_m,condition,rate_hz,packets,setup_delay_s,notes
1,1,LOS,10,1000,30,indoor baseline
2,2,LOS,10,1000,30,indoor LOS
3,3,LOS,10,1000,30,indoor LOS
4,5,LOS,10,1000,45,indoor LOS
5,7,LOS,10,1000,45,indoor max tape
```

If every LOS point is still `0%` loss, add NLOS phases at the same measured
distances: one wall between boards, door open/closed, or a body/vehicle blocking
line of sight. Those conditions are more likely to reveal useful loss behavior
than simply repeating short-range LOS for longer.
