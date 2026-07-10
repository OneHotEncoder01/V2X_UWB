# Stresstest Quickstart — V2X-UWB Scalability Test

## Timeline
- **Setup:** 5–10 min
- **Test run:** ~14 minutes (120s per rate, 7 rates)
- **Analysis:** ~5 min
- **Total:** ~30 min

---

## Pre-Flight Checklist

- [ ] Arduino TX sketch uploaded (`ex_01a_simple_tx_telemetry/ex_01a_simple_tx_telemetry.ino`)
- [ ] Raspberry Pi powered on, GPS HAT connected, serial ready
- [ ] ESP32 TX board connected to Pi via USB at `/dev/ttyUSB4`
- [ ] Laptop with RX ready (optional, for monitoring only)
- [ ] Terminal window open in `/home/onehotencoder/Documents/V2X_UWB/`
- [ ] **~30 min of uninterrupted time**

---

## Run Stresstest

### Command
```bash
python stress_test_tx.py --max-hz 50
```

### What happens
1. Waits for GPS satellite fix (~10–30 sec)
2. For each rate (1, 5, 10, 20, 30, 40, 50 Hz):
   - Sends CAM messages for 120 seconds
   - Prints live stats to console
3. Generates `stress_test_results.csv`

### Expected console output
```
[GPS] Waiting for satellite fix (max 30s)...
[GPS] Got fix: lat=48.8350, lon=10.1035, alt=448.5m

[TEST] Starting 1 Hz sweep for 120s...
[  1 Hz] Achieved: 1.0 Hz | Success: 120/120 (100.0%) | Latency: 4.2±0.1 ms

[TEST] Starting 5 Hz sweep for 120s...
[  5 Hz] Achieved: 5.0 Hz | Success: 600/600 (100.0%) | Latency: 4.5±0.2 ms

[TEST] Starting 10 Hz sweep for 120s...
[ 10 Hz] Achieved: 10.0 Hz | Success: 1200/1200 (100.0%) | Latency: 4.8±0.3 ms

... continues for 20, 30, 40, 50 Hz ...
```

### Look for these signs of saturation
```
[ 50 Hz] Achieved: 42.3 Hz | Success: 5076/6000 (84.6%) | Latency: 12.4±3.2 ms
                            ↑ Drops below 100%
                                              ↑ Latency rising
```

---

## After Test: Generate Plots

```bash
python plot_stress_results.py stress_test_results.csv
```

This creates:
- `stress_test_rate.png` — Where saturation occurs
- `stress_test_success.png` — Success % by rate
- `stress_test_latency.png` — TX latency (should stay < 50 ms)

---

## Key Metrics to Report in Thesis

1. **Saturation point:** e.g., "System reliably handles up to 40 Hz with 100% success rate; saturates at 50 Hz (85% success)"
2. **Latency:** e.g., "TX latency remains 4–12 ms across all rates, well below ETSI 50 ms requirement"
3. **Throughput:** e.g., "Peak measured throughput: ~6,000 CAM messages per rate × 7 rates = 42,000 total messages logged"

---

## Troubleshooting

| Problem | Solution |
|---|---|
| `ModuleNotFoundError: No module named 'GenerateCAM'` | Ensure you're in `/home/onehotencoder/Documents/V2X_UWB/` directory |
| GPS fix not arriving | Check GPS HAT power, antenna, clear sky view; try `python GenerateGPS.py` standalone |
| Serial port error on TX board | Check `/dev/ttyUSB4` exists; verify Arduino sketch uploaded; try `ls -la /dev/ttyUSB*` |
| Low success rate from start | ESP32 may need reset; try power-cycling the UWB board |
| `permission denied` on serial port | Add Pi user to dialout group: `usermod -a -G dialout $USER` |

---

## Notes

- Stresstest caches a **single GPS fix** and reuses it (decoupled from GPS rate)
- Each CAM gets a **fresh ETSI timestamp** for authenticity
- Serial port remains open during entire sweep
- Test is **stationary** (no movement)
- CSV output is suitable for thesis figures
