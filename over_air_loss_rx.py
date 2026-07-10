"""
Receive sequenced CAM frames for over-the-air packet-loss measurements.

Run this on the laptop/PC connected to the RX UWB board before starting
over_air_loss_tx.py on the Raspberry Pi.
"""

import argparse
import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import asn1tools
import serial

import serial_ports
from messages.serial_decode import compile_cam_template, decode_serial_line, flatten_cam


def iso_now():
    return datetime.now(timezone.utc).isoformat()


def split_station_id(station_id, seq_bits):
    if station_id is None:
        return None, None
    mask = (1 << seq_bits) - 1
    return station_id >> seq_bits, station_id & mask


class RxLogger:
    fieldnames = [
        "received_at",
        "elapsed_s",
        "event",
        "test_id",
        "seq",
        "station_id",
        "generation_delta_time",
        "payload_bytes",
        "payload_encoding",
        "asn_type",
        "raw_hex",
        "line",
        "error",
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


def row_base(start):
    return {
        "received_at": iso_now(),
        "elapsed_s": f"{time.monotonic() - start:.6f}",
    }


def print_summary(valid, invalid, rx_errors, duplicates, seen):
    print(
        f"[RX] valid={valid} unique={len(seen)} duplicates={duplicates} "
        f"invalid={invalid} rx_errors={rx_errors}",
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(
        description="RX-side sequenced CAM logger for over-the-air loss tests"
    )
    parser.add_argument("--port", default=serial_ports.rx_port())
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument(
        "--encoding",
        choices=("auto", "hex", "binary"),
        default="auto",
        help="Serial encoding emitted by the RX ESP32 sketch",
    )
    parser.add_argument("--duration", type=float, default=300.0)
    parser.add_argument("--output", default="over_air_rx_log.csv")
    parser.add_argument("--test-id", type=int, help="only log frames for this test id")
    parser.add_argument("--seq-bits", type=int, default=20)
    parser.add_argument("--raw", action="store_true", help="print raw serial lines")
    parser.add_argument(
        "--no-reset-input",
        action="store_true",
        help="do not clear pending serial input when the logger starts",
    )
    parser.add_argument("--progress-interval", type=float, default=10.0)
    args = parser.parse_args()

    if args.seq_bits <= 0 or args.seq_bits >= 32:
        parser.error("--seq-bits must be between 1 and 31")

    print("=== Over-the-air CAM packet-loss RX ===", flush=True)
    print(f"Listening on {args.port} at {args.baud}", flush=True)
    print(f"Available serial ports: {serial_ports.ports_summary()}", flush=True)
    print(f"Output: {args.output}", flush=True)
    if args.test_id is not None:
        print(f"Filtering test id: {args.test_id}", flush=True)

    template = compile_cam_template()
    logger = RxLogger(args.output)

    try:
        ser = serial.Serial(args.port, args.baud, timeout=1)
    except serial.SerialException as exc:
        print(f"FATAL: could not open RX serial port {args.port}: {exc}", flush=True)
        logger.close()
        return 1

    if not args.no_reset_input:
        ser.reset_input_buffer()

    start = time.monotonic()
    deadline = start + args.duration
    next_progress = start + args.progress_interval
    valid = 0
    invalid = 0
    rx_errors = 0
    duplicates = 0
    seen = set()

    try:
        while time.monotonic() < deadline:
            line = ser.readline().strip()
            now = time.monotonic()

            if now >= next_progress:
                print_summary(valid, invalid, rx_errors, duplicates, seen)
                next_progress = now + args.progress_interval

            if not line:
                continue

            if args.raw:
                print(f"RAW: {line!r}", flush=True)

            if line.upper().startswith(b"RX ERROR"):
                rx_errors += 1
                logger.write(
                    {
                        **row_base(start),
                        "event": "rx_error",
                        "test_id": "",
                        "seq": "",
                        "station_id": "",
                        "generation_delta_time": "",
                        "payload_bytes": "",
                        "payload_encoding": "",
                        "asn_type": "",
                        "raw_hex": "",
                        "line": line.decode("ascii", errors="replace"),
                        "error": "",
                    }
                )
                continue

            try:
                payload, decoded, payload_encoding, asn_type, station_id = decode_serial_line(
                    template,
                    line,
                    args.encoding,
                )
                fields = flatten_cam(decoded, station_id)
                frame_test_id, seq = split_station_id(fields["station_id"], args.seq_bits)
            except (ValueError, UnicodeDecodeError, asn1tools.DecodeError, NotImplementedError) as exc:
                invalid += 1
                logger.write(
                    {
                        **row_base(start),
                        "event": "invalid",
                        "test_id": "",
                        "seq": "",
                        "station_id": "",
                        "generation_delta_time": "",
                        "payload_bytes": "",
                        "payload_encoding": "",
                        "asn_type": "",
                        "raw_hex": "",
                        "line": line.decode("ascii", errors="replace"),
                        "error": str(exc),
                    }
                )
                continue

            if args.test_id is not None and frame_test_id != args.test_id:
                continue

            if seq is not None:
                key = (frame_test_id, seq)
                if key in seen:
                    duplicates += 1
                else:
                    seen.add(key)

            valid += 1
            logger.write(
                {
                    **row_base(start),
                    "event": "valid",
                    "test_id": frame_test_id if frame_test_id is not None else "",
                    "seq": seq if seq is not None else "",
                    "station_id": fields["station_id"] if fields["station_id"] is not None else "",
                    "generation_delta_time": fields["generation_delta_time"],
                    "payload_bytes": len(payload),
                    "payload_encoding": payload_encoding,
                    "asn_type": asn_type,
                    "raw_hex": payload.hex(),
                    "line": line.decode("ascii", errors="replace"),
                    "error": "",
                }
            )
    except KeyboardInterrupt:
        print("\n[RX] Interrupted", flush=True)
    finally:
        ser.close()
        logger.close()

    print_summary(valid, invalid, rx_errors, duplicates, seen)
    if seen:
        seqs = sorted(seq for _, seq in seen if seq is not None)
        if seqs:
            span = seqs[-1] - seqs[0] + 1
            missing_in_span = span - len(set(seqs))
            print(
                f"[RX] seq span {seqs[0]}..{seqs[-1]}: "
                f"missing-within-span={missing_in_span}",
                flush=True,
            )
    print(f"RX log saved to {args.output}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
