import serial
import time

# Connect to your microcontroller's live USB port
ser = serial.Serial('/dev/ttyACM0', 115200, timeout=1)

def broadcast_cam_over_uwb(raw_cam_bytes):
    payload_len = len(raw_cam_bytes)
    
    if payload_len > 115: # 802.15.4 standard frame ceiling precaution
        print(f"[!] Warning: Payload size {payload_len} may exceed standard UWB MTU limits.")
        
    # Assemble framing packet: [Sync1, Sync2, Length, Raw Payload...]
    sync_header = bytes([0xAA, 0xBB, payload_len])
    packet = sync_header + raw_cam_bytes
    
    # Push to USB serial pipeline
    ser.write(packet)
    ser.flush()

# Example Execution Loop
while True:
    # Replace this with your actual ASN.1 CAM generation byte generation routine
    mock_cam_bytes = bytes([0x01, 0x02, 0x03, 0x04, 0x05]) 
    
    broadcast_cam_over_uwb(mock_cam_bytes)
    print(f"[*] Dispatched {len(mock_cam_bytes)} CAM bytes to UWB Board.")
    
    time.sleep(1.0) # Match your C-ITS generation period (e.g., 1 Hz)