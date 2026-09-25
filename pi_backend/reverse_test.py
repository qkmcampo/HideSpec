"""
reverse_test.py

Standalone conveyor reverse test.

IMPORTANT:
1. STOP app5.py first so only this script owns the Arduino serial port.
2. Run: python3 reverse_test.py
3. Watch both the terminal and the conveyor.
"""

import glob
import time
import serial

BAUD = 9600
REVERSE_MS = 3000


def find_arduino():
    ports = glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*")

    if not ports:
        raise RuntimeError(
            "No Arduino serial port found under /dev/ttyACM* or /dev/ttyUSB*"
        )

    print("Available serial ports:")
    for port in ports:
        print("  ", port)

    return ports[0]


def read_for(arduino, seconds):
    deadline = time.monotonic() + seconds

    while time.monotonic() < deadline:
        while arduino.in_waiting:
            line = (
                arduino.readline()
                .decode(errors="replace")
                .strip()
            )
            if line:
                print("[ARDUINO]", line)

        time.sleep(0.01)


def command(arduino, text, wait=1.0):
    print("[PI] ->", text)
    arduino.write((text + "\n").encode())
    arduino.flush()
    read_for(arduino, wait)


def main():
    port = find_arduino()

    print(f"\nOpening {port} at {BAUD} baud...")
    arduino = serial.Serial(
        port,
        BAUD,
        timeout=0.05,
    )

    print("Waiting for Arduino startup...")
    time.sleep(2.5)
    read_for(arduino, 1.0)

    try:
        print("\n=== STEP 1: STOP ===")
        command(arduino, "STOP", 1.0)

        print("\n=== STEP 2: CLEAR RETURN LATCH ===")
        command(arduino, "RESET_RETURN", 1.0)

        print(
            f"\n=== STEP 3: REVERSE FOR {REVERSE_MS/1000:.0f} SECONDS ==="
        )
        print(
            "WATCH THE CONVEYOR NOW. "
            "It should physically move in the opposite direction."
        )

        print("[PI] ->", f"REVERSE:{REVERSE_MS}")
        arduino.write((f"REVERSE:{REVERSE_MS}\n").encode())
        arduino.flush()

        read_for(
            arduino,
            REVERSE_MS / 1000.0 + 2.0,
        )

        print("\n=== STEP 4: STOP ===")
        command(arduino, "STOP", 1.0)

        print("\n=== STEP 5: CLEAR LATCH AGAIN ===")
        command(arduino, "RESET_RETURN", 1.0)

        print("\nTest finished.")
        print(
            "Expected replies: STOPPED, RETURN:READY, "
            "REVERSE:STARTED, REVERSE:DONE."
        )

    finally:
        try:
            arduino.write(b"STOP\n")
            arduino.flush()
        except Exception:
            pass

        arduino.close()


if __name__ == "__main__":
    main()
