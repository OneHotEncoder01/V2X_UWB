# UWB CAM Communication Test Setup

Testing

## 1. Flash the ESP32 Boards
1. Connect both ESP32 UWB boards to your computer.
2. Note their serial ports (e.g., `/dev/ttyUSB0` for TX, `/dev/ttyUSB1` for RX).
3. Use `arduino-cli` (or the Arduino IDE) to flash:
   - `UWB_Boards/simple_tx.ino` to the **Transmitter** board.
   - `UWB_Boards/simple_rx.ino` to the **Receiver** board.

## 2. Start the Receiver
1. Open a terminal and navigate to the `V2X_UWB` folder.
2. Run the decoder script:
   ```bash
   python3 DecodeCAM.py
   ```
3. Type `y` to listen over UWB, and enter your Receiver board's port (e.g., `/dev/ttyUSB0`). Leave it running so it can listen for incoming messages.

## 3. Generate and Transmit
1. Open a **second terminal** and run the generator script:
   ```bash
   python3 GenerateCAM.py
   ```
2. Follow the prompt to choose a traffic participant type.
3. When prompted to send over UWB, type `y` and provide your Transmitter board's port (e.g., `/dev/ttyACM0`).
4. The script will wait 2 seconds for the ESP32 to boot and then fire the CAM payload over the air!

## 4. Verify
Switch back to your Receiver terminal. You should see the `Over-The-Air CAM Packet Captured` alert, followed by the successfully decoded ASN.1 CAM dictionary.
