"""
Transmit sequenced CAM frames for over-the-air packet-loss measurements.

This is the TX-side companion to over_air_loss_rx.py. It runs on the Raspberry
Pi connected to the TX UWB board.
"""

import argparse
import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import serial

import GenerateCAM
import GenerateGPS
import activateGPS
import serial_ports


CITS_EPOCH_OFFSET = 1_072_915_200_000
PARTICIPANT_TYPE = 5
DEFAULT_RATES = "1,5,10,20,30,40,45"


def iso_now():
    return datetime.now(timezone.utc).isoformat()


def generation_delta_time():
    system_time = int(time.time() * 1000)
    cits_ms = system_time - CITS_EPOCH_OFFSET
    return cits_ms % 65536


def parse_rates(value):
    rates = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        rate = float(item)
        if rate <= 0:
            raise argparse.ArgumentTypeError("rates must be positive")
        rates.append(rate)
    if not rates:
        raise argparse.ArgumentTypeError("at least one rate is required")
    return rates


def wait_for_gps_fix(timeout_s, mock_gps):
    if mock_gps:
        fix = GenerateGPS.MockGPS()
        print(
            f"[GPS] Using mock fix: lat={fix['latitude']} lon={fix['longitude']}",
            flush=True,
        )
        return fix

    print(f"[GPS] Waiting for satellite fix (max {timeout_s}s)...", flush=True)
    deadline = time.monotonic() + timeout_s
    for fix in GenerateGPS.stream_gps():
        if fix is not None:
            print(
                f"[GPS] Got fix: lat={fix['latitude']} lon={fix['longitude']} "
                f"alt={fix['altitude']['altitudeValue'] / 100:.1f}m",
                flush=True,
            )
            return fix

        if time.monotonic() >= deadline:
            raise TimeoutError(f"No GPS fix obtained within {timeout_s} seconds")

    raise RuntimeError("stream_gps() terminated unexpectedly")


def read_tx_ack(ser, timeout_s):
    response = b""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        waiting = ser.in_waiting
        if waiting:
            response += ser.read(waiting)
        if b"\n" in response or b"ERR" in response:
            break
        time.sleep(0.001)
    text = response.decode("ascii", errors="replace").strip()
    ok = "TX" in text.upper() and "ERR" not in text.upper()
    return ok, text


def station_id_for(test_id, seq, seq_bits):
    if test_id < 0 or test_id >= (1 << (32 - seq_bits)):
        raise ValueError(f"test_id must fit in {32 - seq_bits} bits")
    if seq < 0 or seq >= (1 << seq_bits):
        raise ValueError(f"seq must fit in {seq_bits} bits")
    return (test_id << seq_bits) | seq


def rate_complete(start, attempts, args):
    if args.packets_per_rate is not None:
        return attempts >= args.packets_per_rate
    return time.monotonic() - start >= args.duration


class TxLogger:
    fieldnames = [
        "test_id",
        "rate_hz",
        "seq",
        "station_id",
        "sent_at",
        "elapsed_s",
        "generation_delta_time",
        "payload_bytes",
        "raw_hex",
        "tx_ok",
        "tx_ack",
        "tx_latency_ms",
        "serial_error",
    ]

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("w", newline="", encoding="utf-8")
        self.writer = csv.DictWriter(self.file, fieldnames=self.fieldnames)
        self.writer.writeheader()
        self.file.flush()

    def write(self, row):
        self.writer.writerow(row)
        self.file.flush()

    def close(self):
        self.file.close()


def run_rate(ser, logger, gps_fix, args, rate_hz, seq):
    interval = 1.0 / rate_hz
    start = time.monotonic()
    next_send = start
    attempts = 0
    tx_ok = 0
    tx_fail = 0

    if args.packets_per_rate is None:
        target = f"{args.duration:g}s"
    else:
        target = f"{args.packets_per_rate} packets"
    print(f"\n[TEST] TX {rate_hz:g} Hz for {target}", flush=True)

    while not rate_complete(start, attempts, args):
        now = time.monotonic()
        if now < next_send:
            time.sleep(min(0.001, next_send - now))
            continue

        station_id = station_id_for(args.test_id, seq, args.seq_bits)
        gdt = generation_delta_time()
        sent_at = iso_now()
        elapsed_s = time.monotonic() - start
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
                "rate_hz": f"{rate_hz:g}",
                "seq": seq,
                "station_id": station_id,
                "sent_at": sent_at,
                "elapsed_s": f"{elapsed_s:.6f}",
                "generation_delta_time": gdt,
                "payload_bytes": len(encoded),
                "raw_hex": encoded.hex(),
                "tx_ok": "1" if ok else "0",
                "tx_ack": ack,
                "tx_latency_ms": f"{latency_ms:.3f}",
                "serial_error": serial_error,
            }
        )

        progress_every = max(1, int(rate_hz * 10))
        if args.packets_per_rate is not None:
            progress_every = min(progress_every, max(1, args.packets_per_rate // 5))

        if attempts % progress_every == 0:
            achieved = attempts / max(time.monotonic() - start, 0.001)
            print(
                f"[{rate_hz:g} Hz] seq={seq} attempts={attempts} "
                f"tx_ok={tx_ok} tx_fail={tx_fail} achieved={achieved:.1f} Hz",
                flush=True,
            )

        seq += 1
        next_send += interval

    elapsed = time.monotonic() - start
    achieved = attempts / elapsed if elapsed > 0 else 0
    print(
        f"[{rate_hz:g} Hz] done: attempts={attempts} tx_ok={tx_ok} "
        f"tx_fail={tx_fail} achieved={achieved:.2f} Hz",
        flush=True,
    )
    return seq


def main():
    parser = argparse.ArgumentParser(
        description="TX-side sequenced CAM sender for over-the-air loss tests"
    )
    parser.add_argument("--tx-port", default=serial_ports.tx_port())
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--rates", type=parse_rates, default=parse_rates(DEFAULT_RATES))
    parser.add_argument("--duration", type=float, default=300.0, help="seconds per rate")
    parser.add_argument(
        "--packets-per-rate",
        type=int,
        help="send exactly this many packets at each rate instead of using --duration",
    )
    parser.add_argument("--output", default="over_air_tx_log.csv")
    parser.add_argument(
        "--test-id",
        type=int,
        default=int(time.time()) & 0xFFF,
        help="12-bit test id encoded in stationId high bits",
    )
    parser.add_argument("--seq-bits", type=int, default=20)
    parser.add_argument("--start-seq", type=int, default=1)
    parser.add_argument("--participant-type", type=int, default=PARTICIPANT_TYPE)
    parser.add_argument("--gps-timeout", type=float, default=60.0)
    parser.add_argument("--mock-gps", action="store_true")
    parser.add_argument("--no-gps-activate", action="store_true")
    parser.add_argument(
        "--gps-at-port",
        help="GPS AT command port; omit to use the platform default",
    )
    parser.add_argument("--gps-at-baud", type=int, default=115200)
    parser.add_argument("--ack-timeout", type=float, default=0.1)
    args = parser.parse_args()

    if args.seq_bits <= 0 or args.seq_bits >= 32:
        parser.error("--seq-bits must be between 1 and 31")
    if args.packets_per_rate is not None and args.packets_per_rate <= 0:
        parser.error("--packets-per-rate must be positive")

    print("=== Over-the-air CAM packet-loss TX ===", flush=True)
    print(f"Test id: {args.test_id}", flush=True)
    print(f"Rates: {[f'{rate:g}' for rate in args.rates]} Hz", flush=True)
    if args.packets_per_rate is None:
        print(f"Duration per rate: {args.duration:g}s", flush=True)
    else:
        print(f"Packets per rate: {args.packets_per_rate}", flush=True)
    print(f"Output: {args.output}", flush=True)

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
    time.sleep(0.5)
    logger = TxLogger(args.output)
    seq = args.start_seq

    try:
        for rate in args.rates:
            seq = run_rate(ser, logger, gps_fix, args, rate, seq)
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[TEST] Interrupted", flush=True)
    finally:
        logger.close()
        ser.close()

    print(f"\nTX log saved to {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
