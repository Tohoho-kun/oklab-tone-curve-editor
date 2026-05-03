import numpy as np
import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from pipeline.okhsl import compute_max_saturation

def test_hues():
    for deg in range(0, 360, 30):
        rad = np.deg2rad(deg)
        a_ = np.cos(rad)
        b_ = np.sin(rad)
        S = compute_max_saturation(np.array([a_]), np.array([b_]))[0]
        print(f"Hue {deg:3d} deg: S={S:.4f}")

if __name__ == "__main__":
    test_hues()
