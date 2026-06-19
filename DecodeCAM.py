import serial
import asn1tools
import argparse
import time
from serial.tools import list_ports

from messages.serial_decode import compile_cam_template, decode_serial_line


def _available_ports():
    return ", ".join(port.device for port in list_ports.comports()) or "none"


parser = argparse.ArgumentParser(description="Receive and decode CAM frames from a UWB RX board.")
parser.add_argument("--port", default="/dev/ttyUSB0", help="RX board serial port")
parser.add_argument("--baud", type=int, default=115200, help="RX board baud rate")
parser.add_argument(
    "--encoding",
    choices=("auto", "hex", "binary"),
    default="auto",
    help="Serial frame encoding emitted by the RX sketch",
)
parser.add_argument("--raw", action="store_true", help="Print every raw serial line before decoding")
parser.add_argument("--status-interval", type=float, default=5.0, help="Seconds between waiting messages")
args = parser.parse_args()

print(f"Opening RX serial port {args.port} at {args.baud} baud")
print(f"Available serial ports: {_available_ports()}")
ser = serial.Serial(args.port, args.baud, timeout=1)


template = compile_cam_template()
last_status = time.monotonic()

while True:
    line = ser.readline().strip()
    if not line:
        now = time.monotonic()
        if now - last_status >= args.status_interval:
            print(f"Waiting for CAM frames on {args.port}...")
            last_status = now
        continue

    if args.raw:
        print(f"RAW: {line!r}")

    try:
        _payload, decoded, payload_encoding, asn_type = decode_serial_line(
            template,
            line,
            args.encoding,
        )
    except (ValueError, UnicodeDecodeError, asn1tools.DecodeError) as exc:
        print(f"Invalid CAM frame: {exc} ({line!r})")
        continue

    print(f"Decoded as {payload_encoding}/{asn_type}")
    print(decoded)
