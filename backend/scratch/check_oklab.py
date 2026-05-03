import numpy as np
from pipeline.color_space import linear_srgb_to_oklab, oklab_to_linear_srgb

rgb = np.array([[0, 0, 1]], dtype=np.float64)
lab = linear_srgb_to_oklab(rgb)
print(f"Original RGB: {rgb}")
print(f"OKlab: {lab}")
rgb_back = oklab_to_linear_srgb(lab)
print(f"Back to RGB: {rgb_back}")
print(f"Diff: {rgb - rgb_back}")
print(f"In Gamut (1e-12): {np.all(rgb_back >= -1e-12) and np.all(rgb_back <= 1.0 + 1e-12)}")
