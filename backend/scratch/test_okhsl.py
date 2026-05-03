import sys
import os
import numpy as np

# Add backend to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pipeline.okhsl import linear_srgb_to_okhsl, okhsl_to_linear_srgb

def test_roundtrip():
    # Test cases: black, white, primary colors, random colors
    test_colors = np.array([
        [0, 0, 0],       # Black
        [1, 1, 1],       # White
        [1, 0, 0],       # Red
        [0, 1, 0],       # Green
        [0, 0, 1],       # Blue
        [0, 1, 1],       # Cyan
        [1, 0, 1],       # Magenta
        [1, 1, 0],       # Yellow
        [0.5, 0.5, 0.5], # Grey
    ], dtype=np.float64)
    
    # Add some random colors
    np.random.seed(42)
    random_colors = np.random.rand(1000, 3).astype(np.float64)
    test_colors = np.vstack([test_colors, random_colors])

    # Convert to Okhsl
    okhsl = linear_srgb_to_okhsl(test_colors)
    
    # Check ranges
    assert np.all(okhsl >= -1e-7) and np.all(okhsl <= 1.0000001), f"Okhsl values out of range: min={np.min(okhsl)}, max={np.max(okhsl)}"
    
    # Roundtrip
    back_to_rgb = okhsl_to_linear_srgb(okhsl)
    
    # Check error
    diff = np.abs(test_colors - back_to_rgb)
    max_diff = np.max(diff)
    mean_diff = np.mean(diff)
    
    print(f"Max difference: {max_diff:.8e}")
    print(f"Mean difference: {mean_diff:.8e}")
    
    if max_diff < 1e-5:
        print("Roundtrip test PASSED")
    else:
        print("Roundtrip test FAILED (diff too large)")
        # Find where it failed
        idx = np.argmax(np.max(diff, axis=1))
        print(f"Failed at RGB {test_colors[idx]} -> HSL {okhsl[idx]} -> RGB {back_to_rgb[idx]}")

if __name__ == "__main__":
    test_roundtrip()
