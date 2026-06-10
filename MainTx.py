import GenerateCAM
import GenerateGPS
import time
import serial
import GenerateGPS
import json
import os

CITS_EPOCH_OFFSET = 1_072_915_200_000
generationDeltaTime = 0

def InitCAMConfig():
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
    TrafficParticipantType = int(input())

    system_time = int(time.time() * 1000)
    cits_ms = system_time - CITS_EPOCH_OFFSET
    generationDeltaTime = cits_ms % 65536

    gps = GenerateGPS.MockGPS()

    if gps['speed']['speedValue'] == 0:
        driveDirection = 'unavailable'
    else:
        driveDirection = 'forward'

    config = {'traffic_participant_type' : TrafficParticipantType, 'generation_delta_time' : generationDeltaTime, 'drive_direction' : driveDirection}

    with open('config1.json', 'w') as f:
        json.dump(config, f)
    
    
def GetGps():
    return GenerateGPS.MockGPS()

def getCAM(gps):
    if os.path.isfile("config1.json"):
        with open('config1.json', 'r') as f:
            config = json.load(f)
    else:  
        InitCAMConfig()
      

    encoded = GenerateCAM.GenerateCamMessage(config['generation_delta_time'], 
                                            gps,  
                                            config['traffic_participant_type'])
    return encoded

def sendUWB(encoded):
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

InitCAMConfig()
gps = GetGps()
print()
print(getCAM(gps))