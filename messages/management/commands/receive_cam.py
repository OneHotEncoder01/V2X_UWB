from django.core.management.base import BaseCommand
import asn1tools
import serial
from serial.tools import list_ports

from messages.models import CamMessage
from messages.serial_decode import compile_cam_template, decode_serial_line, flatten_cam


class Command(BaseCommand):
    help = "Read CAM frames from a UWB RX board serial port and store them for the dashboard."

    def add_arguments(self, parser):
        parser.add_argument("--port", default="/dev/ttyUSB0", help="RX board serial port")
        parser.add_argument("--baud", type=int, default=115200, help="RX board baud rate")
        parser.add_argument(
            "--encoding",
            choices=("auto", "hex", "binary"),
            default="auto",
            help="Serial frame encoding emitted by the RX sketch",
        )
        parser.add_argument("--raw", action="store_true", help="Print every raw serial line")
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing dashboard messages before receiving",
        )

    def available_ports(self):
        return ", ".join(port.device for port in list_ports.comports()) or "none"

    def handle(self, *args, **options):
        if options["clear"]:
            deleted, _ = CamMessage.objects.all().delete()
            self.stdout.write(f"Cleared {deleted} existing message records")

        template = compile_cam_template()
        self.stdout.write(
            self.style.SUCCESS(
                f"Listening for CAM frames on {options['port']} at {options['baud']} baud"
            )
        )
        self.stdout.write(f"Available serial ports: {self.available_ports()}")

        with serial.Serial(options["port"], options["baud"], timeout=1) as ser:
            while True:
                line = ser.readline().strip()
                if not line:
                    continue

                if options["raw"]:
                    self.stdout.write(f"RAW: {line!r}")

                try:
                    payload, decoded, payload_encoding, asn_type = decode_serial_line(
                        template,
                        line,
                        options["encoding"],
                    )
                    fields = flatten_cam(decoded)
                except (ValueError, UnicodeDecodeError, asn1tools.DecodeError) as exc:
                    self.stderr.write(f"Invalid CAM frame: {exc} ({line!r})")
                    continue

                message = CamMessage.objects.create(
                    generation_delta_time=fields["generation_delta_time"],
                    station_type=fields["station_type"],
                    latitude=fields["latitude"],
                    longitude=fields["longitude"],
                    altitude_m=fields["altitude_m"],
                    speed_mps=fields["speed_mps"],
                    heading_deg=fields["heading_deg"],
                    drive_direction=fields["drive_direction"],
                    raw_hex=payload.hex(),
                    decoded=decoded,
                )
                self.stdout.write(
                    f"Stored CAM #{message.id}: "
                    f"lat={message.latitude} lon={message.longitude} "
                    f"speed={message.speed_mps}m/s "
                    f"format={payload_encoding}/{asn_type}"
                )
