import asn1tools as asn1
import time

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
    return encoded

print(GenerateCamMessage())