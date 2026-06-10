import serial
import asn1tools


ser = serial.Serial('/dev/ttyUSB0', 115200, timeout=5)


template = asn1tools.compile_files(['CAM-PDU-Descriptions.asn', 'ETSI-ITS-CDD.asn'], 'uper')

while True:
    # Read until "OK" response
    data = ser.read_until(b'\r\n')
    decoded = template.decode('CoopAwareness', data)
    print(decoded)