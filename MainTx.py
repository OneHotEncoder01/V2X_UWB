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

    generationDeltaTime = get_generation_delta_time()

    gps = GenerateGPS.GetGPS()

    if gps['speed']['speedValue'] == 0:
        driveDirection = 'unavailable'
    else:
        driveDirection = 'forward'

    config = {'traffic_participant_type' : TrafficParticipantType, 'generation_delta_time' : generationDeltaTime, 'drive_direction' : driveDirection}

    with open('config1.json', 'w') as f:
        json.dump(config, f)

def get_generation_delta_time():
    system_time = int(time.time() * 1000)
    cits_ms = system_time - CITS_EPOCH_OFFSET
    return cits_ms % 65536
    
def GetGps(gps_queue):
    while True:
        gps_data = GenerateGPS.GetGPS()

        if gps_queue.full():
            gps_queue.get()

        gps_queue.put(gps_data)

def getCAM(
    gps_queue,
    msg_queue,
    participant_type,
    generation_delta_time
):
    while True:
        gps = gps_queue.get()

        generation_delta_time = get_generation_delta_time()

        encoded = GenerateCAM.GenerateCamMessage(
            generation_delta_time,
            gps,
            participant_type
        )

        if msg_queue.full():
            msg_queue.get()

        msg_queue.put(encoded)

def sendCAM(msq_queue):
    ser = serial.Serial("/dev/ttyUSB4", 115200)

    while True:
        msg = msg_queue.get()
        ser.write(msg)


if __name__ == "__main__":
    from multiprocessing import Process, Queue
    
    InitCAMConfig()
    with open("config1.json", "r") as f:
        config = json.load(f)

    participant_type = config["traffic_participant_type"]
    generation_delta_time = config["generation_delta_time"]

    gps_queue = Queue(maxsize=1)
    msg_queue = Queue(maxsize=1)

    gps_worker = Process(
        target=GetGps,
        args=(gps_queue,)
    )

    cam_worker = Process(
        target=getCAM,
        args=(
            gps_queue,
            msg_queue,
            participant_type,
            generation_delta_time
        )
    )

    tx_worker = Process(
        target=sendCAM,
        args=(msg_queue,)
    )

    gps_worker.start()
    cam_worker.start()
    tx_worker.start()