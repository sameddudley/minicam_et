"""
Decodes thermal_log.bin (written by thermal_sensing_et.ino) into either:
  - a flat CSV (one row per frame, 768 pixel columns) - handy for a quick
    look in Excel, or
  - a .npz file containing a proper 3D array of shape (num_frames, 24, 32)
    plus a matching timestamps array - the better choice for anything
    image-like: plotting, video, CNNs, etc.

# CHANGED: this version matches the RTC-based sketch, where each record's
# timestamp is a 4-byte Unix epoch second (real date/time) + a 2-byte
# sub-second ms offset, instead of the old single 4-byte "ms since boot".
# Decoded timestamps are now real epoch milliseconds (int64), not boot-relative.
# If you still have older .bin files recorded BEFORE the RTC was added, set
# LEGACY_BOOT_MS_FORMAT = True below to decode those instead.

The MLX90640 is a 32 (wide) x 24 (tall) sensor. Pixel index i in the flat
array maps to row = i // 32, col = i % 32 (row-major). Whether "row 0" is
physically the top or bottom of the sensor as mounted depends on your
library/orientation - verify once empirically (point a heat source at one
corner and see where it lands in the reshaped array) if that matters for
your use case.

Handles files that are missing the THM1 header (e.g. from a card that was
hot-inserted mid-run) by falling back to the default format.


"""




import struct
import sys
import numpy as np
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
from datetime import datetime, timezone  # CHANGED: for formatting real timestamps in the animation title


HEADER_FMT = "<IHH"          # magic(uint32), numPixels(uint16), scale(uint16)
HEADER_SIZE = struct.calcsize(HEADER_FMT)
MAGIC = 0x54484D31            # "THM1"

DEFAULT_NUM_PIXELS = 768
DEFAULT_SCALE = 100
SENSOR_WIDTH = 32
SENSOR_HEIGHT = 24

# CHANGED: set this True only if decoding a .bin recorded with the OLD
# (pre-RTC) sketch, where the timestamp was a single 4-byte "ms since boot".
LEGACY_BOOT_MS_FORMAT = False


in_path = r"D:\thermal_log.bin"
out_path = r"D:\rtc_test.npz"

# ----- Settings you may need to change for visualization and saving video -----
NPZ_PATH = r"D:\thermal_log.npz" # Path to the decoded .npz file
FPS = 3                          # Playback speed (matches the 1 Hz capture rate)
SAVE_VIDEO = True                # Set True to save a file instead of/in addition to displaying
SAVE_PATH = r"D:\rtc_test.gif"  # Use .mp4 (needs ffmpeg) or .gif (no extra install)
# ---------------------------------------------



def decode(bin_path):
    """Returns (timestamps: np.ndarray[int64] (epoch ms, or boot ms if LEGACY_BOOT_MS_FORMAT),
    pixels: np.ndarray[float32, shape=(N, num_pixels)])"""
    with open(bin_path, "rb") as f:
        data = f.read()

    magic = struct.unpack_from("<I", data, 0)[0] if len(data) >= 4 else None

    if magic == MAGIC:
        _, num_pixels, scale = struct.unpack_from(HEADER_FMT, data, 0)
        offset = HEADER_SIZE
        print(f"Found THM1 header: {num_pixels} pixels, scale={scale}")
    else:
        num_pixels, scale = DEFAULT_NUM_PIXELS, DEFAULT_SCALE
        offset = 0
        print("No THM1 header found - assuming default format "
              f"({num_pixels} pixels, scale={scale}). This happens if the "
              "card wasn't fully seated when the header would have been "
              "written; the frame data itself is unaffected.")

    # CHANGED: new format is uint32 epoch_s + uint16 ms_offset + N x int16 pixels.
    # (old format was just uint32 ms_since_boot + N x int16 pixels.)
    if LEGACY_BOOT_MS_FORMAT:
        record_fmt = f"<I{num_pixels}h"   # ms_since_boot(uint32) + N x int16
    else:
        record_fmt = f"<IH{num_pixels}h"  # epoch_s(uint32) + ms_offset(uint16) + N x int16
    record_size = struct.calcsize(record_fmt)

    timestamps = []
    pixel_rows = []
    while offset + record_size <= len(data):
        values = struct.unpack_from(record_fmt, data, offset)
        if LEGACY_BOOT_MS_FORMAT:
            timestamps.append(values[0])           # ms since boot, as before
            pixel_rows.append([v / scale for v in values[1:]])
        else:
            epoch_s, ms_offset = values[0], values[1]
            timestamps.append(epoch_s * 1000 + ms_offset)  # CHANGED: combined into real epoch ms
            pixel_rows.append([v / scale for v in values[2:]])
        offset += record_size

    leftover = len(data) - offset
    if leftover:
        print(f"Warning: {leftover} trailing bytes don't form a full record "
              "(likely the last write was interrupted) - discarded.")

    return np.array(timestamps, dtype=np.int64), np.array(pixel_rows, dtype=np.float32)


def save_csv(timestamps, pixels, out_path):
    # CHANGED: column renamed from "timestamp_ms" (boot-relative) to
    # "timestamp_epoch_ms" (real Unix time in ms) to match the new format.
    ts_column = "timestamp_ms" if LEGACY_BOOT_MS_FORMAT else "timestamp_epoch_ms"
    columns = [ts_column] + [f"px{i}" for i in range(pixels.shape[1])]
    df = pd.DataFrame(np.column_stack([timestamps, pixels]), columns=columns)
    df.to_csv(out_path, index=False)


def save_npz(timestamps, pixels, out_path):
    num_frames = pixels.shape[0]
    #frames = pixels.reshape(num_frames, SENSOR_HEIGHT, SENSOR_WIDTH)
    np.savez(out_path, timestamps=timestamps, frames=frames)
    print(f"Saved frames array with shape {frames.shape} "
          f"(frames, rows={SENSOR_HEIGHT}, cols={SENSOR_WIDTH})")


def save_animation(anim):
        print(f"Saving animation to {SAVE_PATH} ...")
        if SAVE_PATH.lower().endswith(".gif"):
            writer = animation.PillowWriter(fps=FPS)
        else:
            writer = animation.FFMpegWriter(fps=FPS)

        anim.save(SAVE_PATH, writer=writer)
        print("Done saving.")


def animate_thermograms(frames, timestamps):

    if len(frames) == 0:
        print("No frames found in npz file.")
        return

    print(f"Loaded {len(frames)} frames from {NPZ_PATH}")

    # Use global min/max across all frames so brightness is consistent frame to frame
    vmin, vmax = np.percentile(frames, [2, 99])



    fig, ax = plt.subplots()
    img = ax.imshow(frames[0], cmap="inferno", interpolation= None, vmin=vmin, vmax=vmax)


    fig.colorbar(img, ax=ax, label="Temperature (C)")
    title = ax.set_title("")

    

    def update(i):
        img.set_data(frames[i])
        # CHANGED: timestamps are now real epoch ms, so format them as an
        # actual date/time instead of showing a raw "N ms" boot-relative number.
        if LEGACY_BOOT_MS_FORMAT:
            ts_label = f"{timestamps[i]} ms"
        else:
            # Note: this is whatever timezone your computer was in when you set
            # the RTC (via __DATE__/__TIME__), not true UTC - the RTC has no
            # timezone awareness of its own, it just stores whatever it was given.
            dt = datetime.fromtimestamp(timestamps[i] / 1000, tz=timezone.utc)
            ts_label = dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        title.set_text(f"Frame {i + 1}/{len(frames)}   {ts_label}")
        return img, title

    anim = animation.FuncAnimation(
        fig,
        update,
        frames=len(frames),
        interval=1000 / FPS,  # milliseconds between frames
        blit=False,
        repeat=True,
    )
    
    plt.show()
    return(anim)





if __name__ == "__main__":

    timestamps, pixels = decode(in_path)
    frames = pixels.reshape(-1, SENSOR_HEIGHT, SENSOR_WIDTH)

    thermogram_animation = animate_thermograms(frames, timestamps)
    save_animation(thermogram_animation)
    save_npz(timestamps, pixels, out_path)


    print(f"Decoded {len(timestamps)} frames -> {out_path}")














