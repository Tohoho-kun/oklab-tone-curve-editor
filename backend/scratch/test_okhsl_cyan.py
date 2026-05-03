import sys
import os
import numpy as np

# Add backend to sys.path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from pipeline.okhsl import linear_srgb_to_okhsl, okhsl_to_linear_srgb, _get_Cs, find_cusp
from pipeline.color_space import linear_srgb_to_oklab

def test_cyan():
    print("--- Testing Cyan [0, 1, 1] ---")
    rgb = np.array([[0, 1, 1]], dtype=np.float64)
    
    lab = linear_srgb_to_oklab(rgb)
    L, a, b = lab[0]
    C = np.sqrt(a*a + b*b)
    h = 0.5 + 0.5 * np.arctan2(-b, -a) / np.pi
    print(f"OKlab: L={L:.4f}, a={a:.4f}, b={b:.4f}, C={C:.4f}, h={h:.4f}")
    
    a_ = a / C
    b_ = b / C
    cL, cC = find_cusp(np.array([a_]), np.array([b_]))
    print(f"Cusp: L={cL[0]:.4f}, C={cC[0]:.4f}")
    
    C0, Cmid, Cmax = _get_Cs(np.array([L]), np.array([a_]), np.array([b_]))
    print(f"Cs: C0={C0[0]:.4f}, Cmid={Cmid[0]:.4f}, Cmax={Cmax[0]:.4f}")
    
    hsl = linear_srgb_to_okhsl(rgb)
    print(f"Okhsl: {hsl[0]}")
    
    back_rgb = okhsl_to_linear_srgb(hsl)
    print(f"Back to RGB: {back_rgb[0]}")
    print(f"Diff: {np.abs(rgb[0] - back_rgb[0])}")

if __name__ == "__main__":
    test_cyan()
