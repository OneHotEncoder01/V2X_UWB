import os
from pathlib import Path

from serial.tools import list_ports


def _default_port(windows_port, linux_port):
    return windows_port if os.name == "nt" else linux_port


def _port_from_env(env_name, default):
    value = os.environ.get(env_name)
    if value:
        return value
    return default


def tx_port():
    """Return the TX ESP32 serial port.

    Override with V2X_TX_PORT when the Pi enumerates the board differently.
    """

    return _port_from_env("V2X_TX_PORT", _default_port("COM4", "/dev/ttyUSB4"))


def rx_port():
    """Return the RX ESP32 serial port.

    Override with V2X_RX_PORT when the laptop enumerates the board differently.
    """

    return _port_from_env("V2X_RX_PORT", _default_port("COM3", "/dev/ttyUSB0"))


def describe_ports():
    rows = []
    for port in sorted(list_ports.comports(), key=lambda item: item.device):
        exists = Path(port.device).exists() if os.name != "nt" else True
        rows.append(
            {
                "device": port.device,
                "description": port.description,
                "hwid": port.hwid,
                "exists": exists,
            }
        )
    return rows


def ports_summary():
    ports = describe_ports()
    if not ports:
        return "none"
    return ", ".join(
        f"{port['device']} ({port['description']})" for port in ports
    )
