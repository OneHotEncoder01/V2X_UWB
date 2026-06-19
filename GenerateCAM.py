import asn1tools as asn1
from functools import lru_cache


@lru_cache(maxsize=None)
def _compile_standards(ETSI, CAM, MSG_Type):
    return asn1.compile_files([ETSI, CAM], MSG_Type)

def GenerateCamMessage(generation_delta_time,
                       gps,
                       traffic_participant_type = 2,
                       ETSI = 'ETSI-ITS-CDD.asn', 
                       CAM = 'CAM-PDU-Descriptions.asn', 
                       MSG_Type = 'uper'):

    standards = _compile_standards(ETSI, CAM, MSG_Type)
    generation_delta_time = int(generation_delta_time) % 65536

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
    return standards.encode('CoopAwareness', cam_payload)
