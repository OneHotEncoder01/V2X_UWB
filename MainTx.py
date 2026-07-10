import GenerateCAM
import GenerateGPS
import time
import serial
import json
import os
import sys

CITS_EPOCH_OFFSET = 1_072_915_200_000
TX_SERIAL_PORT = "/dev/ttyUSB4"   # UWB TX board — update if your port differs

def InitCAMConfig():
    if os.path.exists('config1.json'):
        print("Config file found. Loading existing config.", flush=True)
        return

    print("No config found. Generating default config (passengerCar)...", flush=True)
    # Drive direction is set to unavailable here; the GPS worker will supply
    # real values once a fix is obtained. Avoids blocking at startup.
    config = {
        'traffic_participant_type': 5,
        'generation_delta_time': get_generation_delta_time(),
        'drive_direction': 'unavailable',
    }
    with open('config1.json', 'w') as f:
        json.dump(config, f)

def get_generation_delta_time():
    system_time = int(time.time() * 1000)
    cits_ms = system_time - CITS_EPOCH_OFFSET
    return cits_ms % 65536
    
def GetGps(gps_queue):
    """Reads GPS fixes via stream_gps(), which keeps /dev/serial0 open continuously.
    Logs a 'waiting' message every 15 s until the first satellite fix arrives."""
    print("[Worker] GPS process started.", flush=True)
    last_log = time.monotonic()

    for fix in GenerateGPS.stream_gps():
        if fix is None:
            # stream_gps yields None on each 1-second read timeout (no NMEA yet
            # or GPS module not ready). Throttle the log so it is not noisy.
            now = time.monotonic()
            if now - last_log >= 15:
                print(f"[GPS] Waiting for satellite fix on {GenerateGPS.SERIAL_PORT} …", flush=True)
                last_log = now
            continue

        last_log = time.monotonic()
        print(f"[GPS] Fix: lat={fix['latitude']}, lon={fix['longitude']}", flush=True)

        if gps_queue.full():
            gps_queue.get()
        gps_queue.put(fix)

def getCAM(gps_queue, msg_queue, participant_type, generation_delta_time, heartbeat=None):
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

        if heartbeat is not None:
            heartbeat.value = time.time()

        # Debugging: Print when a CAM message is generated and queued for sending
        print(f"[CAM] Generated and queued message (Size: {len(encoded)} bytes).", flush=True)

def sendCAM(msg_queue, heartbeat=None):
    print("[Worker] TX Sender process started. Opening serial port...", flush=True)
    try:
        ser = serial.Serial(TX_SERIAL_PORT, 115200, timeout=0.1)
        time.sleep(2)
        print(f"[TX] Serial port {TX_SERIAL_PORT} opened successfully.", flush=True)
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

        if heartbeat is not None:
            heartbeat.value = time.time()

        # Debugging: Print exactly when bytes are pushed to the serial port
        print(f"[TX] >>> Sent {len(msg)} CAM bytes to transmitter as hex.", flush=True)

if __name__ == "__main__":
    import activateGPS
    from multiprocessing import Process, Queue, Value

    print("=== Starting CAM Broadcasting System ===", flush=True)

    print("Activating GPS module...", flush=True)
    activateGPS.ensure_gps_on("/dev/ttyUSB2", 115200)
    # Wait until the GPS HAT is outputting NMEA on /dev/serial0 rather than
    # sleeping a fixed amount. Handles slow module init after a cold boot.
    GenerateGPS.wait_for_uart(timeout_s=60)
    print("GPS activation step complete.", flush=True)

    print("Initializing Config...", flush=True)
    InitCAMConfig()
    
    with open("config1.json", "r") as f:
        config = json.load(f)

    participant_type = config["traffic_participant_type"]
    generation_delta_time = config["generation_delta_time"]

    gps_queue = Queue(maxsize=1)
    msg_queue = Queue(maxsize=1)

    # Heartbeats let the watchdog below detect a *stalled* worker, not just a
    # crashed one. Python's fork-based multiprocessing has a known intermittent
    # race (lock/queue state can be inherited mid-operation at fork time) that
    # occasionally deadlocks the CAM or TX worker after producing exactly one
    # message, with no exception and no crash -- is_alive() alone can't see
    # this. See TECHNICAL.md ("Stresstest: Known Issues and Fixes") for the
    # full writeup; a retry via systemd's Restart=on-failure reliably recovers.
    cam_heartbeat = Value('d', 0.0)
    tx_heartbeat = Value('d', 0.0)

    print("Starting worker processes...", flush=True)
    gps_worker = Process(target=GetGps, args=(gps_queue,))
    cam_worker = Process(
        target=getCAM,
        args=(gps_queue, msg_queue, participant_type, generation_delta_time, cam_heartbeat)
    )
    tx_worker = Process(target=sendCAM, args=(msg_queue, tx_heartbeat))

    gps_worker.start()
    cam_worker.start()
    tx_worker.start()

    print("All workers started. Running in background.", flush=True)

    STALL_TIMEOUT_S = 15        # no progress since last heartbeat -> stalled
    NO_PROGRESS_TIMEOUT_S = 90  # generous allowance for first GPS fix on cold start
    loop_start = time.monotonic()
    problem = False

    # Keep the main process alive and monitor workers
    try:
        while True:
            time.sleep(1)
            # If any worker dies, print an error and exit so systemd can restart it
            if not gps_worker.is_alive():
                print("ERROR: GPS worker process crashed!", flush=True)
                problem = True
                break
            if not cam_worker.is_alive():
                print("ERROR: CAM worker process crashed!", flush=True)
                problem = True
                break
            if not tx_worker.is_alive():
                print("ERROR: TX worker process crashed!", flush=True)
                problem = True
                break

            now = time.time()
            elapsed = time.monotonic() - loop_start
            cam_stalled = (cam_heartbeat.value and now - cam_heartbeat.value > STALL_TIMEOUT_S) or \
                          (not cam_heartbeat.value and elapsed > NO_PROGRESS_TIMEOUT_S)
            tx_stalled = (tx_heartbeat.value and now - tx_heartbeat.value > STALL_TIMEOUT_S) or \
                         (not tx_heartbeat.value and elapsed > NO_PROGRESS_TIMEOUT_S)
            if cam_stalled:
                print(f"ERROR: CAM worker stalled (no progress for over {STALL_TIMEOUT_S}s). "
                      f"Restarting.", flush=True)
                problem = True
                break
            if tx_stalled:
                print(f"ERROR: TX worker stalled (no progress for over {STALL_TIMEOUT_S}s). "
                      f"Restarting.", flush=True)
                problem = True
                break
    except KeyboardInterrupt:
        print("Stopping processes...", flush=True)
    finally:
        gps_worker.terminate()
        cam_worker.terminate()
        tx_worker.terminate()
        print("System stopped.", flush=True)

    if problem:
        sys.exit(1)

