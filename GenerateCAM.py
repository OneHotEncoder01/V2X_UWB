import asn1tools as asn1
import time
import serial

import GenerateGPS


CITS_EPOCH_OFFSET = 1_072_915_200_000


def GenerateCamMessage():
    print(""" Choose a traffic participant  
    unknown         (0), 
    pedestrian      (1), 
    cyclist         (2), 
    moped           (3), 
    motorcycle      (4), 
    passengerCar    (5), 
    bus             (6), 
    lightTruck      (7), 
    heavyTruck      (8), 
    trailer         (9), 
    specialVehicle  (10), 
    tram            (11), 
    lightVruVehicle (12), 
    animal          (13),
    agricultural    (14), 
    infrastructure  (15)
    :  """)
    traffic_participant_type = int(input())

    system_time = int(time.time() * 1000)
    cits_ms = system_time - CITS_EPOCH_OFFSET
    generation_delta_time = cits_ms % 65536

    gps = GenerateGPS.MockGPS()
    standards = asn1.compile_files(['ETSI-ITS-CDD.asn', 'CAM-PDU-Descriptions.asn'], 'uper')

    if gps['speed']['speedValue'] == 0:
        drive_direction = 'unavailable'
    else:
        drive_direction = 'forward'

    cam_payload = {
        'generationDeltaTime': generation_delta_time,
        'camParameters': {
                'basicContainer': {
                    'stationType': traffic_participant_type,
                    'referencePosition': {
                        'latitude': gps['latitude'],
                        'longitude': gps['longitude'],
                        'positionConfidenceEllipse': gps['positionConfidenceEllipse'],
                        'altitude': gps['altitude']
                    }
                },
                'highFrequencyContainer': (
                    'basicVehicleContainerHighFrequency',
                    {
                        'heading': gps['heading'],
                        'speed': gps['speed'],
                        'driveDirection': drive_direction,
                        'vehicleLength': {
                            'vehicleLengthValue': 1023,
                            'vehicleLengthConfidenceIndication': 'unavailable'
                        },
                        'vehicleWidth': 62,
                        'longitudinalAcceleration': {
                            'longitudinalAccelerationValue': 161,
                            'longitudinalAccelerationConfidence': 102
                        },
                        'curvature': {
                            'curvatureValue': 1023,
                            'curvatureConfidence': 'unavailable'
                        },
                        'curvatureCalculationMode': 'unavailable',
                        'yawRate': {
                            'yawRateValue': 32767,
                            'yawRateConfidence': 'unavailable'
                        }
                    }
                )
            }
        }
    encoded = standards.encode('CoopAwareness', cam_payload)
    
    # Save to file and also return hex representation
    with open('encoded_cam.bin', 'wb') as f:
        f.write(encoded)
        
    print(f"Encoded Hex: {encoded.hex().upper()}")
    
    send_uwb = input("Send over UWB? (y/n) [y]: ").strip().lower()
    if send_uwb == '' or send_uwb == 'y':
        port = input("TX UWB Port [/dev/ttyUSB0]: ").strip()
        if not port:
            port = '/dev/ttyUSB0'
        try:
            ser = serial.Serial(port, 115200, timeout=1)
            print("[*] Waiting for UWB board to boot...")
            time.sleep(2)
            payload_len = len(encoded)
            if payload_len > 115:
                print(f"[!] Warning: Payload size {payload_len} may exceed standard UWB MTU limits.")
            sync_header = bytes([0xAA, 0xBB, payload_len])
            packet = sync_header + encoded
            ser.write(packet)
            ser.flush()
            print(f"[*] Dispatched {payload_len} CAM bytes to UWB Board on {port}.")
            ser.close()
        except Exception as e:
            print(f"[-] Failed to send to UWB board: {e}")
    
    # Return hex string for display and manual testing
    return encoded.hex()

if __name__ == "__main__":
    GenerateCamMessage()