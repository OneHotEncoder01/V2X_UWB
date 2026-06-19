import asn1tools


LATITUDE_UNAVAILABLE = 900_000_001
LONGITUDE_UNAVAILABLE = 1_800_000_001
ALTITUDE_UNAVAILABLE = 800_001
SPEED_UNAVAILABLE = 16_383
HEADING_UNAVAILABLE = 3_601


def compile_cam_template():
    return asn1tools.compile_files(
        ["CAM-PDU-Descriptions.asn", "ETSI-ITS-CDD.asn"],
        "uper",
    )


def decode_cam_payload(template, payload):
    try:
        return template.decode("CoopAwareness", payload), "CoopAwareness"
    except asn1tools.DecodeError as coop_error:
        try:
            wrapped = template.decode("CAM", payload)
        except asn1tools.DecodeError:
            raise coop_error

        return wrapped["cam"], "CAM"


def looks_like_hex(line):
    if len(line) % 2 != 0:
        return False

    try:
        line.decode("ascii")
    except UnicodeDecodeError:
        return False

    return all(byte in b"0123456789abcdefABCDEF" for byte in line)


def serial_payload(line, encoding="auto"):
    line = line.strip()
    if encoding == "binary":
        return line

    if encoding == "hex" or looks_like_hex(line):
        return bytes.fromhex(line.decode("ascii"))

    return line


def payload_candidates(line, encoding="auto"):
    line = line.strip()
    candidates = []

    def add(payload, label):
        if payload and all(existing != payload for existing, _ in candidates):
            candidates.append((payload, label))

    if encoding in ("auto", "binary"):
        add(line, "binary")

    if encoding in ("auto", "hex") and looks_like_hex(line):
        decoded = bytes.fromhex(line.decode("ascii"))
        add(decoded, "hex")

        if looks_like_hex(decoded):
            add(bytes.fromhex(decoded.decode("ascii")), "hex-ascii")

    return candidates


def decode_serial_line(template, line, encoding="auto"):
    errors = []

    for payload, payload_encoding in payload_candidates(line, encoding):
        try:
            decoded, asn_type = decode_cam_payload(template, payload)
        except asn1tools.DecodeError as exc:
            errors.append(f"{payload_encoding}: {exc}")
            continue

        return payload, decoded, payload_encoding, asn_type

    if errors:
        raise asn1tools.DecodeError("; ".join(errors))

    raise ValueError("line is empty or does not match the selected encoding")


def _scaled_coordinate(value, unavailable, scale=10_000_000):
    if value == unavailable:
        return None
    return value / scale


def _altitude(value):
    if value == ALTITUDE_UNAVAILABLE:
        return None
    return value / 100


def _speed(value):
    if value == SPEED_UNAVAILABLE:
        return None
    return value / 100


def _heading(value):
    if value == HEADING_UNAVAILABLE:
        return None
    return value / 10


def flatten_cam(decoded):
    params = decoded["camParameters"]
    basic = params["basicContainer"]
    ref = basic["referencePosition"]
    container_name, high_frequency = params["highFrequencyContainer"]

    return {
        "generation_delta_time": decoded["generationDeltaTime"],
        "station_type": basic.get("stationType"),
        "latitude": _scaled_coordinate(ref.get("latitude"), LATITUDE_UNAVAILABLE),
        "longitude": _scaled_coordinate(ref.get("longitude"), LONGITUDE_UNAVAILABLE),
        "altitude_m": _altitude(ref.get("altitude", {}).get("altitudeValue")),
        "speed_mps": _speed(high_frequency.get("speed", {}).get("speedValue")),
        "heading_deg": _heading(high_frequency.get("heading", {}).get("headingValue")),
        "drive_direction": high_frequency.get("driveDirection", ""),
        "container": container_name,
    }
