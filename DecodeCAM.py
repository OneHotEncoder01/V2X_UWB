import asn1tools as asn1
import sys
import os
import serial

def listen_for_uwb_cam(port='/dev/ttyUSB1'):
    try:
        with serial.Serial(port, baudrate=115200, timeout=0.5) as ser:
            print(f"[*] Connected to UWB Receiver Node on {port}")
            print("[*] Listening for incoming over-the-air CAM messages...")
            while True:
                byte1 = ser.read(1)
                if not byte1 or byte1 != b'\xaa':
                    continue
                byte2 = ser.read(1)
                if not byte2 or byte2 != b'\xbb':
                    continue
                len_byte = ser.read(1)
                if not len_byte:
                    continue
                payload_len = int.from_bytes(len_byte, byteorder='big')
                cam_payload = ser.read(payload_len)
                if len(cam_payload) != payload_len:
                    print("[!] Warning: Fragmented or incomplete packet frame read.")
                    continue
                
                print("\n--- Over-The-Air CAM Packet Captured ---")
                print(f"Payload Size: {payload_len} bytes")
                return cam_payload
    except Exception as e:
        print(f"[-] Serial error: {e}")
        return None

use_uwb = input("Listen for message over UWB? (y/n) [y]: ").strip().lower()
if use_uwb == '' or use_uwb == 'y':
    port = input("RX UWB Port [/dev/ttyUSB1]: ").strip()
    if not port:
        port = '/dev/ttyUSB1'
    msg_bytes = listen_for_uwb_cam(port)
    if not msg_bytes:
        sys.exit(1)
else:
    # Check if binary file exists from last generation
    if os.path.exists('encoded_cam.bin'):
        print("Found encoded_cam.bin from previous generation")
        use_file = input("Load from file? (y/n) [default: y]: ").strip().lower()
        if use_file != 'n':
            with open('encoded_cam.bin', 'rb') as f:
                msg_bytes = f.read()
            print(f"Loaded {len(msg_bytes)} bytes from file")
        else:
            # Read hex from user
            user_input = input("Enter the message (hex string): ").strip()
            if not user_input:
                print("No input provided")
                sys.exit(1)
            msg_bytes = bytes.fromhex(user_input)
    else:
        # Accept hex string input
        user_input = input("Enter the message (hex string): ").strip()
        if not user_input:
            print("No input provided")
            sys.exit(1)
        msg_bytes = bytes.fromhex(user_input)

try:
    decoded = template.decode('CoopAwareness', msg_bytes)
    print("\n=== Decoded CAM Message ===")
    print(decoded)
except ValueError as e:
    print(f"Error: Invalid hex string - {e}")
except Exception as e:
    print(f"Error decoding message: {e}")
    if 'msg_bytes' in locals():
        print(f"Message length: {len(msg_bytes)} bytes ({len(msg_bytes)*8} bits)")