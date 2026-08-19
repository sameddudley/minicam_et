"""
MLX90640 Thermal Camera Visualizer
-----------------------------------
Reads comma-separated temperature values (768 per line, one line per frame)
from the ESP32 over serial and displays them as a live heatmap.

Pairs with the Arduino sketch based on Example2_OutputToProcessing.ino,
printing all 768 pixel values as CSV once per frame.

Install dependencies first:
    pip install pyserial matplotlib numpy
"""

import serial
import numpy as np
import matplotlib.pyplot as plt
import time
import pickle

# ----- Settings you may need to change -----
SERIAL_PORT = "COM3"      # Windows e.g. "COM5"; Mac/Linux e.g. "/dev/ttyUSB0" or "/dev/cu.usbserial-XXXX"
BAUD_RATE = 115200        # Must match Serial.begin() in the Arduino sketch
FRAME_WIDTH = 32
FRAME_HEIGHT = 24

SAVE_DATA = False                       # Set False if you don't want to log frames at all
SAVE_PATH = r"C:\Users\samed\OneDrive\Documents\postdoc\code\thermal_camera_project/thermal_log.pkl"          # Where the recorded frames get written
AUTOSAVE_EVERY_N_FRAMES = 30           # Periodically save to disk so a crash doesn't lose everything
# ---------------------------------------------

def save_to_disk(frames_dict, path):
    """Dump the frames dictionary to disk with pickle."""
    with open(path, "wb") as f:
        pickle.dump(frames_dict, f)


def main():
    ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)
    print(f"Connected to {SERIAL_PORT} at {BAUD_RATE} baud. Waiting for data...")

    # Dictionary that holds every captured frame, keyed by timestamp.
    # frames["2026-08-13 10:15:32.104"] -> 24x32 numpy array of temperatures (C)
    frames = {}

    # Set up the plot
    plt.ion()
    fig, ax = plt.subplots()
    dummy = np.zeros((FRAME_HEIGHT, FRAME_WIDTH))
    img = ax.imshow(dummy, cmap="inferno", interpolation= None)
    cbar = fig.colorbar(img, ax=ax, label="Temperature (C)")
    ax.set_title("MLX90640 Thermal View")

    try:
        while True:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if not line:
                continue  # timed out waiting, try again

            values = line.split(",")
            values = [v for v in values if v != ""]  # drop trailing empty entries

            if len(values) != FRAME_WIDTH * FRAME_HEIGHT:
                # Skip malformed/partial lines (e.g. startup messages, dropped bytes)
                print(f"Skipping line: got {len(values)} values, expected {FRAME_WIDTH * FRAME_HEIGHT}")
                continue

            try:
                frame = np.array(values, dtype=float).reshape((FRAME_HEIGHT, FRAME_WIDTH))
            except ValueError:
                print("Skipping line: could not parse floats")
                continue

            # ---- Save this frame ----
            if SAVE_DATA:
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S.") + f"{int(time.time() * 1000) % 1000:03d}"
                frames[timestamp] = frame

                if len(frames) % AUTOSAVE_EVERY_N_FRAMES == 0:
                    save_to_disk(frames, SAVE_PATH)
                    print(f"Autosaved {len(frames)} frames to {SAVE_PATH}")

            # ---- Display this frame ----
            img.set_data(frame)
            img.set_clim(vmin=frame.min(), vmax=frame.max())  # auto-scale color range each frame
            ax.set_title(f"MLX90640 Thermal View  (min {frame.min():.1f}C / max {frame.max():.1f}C)")
            fig.canvas.draw()
            fig.canvas.flush_events()

    except KeyboardInterrupt:
        print("Stopped by user.")
    finally:
        ser.close()
        if SAVE_DATA and frames:
            save_to_disk(frames, SAVE_PATH)
            print(f"Saved {len(frames)} total frames to {SAVE_PATH}")

if __name__ == "__main__":
    main()