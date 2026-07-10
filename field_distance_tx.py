"""
Autonomous Pi-side distance test transmitter.

Reads a CSV plan with distance/condition phases, waits during setup gaps, then
sends sequenced full CAM frames for each phase. It is designed for field tests
where the Pi cannot be controlled over SSH once the boards are moved outside.
"""

import argparse
import csv
import time
from datetime import datetime, timezone
from pathlib import Path

import serial

import GenerateCAM
import GenerateGPS
import activateGPS
import serial_ports
from over_air_loss_tx import (
    PARTICIPANT_TYPE,
    generation_delta_time,
    read_tx_ack,
    station_id_for,
    wait_for_gps_fix,
)


FIELDNAMES = [
    "test_id",
    "phase",
    "distance_m",
    "condition",
    "rate_hz",
    "seq",
    "station_id",
    "sent_at",
    "phase_elapsed_s",
    "total_elapsed_s",
    "generation_delta_time",
    "payload_bytes",
    "raw_hex",
    "tx_ok",
    "tx_ack",
    "tx_latency_ms",
    "serial_error",
    "notes",
]


def iso_now():
    return datetime.now(timezone.utc).isoformat()


def _float(value, default=0.0):
    if value in (None, ""):
        return default
    return float(value)


def _int(value, default=0):
    if value in (None, ""):
        return default
    return int(value)


def read_plan(path):
    phases = []
    with Path(path).open(newline="", encoding="utf-8") as file:
        reader = csv.DictReader(file)
        for index, row in enumerate(reader, start=1):
            rate_hz = _float(row.get("rate_hz"))
            packets = _int(row.get("packets"))
            if rate_hz <= 0:
                raise ValueError(f"plan row {index}: rate_hz must be positive")
            if packets <= 0:
                raise ValueError(f"plan row {index}: packets must be positive")

            phases.append(
                {
                    "phase": row.get("phase") or str(index),
                    "distance_m": row.get("distance_m", ""),
                    "condition": row.get("condition") or "LOS",
                    "rate_hz": rate_hz,
                    "packets": packets,
                    "setup_delay_s": _float(row.get("setup_delay_s"), 0.0),
                    "notes": row.get("notes", ""),
                }
            )
    if not phases:
        raise ValueError(f"plan has no phases: {path}")
    return phases


def estimate_seconds(phases):
    return sum(phase["setup_delay_s"] + phase["packets"] / phase["rate_hz"] for phase in phases)


class FieldLogger:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("w", newline="", encoding="utf-8")
        self.writer = csv.DictWriter(self.file, fieldnames=FIELDNAMES)
        self.writer.writeheader()
        self.file.flush()

    def write(self, row):
        self.writer.writerow(row)
        self.file.flush()

    def close(self):
        self.file.close()


def sleep_countdown(seconds, label):
    remaining = int(seconds)
    if remaining <= 0:
        return
    print(f"[SETUP] {label}: waiting {remaining}s", flush=True)
    while remaining > 0:
        step = min(10, remaining)
        time.sleep(step)
        remaining -= step
        if remaining:
            print(f"[SETUP] {remaining}s remaining", flush=True)


def run_phase(ser, logger, gps_fix, args, phase, seq, total_start):
    interval = 1.0 / phase["rate_hz"]
    attempts = 0
    tx_ok = 0
    tx_fail = 0
    phase_start = time.monotonic()
    next_send = phase_start
    progress_every = max(1, min(int(phase["rate_hz"] * 10), phase["packets"] // 5 or 1))

    print(
        f"\n[PHASE {phase['phase']}] {phase['distance_m']}m {phase['condition']} "
        f"{phase['rate_hz']:g} Hz x {phase['packets']} packets",
        flush=True,
    )

    while attempts < phase["packets"]:
        now = time.monotonic()
        if now < next_send:
            time.sleep(min(0.001, next_send - now))
            continue

        station_id = station_id_for(args.test_id, seq, args.seq_bits)
        gdt = generation_delta_time()
        sent_at = iso_now()
        phase_elapsed = time.monotonic() - phase_start
        total_elapsed = time.monotonic() - total_start
        serial_error = ""
        ack = ""
        ok = False
        latency_ms = 0.0

        try:
            encoded = GenerateCAM.GenerateWrappedCamMessage(
                gdt,
                gps_fix,
                station_id,
                args.participant_type,
            )
            tx_start = time.monotonic()
            ser.write(encoded.hex().encode("ascii") + b"\n")
            ser.flush()
            ok, ack = read_tx_ack(ser, args.ack_timeout)
            latency_ms = (time.monotonic() - tx_start) * 1000
        except Exception as exc:
            encoded = b""
            serial_error = str(exc)

        attempts += 1
        if ok:
            tx_ok += 1
        else:
            tx_fail += 1

        logger.write(
            {
                "test_id": args.test_id,
                "phase": phase["phase"],
                "distance_m": phase["distance_m"],
                "condition": phase["condition"],
                "rate_hz": f"{phase['rate_hz']:g}",
                "seq": seq,
                "station_id": station_id,
                "sent_at": sent_at,
                "phase_elapsed_s": f"{phase_elapsed:.6f}",
                "total_elapsed_s": f"{total_elapsed:.6f}",
                "generation_delta_time": gdt,
                "payload_bytes": len(encoded),
                "raw_hex": encoded.hex(),
                "tx_ok": "1" if ok else "0",
                "tx_ack": ack,
                "tx_latency_ms": f"{latency_ms:.3f}",
                "serial_error": serial_error,
                "notes": phase["notes"],
            }
        )

        if attempts % progress_every == 0:
            achieved = attempts / max(time.monotonic() - phase_start, 0.001)
            print(
                f"[PHASE {phase['phase']}] seq={seq} attempts={attempts} "
                f"tx_ok={tx_ok} tx_fail={tx_fail} achieved={achieved:.1f} Hz",
                flush=True,
            )

        seq += 1
        next_send += interval

    elapsed = time.monotonic() - phase_start
    achieved = attempts / elapsed if elapsed > 0 else 0.0
    print(
        f"[PHASE {phase['phase']}] done: attempts={attempts} tx_ok={tx_ok} "
        f"tx_fail={tx_fail} achieved={achieved:.2f} Hz",
        flush=True,
    )
    return seq


def main():
    parser = argparse.ArgumentParser(description="Autonomous Pi distance-test TX")
    parser.add_argument("--plan", default="field_distance_plan.csv")
    parser.add_argument("--output", default="field_distance_tx_log.csv")
    parser.add_argument("--tx-port", default=serial_ports.tx_port())
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--test-id", type=int, default=int(time.time()) & 0xFFF)
    parser.add_argument("--seq-bits", type=int, default=20)
    parser.add_argument("--start-seq", type=int, default=1)
    parser.add_argument("--participant-type", type=int, default=PARTICIPANT_TYPE)
    parser.add_argument("--gps-timeout", type=float, default=60.0)
    parser.add_argument("--mock-gps", action="store_true")
    parser.add_argument("--no-gps-activate", action="store_true")
    parser.add_argument("--gps-at-port")
    parser.add_argument("--gps-at-baud", type=int, default=115200)
    parser.add_argument("--ack-timeout", type=float, default=0.1)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.seq_bits <= 0 or args.seq_bits >= 32:
        parser.error("--seq-bits must be between 1 and 31")
    if args.test_id < 0 or args.test_id >= (1 << (32 - args.seq_bits)):
        parser.error("--test-id is too large for the selected --seq-bits")

    phases = read_plan(args.plan)
    estimate = estimate_seconds(phases)

    print("=== Autonomous UWB distance packet-loss TX ===", flush=True)
    print(f"Plan: {args.plan}", flush=True)
    print(f"Output: {args.output}", flush=True)
    print(f"Test id: {args.test_id}", flush=True)
    print(f"Estimated run time: {estimate / 60:.1f} min", flush=True)
    for phase in phases:
        print(
            f"  phase {phase['phase']}: {phase['distance_m']}m {phase['condition']} "
            f"{phase['rate_hz']:g} Hz x {phase['packets']} "
            f"(setup {phase['setup_delay_s']:g}s)",
            flush=True,
        )

    if args.dry_run:
        return 0

    if not args.no_gps_activate and not args.mock_gps:
        print("[GPS] Activating GPS HAT...", flush=True)
        if args.gps_at_port:
            activateGPS.ensure_gps_on(args.gps_at_port, args.gps_at_baud)
        else:
            activateGPS.ensure_gps_on()
        GenerateGPS.wait_for_uart(timeout_s=args.gps_timeout)

    gps_fix = wait_for_gps_fix(args.gps_timeout, args.mock_gps)

    try:
        ser = serial.Serial(args.tx_port, args.baud, timeout=0.05)
    except serial.SerialException as exc:
        print(f"FATAL: could not open TX serial port {args.tx_port}: {exc}", flush=True)
        return 1

    print(f"[TX] Serial opened: {args.tx_port} at {args.baud}", flush=True)
    logger = FieldLogger(args.output)
    seq = args.start_seq
    total_start = time.monotonic()

    try:
        for phase in phases:
            sleep_countdown(
                phase["setup_delay_s"],
                f"move to phase {phase['phase']} ({phase['distance_m']}m {phase['condition']})",
            )
            seq = run_phase(ser, logger, gps_fix, args, phase, seq, total_start)
    except KeyboardInterrupt:
        print("\n[TEST] Interrupted", flush=True)
    finally:
        logger.close()
        ser.close()

    print(f"\nTX log saved to {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
