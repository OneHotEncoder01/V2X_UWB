from functools import lru_cache
from pathlib import Path

import asn1tools as asn1


_ASN_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def _compile_standards(ETSI, CAM, MSG_Type):
    return asn1.compile_files([ETSI, CAM], MSG_Type)

def _cam_payload(generation_delta_time, gps, traffic_participant_type):
    generation_delta_time = int(generation_delta_time) % 65536

    if gps['speed']['speedValue'] == 0:
        drive_direction = 'unavailable'
    else:
        drive_direction = 'forward'

    return {
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


def GenerateCamMessage(generation_delta_time,
                       gps,
                       traffic_participant_type=2,
                       ETSI=str(_ASN_DIR / 'ETSI-ITS-CDD.asn'),
                       CAM=str(_ASN_DIR / 'CAM-PDU-Descriptions.asn'),
                       MSG_Type='uper'):

    standards = _compile_standards(ETSI, CAM, MSG_Type)
    cam_payload = _cam_payload(
        generation_delta_time,
        gps,
        traffic_participant_type,
    )
    return standards.encode('CoopAwareness', cam_payload)


def GenerateWrappedCamMessage(generation_delta_time,
                              gps,
                              station_id,
                              traffic_participant_type=2,
                              protocol_version=2,
                              message_id=2,
                              ETSI=str(_ASN_DIR / 'ETSI-ITS-CDD.asn'),
                              CAM=str(_ASN_DIR / 'CAM-PDU-Descriptions.asn'),
                              MSG_Type='uper'):
    """Encode a full CAM with an ITS-PDU header.

    The normal transmitter uses the smaller CoopAwareness payload. The
    over-the-air loss test uses the wrapper so stationId can carry a test
    sequence number that survives the UWB link and is decoded by the RX side.
    """

    standards = _compile_standards(ETSI, CAM, MSG_Type)
    station_id = int(station_id)
    if station_id < 0 or station_id > 4_294_967_295:
        raise ValueError("station_id must fit the ETSI StationId uint32 range")

    wrapped_cam = {
        'header': {
            'protocolVersion': int(protocol_version),
            'messageId': int(message_id),
            'stationId': station_id,
        },
        'cam': _cam_payload(
            generation_delta_time,
            gps,
            traffic_participant_type,
        ),
    }
    return standards.encode('CAM', wrapped_cam)
