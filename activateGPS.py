"""
Activate the GPS receiver on a SIM7600-series 4G/GPS HAT via AT commands.

Tested on the Waveshare SIM7600E-H 4G HAT for Raspberry Pi.
For other GPS modules that output NMEA directly (no AT command needed),
you can replace the body of ensure_gps_on with a no-op `pass`.
"""

import time
import serial


def ensure_gps_on(port="/dev/ttyUSB2", baud=115200, timeout=5):
    """Send AT+CGPS=1 to enable the GPS receiver, then return.

    Failures are non-fatal: if the module is already running or unreachable,
    we log and continue so MainTx.py can still attempt to read NMEA sentences.
    """
    try:
        with serial.Serial(port, baud, timeout=timeout) as modem:
            modem.write(b"AT+CGPS=1\r\n")
            time.sleep(0.5)
            resp = modem.read(modem.in_waiting or 1)
            if resp:
                print(f"[GPS HAT] {resp.decode('ascii', errors='replace').strip()}", flush=True)
    except serial.SerialException as exc:
        print(f"[GPS HAT] Could not reach modem on {port}: {exc}", flush=True)
        print("[GPS HAT] Continuing — GPS may already be active.", flush=True)
