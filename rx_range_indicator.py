"""Large, live RX indicator for manual UWB range tests."""

import argparse
from collections import deque
import sys
import time

import asn1tools
import serial

from messages.serial_decode import compile_cam_template, decode_serial_line
import serial_ports


GREEN = "\033[1;97;42m"
RED = "\033[1;97;41m"
YELLOW = "\033[1;30;43m"
RESET = "\033[0m"
CLEAR = "\033[2J\033[H"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"

RECEIVING = (
    "██████  ███████  ██████ ███████ ██ ██    ██ ██ ███    ██  ██████ ",
    "██   ██ ██      ██      ██      ██ ██    ██ ██ ████   ██ ██       ",
    "██████  █████   ██      █████   ██ ██    ██ ██ ██ ██  ██ ██   ███ ",
    "██   ██ ██      ██      ██      ██  ██  ██  ██ ██  ██ ██ ██    ██ ",
    "██   ██ ███████  ██████ ███████ ██   ████   ██ ██   ████  ██████ ",
)

NO_SIGNAL = (
    "███    ██  ██████      ███████ ██  ██████  ███    ██  █████  ██      ",
    "████   ██ ██    ██     ██      ██ ██       ████   ██ ██   ██ ██      ",
    "██ ██  ██ ██    ██     ███████ ██ ██   ███ ██ ██  ██ ███████ ██      ",
    "██  ██ ██ ██    ██          ██ ██ ██    ██ ██  ██ ██ ██   ██ ██      ",
    "██   ████  ██████      ███████ ██  ██████  ██   ████ ██   ██ ███████ ",
)


def render(state, total, rate, age, invalid, port):
    if state == "receiving":
        color, banner, label = GREEN, RECEIVING, "VALID CAM FRAMES ARE ARRIVING"
    elif state == "waiting":
        color, banner, label = YELLOW, NO_SIGNAL, "WAITING FOR FIRST VALID CAM"
    else:
        color, banner, label = RED, NO_SIGNAL, "NO VALID CAM WITHIN TIMEOUT"

    width = max(len(line) for line in banner)
    lines = [CLEAR, color]
    lines.extend(f"  {line:<{width}}  " for line in banner)
    lines.append(f"  {label:^{width}}  ")
    lines.append(RESET)
    lines.append("")
    lines.append(f"  Port: {port}")
    lines.append(f"  Valid packets: {total:,}")
    lines.append(f"  Current rate: {rate:5.1f} packets/s")
    lines.append(
        "  Last valid packet: never"
        if age is None
        else f"  Last valid packet: {age:5.2f} s ago"
    )
    lines.append(f"  Invalid serial frames: {invalid:,}")
    lines.append("")
    lines.append("  Ctrl+C stops the indicator.")
    sys.stdout.write("\n".join(lines))
    sys.stdout.flush()


def main():
    parser = argparse.ArgumentParser(
        description="Full-screen CAM reception indicator for manual range tests"
    )
    parser.add_argument("--port", default=serial_ports.rx_port())
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument(
        "--encoding", choices=("auto", "hex", "binary"), default="auto"
    )
    parser.add_argument(
        "--lost-after",
        type=float,
        default=1.5,
        help="show NO SIGNAL after this many seconds without a valid CAM",
    )
    parser.add_argument(
        "--rate-window",
        type=float,
        default=2.0,
        help="rolling window used for the displayed packet rate",
    )
    parser.add_argument(
        "--no-beep", action="store_true", help="disable beep when signal state changes"
    )
    args = parser.parse_args()

    if args.lost_after <= 0 or args.rate_window <= 0:
        parser.error("--lost-after and --rate-window must be positive")

    template = compile_cam_template()
    arrivals = deque()
    total = 0
    invalid = 0
    last_valid = None
    previous_state = None
    next_render = 0.0

    sys.stdout.write(HIDE_CURSOR)
    sys.stdout.flush()
    try:
        with serial.Serial(args.port, args.baud, timeout=0.1) as ser:
            ser.reset_input_buffer()
            while True:
                line = ser.readline().strip()
                now = time.monotonic()

                if line:
                    try:
                        decode_serial_line(template, line, args.encoding)
                    except (ValueError, UnicodeDecodeError, asn1tools.DecodeError):
                        invalid += 1
                    else:
                        total += 1
                        last_valid = now
                        arrivals.append(now)

                cutoff = now - args.rate_window
                while arrivals and arrivals[0] < cutoff:
                    arrivals.popleft()

                age = None if last_valid is None else now - last_valid
                if last_valid is None:
                    state = "waiting"
                elif age <= args.lost_after:
                    state = "receiving"
                else:
                    state = "lost"

                if state != previous_state and previous_state is not None and not args.no_beep:
                    sys.stdout.write("\a")
                previous_state = state

                if now >= next_render:
                    rate = len(arrivals) / args.rate_window
                    render(state, total, rate, age, invalid, args.port)
                    next_render = now + 0.2
    except serial.SerialException as exc:
        sys.stdout.write(f"{CLEAR}{RED}\n  RX SERIAL ERROR: {exc}  \n{RESET}")
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        sys.stdout.write(f"{RESET}{SHOW_CURSOR}\n")
        sys.stdout.flush()


if __name__ == "__main__":
    raise SystemExit(main())
