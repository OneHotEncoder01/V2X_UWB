import GenerateCAM
import GenerateGPS
import time
import serial
import json
import os
import activateGPS

CITS_EPOCH_OFFSET = 1_072_915_200_000

def InitCAMConfig():
    if os.path.exists('config1.json'):
        print("Config file found. Loading existing config.", flush=True)
        return

    print("No config found. Generating default config (passengerCar)...", flush=True)
    TrafficParticipantType = 5 

    generationDeltaTime = get_generation_delta_time()
    gps = GenerateGPS.GetGPS()

    if gps['speed']['speedValue'] == 0:
        driveDirection = 'unavailable'
    else:
        driveDirection = 'forward'

    config = {
        'traffic_participant_type': TrafficParticipantType, 
        'generation_delta_time': generationDeltaTime, 
        'drive_direction': driveDirection
    }

    with open('config1.json', 'w') as f:
        json.dump(config, f)

def get_generation_delta_time():
    system_time = int(time.time() * 1000)
    cits_ms = system_time - CITS_EPOCH_OFFSET
    return cits_ms % 65536
    
def GetGps(gps_queue):
    print("[Worker] GPS process started.", flush=True)
    while True:
        gps_data = GenerateGPS.GetGPS()

        # Debugging: Print when GPS data is successfully acquired
        print(f"[GPS] Acquired data: Lat={gps_data.get('latitude')}, Lon={gps_data.get('longitude')}", flush=True)

        if gps_queue.full():
            gps_queue.get()

        gps_queue.put(gps_data)

def getCAM(gps_queue, msg_queue, participant_type, generation_delta_time):
    print("[Worker] CAM generator process started.", flush=True)
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
        
        # Debugging: Print when a CAM message is generated and queued for sending
        print(f"[CAM] Generated and queued message (Size: {len(encoded)} bytes).", flush=True)

def sendCAM(msg_queue):
    print("[Worker] TX Sender process started. Opening serial port...", flush=True)
    try:
        ser = serial.Serial("/dev/ttyUSB4", 115200, timeout=0.1)
        time.sleep(2)
        print("[TX] Serial port /dev/ttyUSB4 opened successfully.", flush=True)
    except Exception as e:
        print(f"[TX] FATAL: Could not open serial port: {e}", flush=True)
        return

    while True:
        msg = msg_queue.get()
        ser.write(msg.hex().encode("ascii") + b"\n")
        ser.flush()

        response = ser.read(ser.in_waiting or 1)
        if response:
            print(f"[TX Board] {response!r}", flush=True)
        
        # Debugging: Print exactly when bytes are pushed to the serial port
        print(f"[TX] >>> Sent {len(msg)} CAM bytes to transmitter as hex.", flush=True)

if __name__ == "__main__":
    from multiprocessing import Process, Queue
    
    print("=== Starting CAM Broadcasting System ===", flush=True)
    
    print("Activating GPS module...", flush=True)
    activateGPS.ensure_gps_on("/dev/ttyUSB2", 115200)
    time.sleep(2) # Give the GPS a moment to initialize
    print("GPS activation step complete.", flush=True)

    print("Initializing Config...", flush=True)
    InitCAMConfig()
    
    with open("config1.json", "r") as f:
        config = json.load(f)

    participant_type = config["traffic_participant_type"]
    generation_delta_time = config["generation_delta_time"]

    gps_queue = Queue(maxsize=1)
    msg_queue = Queue(maxsize=1)

    print("Starting worker processes...", flush=True)
    gps_worker = Process(target=GetGps, args=(gps_queue,))
    cam_worker = Process(
        target=getCAM, 
        args=(gps_queue, msg_queue, participant_type, generation_delta_time)
    )
    tx_worker = Process(target=sendCAM, args=(msg_queue,))

    gps_worker.start()
    cam_worker.start()
    tx_worker.start()

    print("All workers started. Running in background.", flush=True)

    # Keep the main process alive and monitor workers
    try:
        while True:
            time.sleep(1)
            # If any worker dies, print an error and exit so systemd can restart it
            if not gps_worker.is_alive():
                print("ERROR: GPS worker process crashed!", flush=True)
                break
            if not cam_worker.is_alive():
                print("ERROR: CAM worker process crashed!", flush=True)
                break
            if not tx_worker.is_alive():
                print("ERROR: TX worker process crashed!", flush=True)
                break
    except KeyboardInterrupt:
        print("Stopping processes...", flush=True)
    finally:
        gps_worker.terminate()
        cam_worker.terminate()
        tx_worker.terminate()
        print("System stopped.", flush=True)
