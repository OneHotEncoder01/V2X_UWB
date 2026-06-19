from datetime import datetime, timezone
from pathlib import Path

import pynmea2
import serial


SERIAL_PORT = "/dev/serial0"
BAUD_RATE = 9600
NMEA_FILE = Path(__file__).with_name("output.nmea")

ITS_EPOCH = datetime(2004, 1, 1, tzinfo=timezone.utc)
KNOT_TO_MPS = 0.5144444444444445

LATITUDE_UNAVAILABLE = 900_000_001
LONGITUDE_UNAVAILABLE = 1_800_000_001
SPEED_OUT_OF_RANGE = 16_382
SPEED_UNAVAILABLE = 16_383
HEADING_UNAVAILABLE = 3_601
ALTITUDE_NEGATIVE_OUT_OF_RANGE = -100_000
ALTITUDE_POSITIVE_OUT_OF_RANGE = 800_000
ALTITUDE_UNAVAILABLE = 800_001
POSITION_CONFIDENCE_OUT_OF_RANGE = 4_094
POSITION_CONFIDENCE_UNAVAILABLE = 4_095

_mock_locations = None
_mock_index = 0


def _float(value):
    return float(value) if value not in (None, "") else None


def _its_timestamp(datestamp, timestamp):
    gps_time = datetime.combine(datestamp, timestamp, tzinfo=timezone.utc)
    return int((gps_time - ITS_EPOCH).total_seconds() * 1000)


def _latitude(value):
    if value is None:
        return LATITUDE_UNAVAILABLE

    encoded = int(round(value * 10_000_000))
    if encoded < -900_000_000 or encoded > 900_000_000:
        return LATITUDE_UNAVAILABLE
    return encoded


def _longitude(value):
    if value is None:
        return LONGITUDE_UNAVAILABLE

    encoded = int(round(value * 10_000_000))
    if encoded <= -1_800_000_000 or encoded > 1_800_000_000:
        return LONGITUDE_UNAVAILABLE
    return encoded


def _heading_value(heading_deg):
    if heading_deg is None:
        return HEADING_UNAVAILABLE

    return int(round((heading_deg % 360.0) * 10)) % 3600


def _speed_value(speed_mps):
    if speed_mps is None:
        return SPEED_UNAVAILABLE

    encoded = int(round(speed_mps * 100))
    if encoded < 0:
        return SPEED_UNAVAILABLE
    if encoded >= SPEED_OUT_OF_RANGE:
        return SPEED_OUT_OF_RANGE
    return encoded


def _altitude_value(altitude_m):
    if altitude_m is None:
        return ALTITUDE_UNAVAILABLE

    encoded = int(round(altitude_m * 100))
    if encoded <= ALTITUDE_NEGATIVE_OUT_OF_RANGE:
        return ALTITUDE_NEGATIVE_OUT_OF_RANGE
    if encoded >= ALTITUDE_POSITIVE_OUT_OF_RANGE:
        return ALTITUDE_POSITIVE_OUT_OF_RANGE
    return encoded


def _position_confidence(hdop):
    if hdop is None:
        return POSITION_CONFIDENCE_UNAVAILABLE

    encoded = int(round(hdop * 100))
    if encoded >= POSITION_CONFIDENCE_OUT_OF_RANGE:
        return POSITION_CONFIDENCE_OUT_OF_RANGE
    return max(1, encoded)


def _altitude_confidence(hdop):
    if hdop is None:
        return "unavailable"
    if hdop <= 0.5:
        return "alt-000-50"
    if hdop <= 1.0:
        return "alt-001-00"
    if hdop <= 2.0:
        return "alt-002-00"
    if hdop <= 5.0:
        return "alt-005-00"
    if hdop <= 10.0:
        return "alt-010-00"
    return "unavailable"


def _cam_from_fix(rmc, gga=None):
    speed_mps = _float(getattr(rmc, "spd_over_grnd", None))
    speed_mps = speed_mps * KNOT_TO_MPS if speed_mps is not None else None

    heading_deg = _float(getattr(rmc, "true_course", None))
    altitude_m = _float(getattr(gga, "altitude", None)) if gga else None
    hdop = _float(getattr(gga, "horizontal_dil", None)) if gga else None

    heading_value = _heading_value(heading_deg)
    speed_value = _speed_value(speed_mps)
    altitude_value = _altitude_value(altitude_m)
    position_confidence = _position_confidence(hdop)

    return {
        "timestampIts": _its_timestamp(rmc.datestamp, rmc.timestamp),
        "latitude": _latitude(rmc.latitude),
        "longitude": _longitude(rmc.longitude),
        "heading": {
            "headingValue": heading_value,
            "headingConfidence": 127,
        },
        "speed": {
            "speedValue": speed_value,
            "speedConfidence": 127,
        },
        "positionConfidenceEllipse": {
            "semiMajorConfidence": position_confidence,
            "semiMinorConfidence": position_confidence,
            "semiMajorOrientation": heading_value,
        },
        "altitude": {
            "altitudeValue": altitude_value,
            "altitudeConfidence": _altitude_confidence(hdop),
        },
    }


def _locations_from_lines(lines):
    latest_gga = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        try:
            msg = pynmea2.parse(line)
        except pynmea2.ParseError:
            continue

        if msg.sentence_type == "GGA" and getattr(msg, "gps_qual", "0") != "0":
            latest_gga = msg

        elif msg.sentence_type == "RMC" and getattr(msg, "status", "") == "A":
            yield _cam_from_fix(msg, latest_gga)


def GetGPS():
    with serial.Serial(SERIAL_PORT, baudrate=BAUD_RATE, timeout=1) as gps:
        for location in _locations_from_lines(
            gps.readline().decode("ascii", errors="replace") for _ in iter(int, 1)
        ):
            return location


def MockGPS():
    global _mock_locations, _mock_index

    if _mock_locations is None:
        with NMEA_FILE.open("r", encoding="utf-8") as file:
            _mock_locations = list(_locations_from_lines(file))

    if not _mock_locations:
        raise ValueError(f"No valid GPS locations found in {NMEA_FILE}")

    location = _mock_locations[_mock_index]
    _mock_index = (_mock_index + 1) % len(_mock_locations)

    return location.copy()


if __name__ == "__main__":
    print(MockGPS())
