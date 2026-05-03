"""
okhsl.py — Okhsl 色空間変換 (Björn Ottosson) — 高速LUT版

Okhsl は sRGB ガマット境界にマッピングされた相対彩度 (Saturation) ベースの色空間。
このバージョンでは、計算負荷の高いガマット境界探索を事前計算された LUT (Lookup Table) 
に置き換えることで、劇的な高速化を実現している。

参考: https://bottosson.github.io/posts/colorpicker/
"""

import numpy as np
from .color_space import linear_srgb_to_oklab, oklab_to_linear_srgb

_K1 = 0.206
_K2 = 0.03
_K3 = (1.0 + _K1) / (1.0 + _K2)

def toe(x: np.ndarray) -> np.ndarray:
    return 0.5 * (_K3 * x - _K1 + np.sqrt(np.maximum((_K3 * x - _K1) ** 2 + 4.0 * _K2 * _K3 * x, 0.0)))

def toe_inv(x: np.ndarray) -> np.ndarray:
    return (x * x + _K1 * x) / np.maximum(_K3 * (x + _K2), 1e-12)

# ── Gamut LUT ──

class GamutLUT:
    """sRGB ガマット境界 (C_max) を事前計算するクラス"""
    def __init__(self, h_bins=720, l_bins=201):
        self.h_bins = h_bins
        self.l_bins = l_bins
        
        # h: 0 to 1, L: 0 to 1
        h_vals = np.linspace(0, 1, h_bins, endpoint=False)
        l_vals = np.linspace(0, 1, l_bins)
        
        # Precompute a_, b_ for all hues
        a_h = np.cos(2.0 * np.pi * h_vals)
        b_h = np.sin(2.0 * np.pi * h_vals)
        
        # 1. Compute S_max(h) -> maximum S=C/L at L=1 (Cusp saturation)
        self.s_max_lut = self._compute_s_max_vector(a_h, b_h)
        
        # 2. Compute C_max(L, h) -> maximum chroma at lightness L
        # Shape: (l_bins, h_bins)
        self.c_max_lut = np.zeros((l_bins, h_bins), dtype=np.float32)
        for i, l in enumerate(l_vals):
            self.c_max_lut[i] = self._find_gamut_intersection_vector(a_h, b_h, np.full_like(a_h, l))

    def _compute_s_max_vector(self, a_, b_):
        s_min = np.zeros_like(a_)
        s_max = np.ones_like(a_) * 5.0
        for _ in range(40):
            s = (s_min + s_max) / 2.0
            lab = np.stack([np.ones_like(a_), s * a_, s * b_], axis=-1)
            rgb = oklab_to_linear_srgb(lab)
            in_gamut = np.all(rgb >= -1e-2, axis=-1)
            s_min = np.where(in_gamut, s, s_min)
            s_max = np.where(in_gamut, s_max, s)
        return s_min + 1e-6

    def _find_gamut_intersection_vector(self, a_, b_, L):
        t_min = np.zeros_like(L)
        t_max = np.ones_like(L) * 1.5
        for _ in range(40):
            t = (t_min + t_max) / 2.0
            lab = np.stack([L, t * a_, t * b_], axis=-1)
            rgb = oklab_to_linear_srgb(lab)
            in_gamut = np.all((rgb >= -1e-2) & (rgb <= 1.0 + 1e-2), axis=-1)
            t_min = np.where(in_gamut, t, t_min)
            t_max = np.where(in_gamut, t_max, t)
        return t_min + 1e-6

    def get_c_max(self, h, L):
        """Bilinear interpolation from 2D LUT"""
        h_idx = h * (self.h_bins) # Hue is periodic
        l_idx = L * (self.l_bins - 1)
        
        h0 = np.floor(h_idx).astype(np.int32) % self.h_bins
        h1 = (h0 + 1) % self.h_bins
        l0 = np.floor(l_idx).astype(np.int32)
        l1 = np.minimum(l0 + 1, self.l_bins - 1)
        
        wh = h_idx - np.floor(h_idx)
        wl = l_idx - l0
        
        c00 = self.c_max_lut[l0, h0]
        c01 = self.c_max_lut[l0, h1]
        c10 = self.c_max_lut[l1, h0]
        c11 = self.c_max_lut[l1, h1]
        
        return (c00 * (1-wh) * (1-wl) +
                c01 * wh * (1-wl) +
                c10 * (1-wh) * wl +
                c11 * wh * wl)

    def get_s_max(self, h):
        """Linear interpolation from 1D LUT"""
        h_idx = h * (self.h_bins)
        h0 = np.floor(h_idx).astype(np.int32) % self.h_bins
        h1 = (h0 + 1) % self.h_bins
        wh = h_idx - np.floor(h_idx)
        return self.s_max_lut[h0] * (1-wh) + self.s_max_lut[h1] * wh

# Global singleton
GAMUT_LUT = GamutLUT()

# ── Helper Functions ──

def find_cusp(h):
    S_cusp = GAMUT_LUT.get_s_max(h)
    a_ = np.cos(2.0 * np.pi * h)
    b_ = np.sin(2.0 * np.pi * h)
    lab_at_1 = np.stack([np.ones_like(h), S_cusp * a_, S_cusp * b_], axis=-1)
    rgb_at_1 = oklab_to_linear_srgb(lab_at_1)
    rgb_max = np.maximum(np.max(rgb_at_1, axis=-1), 1e-12)
    L_cusp = np.power(1.0 / rgb_max, 1.0 / 3.0)
    C_cusp = L_cusp * S_cusp
    return L_cusp, C_cusp

def _get_Cs(L, h, a_, b_):
    cusp_L, cusp_C = find_cusp(h)
    C_max = GAMUT_LUT.get_c_max(h, L)
    
    S_cusp = cusp_C / np.maximum(cusp_L, 1e-12)
    T_cusp = cusp_C / np.maximum(1.0 - cusp_L, 1e-12)
    k = C_max / np.maximum(np.minimum(L * S_cusp, (1.0 - L) * T_cusp), 1e-12)

    S_mid = 0.11516993 + 1.0 / (7.44778970 + 4.15901240 * b_ + a_ * (-2.19557347 + 1.75198401 * b_ + a_ * (-2.13704948 - 10.02301043 * b_ + a_ * (-4.24894561 + 5.38770819 * b_ + 4.69891013 * a_))))
    T_mid = 0.11239642 + 1.0 / (1.61320320 - 0.68124379 * b_ + a_ * (0.40370612 + 0.90148123 * b_ + a_ * (-0.27087943 + 0.61223990 * b_ + a_ * (0.00299215 - 0.45399568 * b_ - 0.14661872 * a_))))
    C_a, C_b = L * S_mid, (1.0 - L) * T_mid
    C_mid = 0.9 * k * np.power(np.maximum(1.0/np.maximum(C_a**4, 1e-24) + 1.0/np.maximum(C_b**4, 1e-24), 1e-24), -0.25)
    C0a, C0b = L * 0.4, (1.0 - L) * 0.8
    C_0 = np.sqrt(np.maximum(1.0 / np.maximum(1.0/np.maximum(C0a**2, 1e-24) + 1.0/np.maximum(C0b**2, 1e-24), 1e-24), 0.0))
    return C_0, C_mid, C_max

def linear_srgb_to_okhsl(rgb: np.ndarray) -> np.ndarray:
    orig_shape = rgb.shape
    flat = rgb.reshape(-1, 3).astype(np.float64)
    lab = linear_srgb_to_oklab(flat).astype(np.float64)
    L, a, b = lab[:, 0], lab[:, 1], lab[:, 2]
    C = np.sqrt(a * a + b * b)
    eps = 1e-12
    h = 0.5 + 0.5 * np.arctan2(-b, -a) / np.pi
    a_ = np.cos(2.0 * np.pi * h)
    b_ = np.sin(2.0 * np.pi * h)

    C0, Cmid, Cmax = _get_Cs(L, h, a_, b_)
    C_eff = np.minimum(C, Cmax)
    
    mid = 0.8
    k1 = mid * C0
    k2 = 1.0 - k1 / np.maximum(Cmid, eps)
    s_lo = (C_eff / np.maximum(k1 + k2 * C_eff, eps)) * mid
    
    k1_hi = (1.0 - mid) * Cmid**2 * 1.5625 / np.maximum(C0, eps)
    k2_hi = 1.0 - k1_hi / np.maximum(Cmax - Cmid, eps)
    s_hi = mid + (1.0 - mid) * (C_eff - Cmid) / np.maximum(k1_hi + k2_hi * (C_eff - Cmid), eps)
    
    s = np.where(C_eff < Cmid, s_lo, s_hi)
    s = np.where(C < eps, 0.0, np.clip(s, 0.0, 1.0))
    return np.stack([h, s, toe(L)], axis=-1).reshape(orig_shape).astype(rgb.dtype)

def okhsl_to_linear_srgb(hsl: np.ndarray) -> np.ndarray:
    orig_shape = hsl.shape
    flat = hsl.reshape(-1, 3).astype(np.float64)
    h, s, l = flat[:, 0], flat[:, 1], flat[:, 2]
    L = toe_inv(np.clip(l, 0.0, 1.0))
    a_, b_ = np.cos(2.0 * np.pi * h), np.sin(2.0 * np.pi * h)
    C0, Cmid, Cmax = _get_Cs(L, h, a_, b_)
    
    mid = 0.8
    t_lo = 1.25 * s
    k1_lo = mid * C0
    C_lo = t_lo * k1_lo / np.maximum(1.0 - (1.0 - k1_lo / np.maximum(Cmid, 1e-12)) * t_lo, 1e-12)
    
    t_hi = (s - mid) * 5.0
    k1_hi = (1.0 - mid) * Cmid**2 * 1.5625 / np.maximum(C0, 1e-12)
    C_hi = Cmid + t_hi * k1_hi / np.maximum(1.0 - (1.0 - k1_hi / np.maximum(Cmax - Cmid, 1e-12)) * t_hi, 1e-12)
    
    C = np.where(s < mid, C_lo, C_hi)
    is_achromatic = (s <= 0.0) | (l <= 0.0) | (l >= 1.0)
    
    rgb = oklab_to_linear_srgb(np.stack([L, np.where(is_achromatic, 0.0, C) * a_, np.where(is_achromatic, 0.0, C) * b_], axis=-1))
    return np.clip(rgb, 0.0, 1.0).reshape(orig_shape).astype(hsl.dtype)
