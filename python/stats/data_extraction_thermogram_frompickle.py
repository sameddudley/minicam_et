
import pickle
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.animation as animation
 
# ----- Settings you may need to change -----
PICKLE_PATH = r"C:\Users\samed\OneDrive\Documents\Arduino\thermal_log.pkl"   # Path to the pickled frames dictionary
SAVE_PATH = "thermal_playback."  # Use .mp4 (needs ffmpeg) or .gif (no extra install)
# ---------------------------------------------
 
def main():
    with open(PICKLE_PATH, "rb") as f:
        frames_dict = pickle.load(f)
 
    if not frames_dict:
        print("No frames found in pickle file.")
        return
 
    # Sort by timestamp so playback is in chronological order
    timestamps = sorted(frames_dict.keys())
    frames = [frames_dict[t] for t in timestamps]
    print(f"Loaded {len(frames)} frames from {PICKLE_PATH}")


    x, y = 12, 12
    results = {}

    for key, arr in data.items():
        # slice is [row_start:row_end, col_start:col_end]
        # rows correspond to y, columns correspond to x
        patch = arr[y-1:y+2, x-1:x+2]
        results[key] = patch.mean()

    df = pd.DataFrame(list(results.items()), columns=['key', 'avg_3x3'])



    print(df)
 


 
if __name__ == "__main__":
    main()