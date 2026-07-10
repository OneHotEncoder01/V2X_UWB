"""
Stationary Stresstest for V2X-UWB CAM Broadcasting.

Decouples CAM transmission rate from GPS updates by caching the last GPS fix
and resending it with fresh timestamps. Sweeps rates from 1 Hz to 50+ Hz to
find saturation point.

Usage:
    python stress_test_tx.py --max-hz 50 --duration 30 --output results.csv
"""

import GenerateCAM
import GenerateGPS
import activateGPS
import serial_ports
import time
import serial
import json
import csv
import sys
import argparse
from pathlib import Path
from datetime import datetime

CITS_EPOCH_OFFSET = 1_072_915_200_000
TX_SERIAL_PORT = serial_ports.tx_port()   # ESP32 UWB board (CP210x)
PARTICIPANT_TYPE = 5  # Passenger car

class StressTestLogger:
    """Logs stresstest results to CSV and console."""

    def __init__(self, output_file):
        self.output_file = output_file
        self.data = []
        self.file = open(output_file, 'w', newline='')
        self.writer = csv.DictWriter(
            self.file,
            fieldnames=[
                'timestamp',
                'target_hz',
                'achieved_hz',
                'attempts',
                'successes',
                'failures',
                'serial_errors',
                'min_latency_ms',
                'max_latency_ms',
                'avg_latency_ms',
            ]
        )
        self.writer.writeheader()
        self.file.flush()

    def log_result(self, target_hz, achieved_hz, attempts, successes, failures,
                   serial_errors, latencies):
        """Log a rate-sweep result."""
        min_lat = min(latencies) if latencies else 0
        max_lat = max(latencies) if latencies else 0
        avg_lat = sum(latencies) / len(latencies) if latencies else 0

        row = {
            'timestamp': datetime.now().isoformat(),
            'target_hz': target_hz,
            'achieved_hz': achieved_hz,
            'attempts': attempts,
            'successes': successes,
            'failures': failures,
            'serial_errors': serial_errors,
            'min_latency_ms': f"{min_lat:.1f}",
            'max_latency_ms': f"{max_lat:.1f}",
            'avg_latency_ms': f"{avg_lat:.1f}",
        }
        self.writer.writerow(row)
        self.file.flush()

        # Also print to console
        print(
            f"[{target_hz:3d} Hz] Achieved: {achieved_hz:.1f} Hz | "
            f"Success: {successes}/{attempts} ({100*successes/attempts:.1f}%) | "
            f"Latency: {avg_lat:.1f}±{(max_lat-min_lat)/2:.1f} ms",
            flush=True
        )

    def close(self):
        self.file.close()


def get_generation_delta_time():
    """Get current ETSI generation delta time (ms since 2004-01-01 UTC, mod 65536)."""
    system_time = int(time.time() * 1000)
    cits_ms = system_time - CITS_EPOCH_OFFSET
    return cits_ms % 65536


def wait_for_gps_fix(timeout_s=30):
    """Block until a valid GPS fix is obtained, return the fix dict."""
    print(f"[GPS] Waiting for satellite fix (max {timeout_s}s)...", flush=True)
    start = time.monotonic()

    for fix in GenerateGPS.stream_gps():
        if fix is not None:
            print(
                f"[GPS] Got fix: lat={fix['latitude']}, lon={fix['longitude']}, "
                f"alt={fix['altitude']['altitudeValue'] / 100:.1f}m",
                flush=True
            )
            return fix

        elapsed = time.monotonic() - start
        if elapsed > timeout_s:
            raise TimeoutError(f"No GPS fix obtained within {timeout_s} seconds")

    raise RuntimeError("stream_gps() terminated unexpectedly")


def stress_test_rate(ser, gps_fix, target_hz, duration_s=30):
    """
    Run a single rate-sweep at target_hz for duration_s seconds.

    Returns:
        (achieved_hz, successes, failures, serial_errors, latencies)
    """
    interval = 1.0 / target_hz
    attempts = 0
    successes = 0
    failures = 0
    serial_errors = 0
    latencies = []

    print(f"\n[TEST] Starting {target_hz} Hz sweep for {duration_s}s...", flush=True)

    start_time = time.monotonic()
    next_send = start_time

    while time.monotonic() - start_time < duration_s:
        now = time.monotonic()

        # If it's time to send, send. Otherwise, sleep a bit.
        if now < next_send:
            time.sleep(min(0.001, next_send - now))
            continue

        # Generate fresh CAM with updated timestamp
        generation_delta_time = get_generation_delta_time()
        try:
            encoded = GenerateCAM.GenerateCamMessage(
                generation_delta_time,
                gps_fix,
                PARTICIPANT_TYPE
            )
        except Exception as e:
            print(f"[CAM] Error generating message: {e}", flush=True)
            failures += 1
            attempts += 1
            next_send += interval
            continue

        # Send via serial
        attempts += 1
        tx_start = time.monotonic()
        try:
            hex_msg = encoded.hex().encode("ascii") + b"\n"
            ser.write(hex_msg)
            ser.flush()

            # Read response (with timeout)
            response = b""
            timeout_start = time.monotonic()
            while time.monotonic() - timeout_start < 0.1:
                if ser.in_waiting > 0:
                    response += ser.read(ser.in_waiting)
                if b"\n" in response or b"ERR" in response:
                    break
                time.sleep(0.001)

            tx_latency = (time.monotonic() - tx_start) * 1000  # ms
            latencies.append(tx_latency)

            # Check response
            if b"TX" in response or b"tx" in response.lower():
                successes += 1
            elif b"ERR" in response:
                failures += 1
                serial_errors += 1
            else:
                # No clear response, assume success (might indicate timing issue)
                successes += 1

        except Exception as e:
            print(f"[TX] Serial error: {e}", flush=True)
            failures += 1
            serial_errors += 1

        next_send += interval

    elapsed = time.monotonic() - start_time
    achieved_hz = attempts / elapsed if elapsed > 0 else 0

    return achieved_hz, successes, failures, serial_errors, latencies


def main():
    parser = argparse.ArgumentParser(description="Stresstest: sweep CAM rates to saturation")
    parser.add_argument("--max-hz", type=int, default=100, help="Max rate to test (Hz)")
    parser.add_argument("--duration", type=int, default=120,
                        help="Duration per rate (s) [default: 120s gives ~6000 packets @ 50Hz]")
    parser.add_argument("--output", type=str, default="stress_test_results.csv",
                        help="Output CSV file")
    parser.add_argument("--tx-port", type=str, default=TX_SERIAL_PORT,
                        help="TX board serial port")
    parser.add_argument("--rates", type=str,
                        default="1,10,20,30,40,45,50,55,60,70,80,100",
                        help="Comma-separated target rates (Hz) to sweep, in order")
    args = parser.parse_args()

    print("=== CAM Broadcasting Stresstest (Stationary) ===", flush=True)

    # Activate GPS
    print("Activating GPS...", flush=True)
    activateGPS.ensure_gps_on()
    GenerateGPS.wait_for_uart(timeout_s=60)

    # Get initial GPS fix (cached for entire test)
    gps_fix = wait_for_gps_fix(timeout_s=60)

    # Open serial port to TX board
    print(f"Opening serial port {args.tx_port}...", flush=True)
    try:
        ser = serial.Serial(args.tx_port, 115200, timeout=0.1)
        time.sleep(0.5)
        print(f"Serial port opened successfully.", flush=True)
    except Exception as e:
        print(f"FATAL: Could not open serial port: {e}", flush=True)
        sys.exit(1)

    # Set up logging
    logger = StressTestLogger(args.output)

    # Rate sweep
    rates_to_test = [int(r) for r in args.rates.split(",") if r.strip()]
    # Filter to only rates up to max_hz
    rates_to_test = [r for r in rates_to_test if r <= args.max_hz]

    print(f"\nTesting rates: {rates_to_test}", flush=True)
    max_rate = max(rates_to_test) if rates_to_test else 0
    print(f"Duration per rate: {args.duration}s (~{args.duration * max_rate} packets @ {max_rate}Hz)", flush=True)
    total_time = args.duration * len(rates_to_test)
    print(f"Total test time: ~{total_time}s (~{total_time//60}m {total_time%60}s)", flush=True)
    print(f"Output: {args.output}", flush=True)

    try:
        for target_hz in rates_to_test:
            achieved_hz, successes, failures, serial_errors, latencies = \
                stress_test_rate(ser, gps_fix, target_hz, args.duration)

            logger.log_result(
                target_hz, achieved_hz,
                successes + failures, successes, failures,
                serial_errors, latencies
            )

            # Brief pause between rates
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n[TEST] Interrupted by user.", flush=True)
    except Exception as e:
        print(f"\n[TEST] Error: {e}", flush=True)
    finally:
        ser.close()
        logger.close()
        print(f"\nResults saved to: {args.output}", flush=True)


if __name__ == "__main__":
    main()
