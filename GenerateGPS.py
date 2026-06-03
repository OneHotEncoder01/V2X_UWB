from datetime import datetime, timezone
from pathlib import Path


NMEA_FILE = Path(__file__).with_name('output.nmea')
_mock_locations = None
_mock_location_index = 0

def parse_nmea_to_decimal(coord_str, direction):
    """
    Converts NMEA DDMM.MMMM (Degrees and Minutes) format to standard decimal degrees.
    """
    if not coord_str or not direction:
        return 0.0

    # Find the decimal point to isolate degrees from minutes
    dot_idx = coord_str.find('.')
    if dot_idx == -1:
        return 0.0

    # Minutes always occupy 2 digits to the left of the decimal point
    deg_len = dot_idx - 2
    degrees = float(coord_str[:deg_len])
    minutes = float(coord_str[deg_len:])

    decimal_degrees = degrees + (minutes / 60.0)

    # Invert sign for South or West coordinates
    if direction in ['S', 'W']:
        decimal_degrees = -decimal_degrees

    return decimal_degrees


def calculate_its_timestamp(date_str, time_str):
    """
    Calculates milliseconds elapsed since the C-ITS Epoch (January 1, 2004 00:00:00 UTC).
    """
    # Parse date (DDMMYY)
    day = int(date_str[0:2])
    month = int(date_str[2:4])
    year = int(date_str[4:6]) + 2000  # Map to 21st century

    # Parse time (HHMMSS.sss)
    hour = int(time_str[0:2])
    minute = int(time_str[2:4])
    second = int(time_str[4:6])
    
    # Extract milliseconds safely if present
    ms = int(time_str.split('.')[1]) if '.' in time_str else 0

    # Instantiate timezone-aware UTC datetime objects
    its_epoch = datetime(2004, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    current_time = datetime(year, month, day, hour, minute, second, ms * 1000, tzinfo=timezone.utc)

    # Calculate total elapsed delta in milliseconds
    delta = current_time - its_epoch
    return int(delta.total_seconds() * 1000)


def _derive_altitude_confidence(hdop):
    if hdop <= 0.5:
        return 'alt-000-50'
    if hdop <= 1.0:
        return 'alt-001-00'
    if hdop <= 2.0:
        return 'alt-002-00'
    if hdop <= 5.0:
        return 'alt-005-00'
    if hdop <= 10.0:
        return 'alt-010-00'
    return 'unavailable'


def _derive_position_confidence_ellipse(hdop, course_value):
    semi_axis = max(1, int(round(hdop * 100)))
    return {
        'semiMajorConfidence': semi_axis,
        'semiMinorConfidence': semi_axis,
        'semiMajorOrientation': course_value if course_value is not None else 3601
    }


def _derive_heading(course_over_ground):
    if course_over_ground is None:
        return {
            'headingValue': 3601,
            'headingConfidence': 127
        }

    return {
        'headingValue': int(round(course_over_ground * 10)),
        'headingConfidence': 127
    }


def _derive_speed(speed_knots):
    if speed_knots is None:
        return {
            'speedValue': 16383,
            'speedConfidence': 127
        }

    speed_mps = speed_knots * 0.5144444444444445
    return {
        'speedValue': int(round(speed_mps * 100)),
        'speedConfidence': 127
    }


def _parse_gga_sentence(nmea_line):
    parts = [p.strip() for p in nmea_line.split(',')]

    if not parts[0].endswith('GGA') or len(parts) < 10:
        return None

    fix_quality = parts[6]
    if fix_quality in ('', '0'):
        return None

    return {
        'raw_time': parts[1],
        'hdop': float(parts[8]) if parts[8] else 99.9,
        'altitude': {
            'altitudeValue': int(round((float(parts[9]) if parts[9] else 0.0) * 100)),
            'altitudeConfidence': _derive_altitude_confidence(float(parts[8]) if parts[8] else 99.9)
        }
    }


def _load_mock_locations():
    if not NMEA_FILE.exists():
        raise FileNotFoundError(f'Mock GPS source not found: {NMEA_FILE}')

    locations = []
    pending_gga = None

    with NMEA_FILE.open('r', encoding='utf-8') as nmea_file:
        for line in nmea_file:
            line = line.strip()
            if not line:
                continue

            if line.startswith('$GPGGA'):
                pending_gga = _parse_gga_sentence(line)
                continue

            parts = [p.strip() for p in line.split(',')]
            if not parts[0].endswith('RMC') or parts[2] != 'A':
                continue

            raw_time = parts[1]
            raw_lat = parts[3]
            lat_dir = parts[4]
            raw_lon = parts[5]
            lon_dir = parts[6]
            raw_speed = float(parts[7]) if parts[7] else None
            raw_date = parts[9]
            course = float(parts[8]) if parts[8] else 0.0

            lat_decimal = parse_nmea_to_decimal(raw_lat, lat_dir)
            lon_decimal = parse_nmea_to_decimal(raw_lon, lon_dir)
            hdop = pending_gga['hdop'] if pending_gga else 99.9

            locations.append({
                'timestampIts': calculate_its_timestamp(raw_date, raw_time),
                'latitude': int(round(lat_decimal * 10_000_000)),
                'longitude': int(round(lon_decimal * 10_000_000)),
                'heading': _derive_heading(course),
                'speed': _derive_speed(raw_speed),
                'positionConfidenceEllipse': _derive_position_confidence_ellipse(
                    hdop,
                    int(round(course * 10)) if course else 3601
                ),
                'altitude': pending_gga['altitude'] if pending_gga else {
                    'altitudeValue': 0,
                    'altitudeConfidence': 'unavailable'
                }
            })
            pending_gga = None

    return locations


def process_rmc_sentence(nmea_line):
    """
    Parses a single $GPRMC line and returns C-ITS compliant integers.
    """
    # Clean string and tokenize parameters
    parts = [p.strip() for p in nmea_line.split(',')]
    
    # Validate sentence header and receiver warning status flag ('A' = Active/Valid Fix)
    if not parts[0].endswith('RMC') or parts[2] != 'A':
        return None

    raw_time = parts[1]
    raw_lat  = parts[3]
    lat_dir  = parts[4]
    raw_lon  = parts[5]
    lon_dir  = parts[6]
    raw_date = parts[9]

    # 1. Transform raw coordinates to float decimal degrees
    lat_decimal = parse_nmea_to_decimal(raw_lat, lat_dir)
    lon_decimal = parse_nmea_to_decimal(raw_lon, lon_dir)

    # 2. Apply the 10^7 C-ITS scaling factor and cast to pure integer spaces
    cits_latitude  = int(round(lat_decimal * 10_000_000))
    cits_longitude = int(round(lon_decimal * 10_000_000))

    # 3. Calculate C-ITS absolute epoch timestamp
    cits_timestamp = calculate_its_timestamp(raw_date, raw_time)

    return {
        "timestampIts": cits_timestamp,
        "latitude": cits_latitude,
        "longitude": cits_longitude
    }

def MockGPS():
    global _mock_locations, _mock_location_index

    if _mock_locations is None:
        _mock_locations = _load_mock_locations()

    if not _mock_locations:
        raise ValueError('No mock GPS locations were parsed from output.nmea')

    location = _mock_locations[_mock_location_index]
    _mock_location_index = (_mock_location_index + 1) % len(_mock_locations)
    return location.copy()