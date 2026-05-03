"""
color_space.py — OKlab / sRGB / Adobe RGB / Display P3 色空間変換

すべての演算は float32 NumPy 配列上で行い、画像全体をベクタライズ処理する。
行列定数は Björn Ottosson の OKlab 仕様および IEC / ICC 公式定義に基づく。
"""

import numpy as np

# ──────────────────────────────────────────────
# 定数: RGB ↔ XYZ 変換行列 (D65 白色点)
# ──────────────────────────────────────────────

# sRGB (IEC 61966-2-1)  — D65
SRGB_TO_XYZ = np.array([
    [0.4123907993, 0.3575843394, 0.1804807884],
    [0.2126390059, 0.7151686788, 0.0721923154],
    [0.0193308187, 0.1191947798, 0.9505321522],
], dtype=np.float64)

XYZ_TO_SRGB = np.linalg.inv(SRGB_TO_XYZ)

# Adobe RGB (1998)  — D65
ADOBE_RGB_TO_XYZ = np.array([
    [0.5766690429, 0.1855582379, 0.1882286462],
    [0.2973449753, 0.6273635663, 0.0752914585],
    [0.0270313614, 0.0706888525, 0.9913375368],
], dtype=np.float64)

XYZ_TO_ADOBE_RGB = np.linalg.inv(ADOBE_RGB_TO_XYZ)

# Display P3 (Apple)  — D65  (sRGB と同じ TRC, 異なる primaries)
DISPLAY_P3_TO_XYZ = np.array([
    [0.4865709486, 0.2656676932, 0.1982172852],
    [0.2289745641, 0.6917385218, 0.0792869141],
    [0.0000000000, 0.0451133819, 1.0439443689],
], dtype=np.float64)

XYZ_TO_DISPLAY_P3 = np.linalg.inv(DISPLAY_P3_TO_XYZ)

# ──────────────────────────────────────────────
# 定数: OKlab 変換行列 (Björn Ottosson)
# ──────────────────────────────────────────────

# Linear sRGB → LMS (approximate cone response)
_M1 = np.array([
    [0.4122214708, 0.5363325363, 0.0514459929],
    [0.2119034982, 0.6806995451, 0.1073969566],
    [0.0883024619, 0.2817188376, 0.6299787005],
], dtype=np.float64)

# LMS^(1/3) → OKlab
_M2 = np.array([
    [0.2104542553, 0.7936177850, -0.0040720468],
    [1.9779984951, -2.4285922050,  0.4505937099],
    [0.0259040371, 0.7827717662, -0.8086757660],
], dtype=np.float64)

_M1_INV = np.linalg.inv(_M1)
_M2_INV = np.linalg.inv(_M2)

# ──────────────────────────────────────────────
# ガンマ関数 (EOTF / OETF)
# ──────────────────────────────────────────────

def srgb_eotf(v: np.ndarray) -> np.ndarray:
    """sRGB ガンマ解除 (非線形 → リニア)。"""
    orig_dtype = v.dtype if v.dtype in (np.float16, np.float32, np.float64) else np.float32
    v_f32 = v.astype(np.float32, copy=False)
    linear = np.where(
        v_f32 <= 0.04045,
        v_f32 / 12.92,
        np.power((v_f32 + 0.055) / 1.055, 2.4),
    )
    return linear.astype(orig_dtype)


def srgb_oetf(v: np.ndarray) -> np.ndarray:
    """sRGB ガンマエンコード (リニア → 非線形)。"""
    orig_dtype = v.dtype if v.dtype in (np.float16, np.float32, np.float64) else np.float32
    v_f32 = np.clip(v.astype(np.float32, copy=False), 0.0, 1.0)
    encoded = np.where(
        v_f32 <= 0.0031308,
        12.92 * v_f32,
        1.055 * np.power(v_f32, 1.0 / 2.4) - 0.055,
    )
    return encoded.astype(orig_dtype)


def adobe_rgb_eotf(v: np.ndarray) -> np.ndarray:
    """Adobe RGB ガンマ解除 (γ = 2.19921875)。"""
    orig_dtype = v.dtype if v.dtype in (np.float16, np.float32, np.float64) else np.float32
    v = np.asarray(v, dtype=orig_dtype)
    return np.power(np.clip(v, 0.0, 1.0), 2.19921875).astype(orig_dtype)


def adobe_rgb_oetf(v: np.ndarray) -> np.ndarray:
    """Adobe RGB ガンマエンコード。"""
    orig_dtype = v.dtype if v.dtype in (np.float16, np.float32, np.float64) else np.float32
    v = np.asarray(v, dtype=orig_dtype)
    v = np.clip(v, 0.0, 1.0)
    return np.power(v, 1.0 / 2.19921875).astype(orig_dtype)


def display_p3_eotf(v: np.ndarray) -> np.ndarray:
    """Display P3 ガンマ解除 (sRGB TRC と同一)。"""
    return srgb_eotf(v)


def display_p3_oetf(v: np.ndarray) -> np.ndarray:
    """Display P3 ガンマエンコード (sRGB TRC と同一)。"""
    return srgb_oetf(v)


# ──────────────────────────────────────────────
# OKlab 変換
# ──────────────────────────────────────────────

def linear_srgb_to_oklab(rgb: np.ndarray) -> np.ndarray:
    """
    Linear sRGB → OKlab。
    入力: (..., 3) float 配列 [0, 1]
    出力: (..., 3) float 配列  L∈[0,1], a,b∈[-0.5, 0.5] 程度
    """
    orig_dtype = rgb.dtype if rgb.dtype in (np.float16, np.float32, np.float64) else np.float32
    # float64 入力の場合は float64 で計算を維持
    work_dtype = np.float64 if orig_dtype == np.float64 else np.float32
    
    rgb_w = rgb.astype(work_dtype, copy=False)
    m1 = _M1.astype(work_dtype)
    m2 = _M2.astype(work_dtype)
    
    lms = rgb_w @ m1.T
    # cube root (符号を保持)
    lms_cr = np.sign(lms) * np.abs(lms) ** (1.0 / 3.0)
    oklab = lms_cr @ m2.T
    return oklab.astype(orig_dtype)


def oklab_to_linear_srgb(lab: np.ndarray) -> np.ndarray:
    """
    OKlab → Linear sRGB。
    クリッピングは行わない（呼び出し側でガマットマッピングする）。
    """
    orig_dtype = lab.dtype if lab.dtype in (np.float16, np.float32, np.float64) else np.float32
    work_dtype = np.float64 if orig_dtype == np.float64 else np.float32
    
    lab_w = lab.astype(work_dtype, copy=False)
    m1_inv = _M1_INV.astype(work_dtype)
    m2_inv = _M2_INV.astype(work_dtype)
    
    lms_cr = lab_w @ m2_inv.T
    lms = lms_cr ** 3
    rgb = lms @ m1_inv.T
    return rgb.astype(orig_dtype)


# ──────────────────────────────────────────────
# OKlab ↔ Oklch
# ──────────────────────────────────────────────

def oklab_to_oklch(lab: np.ndarray) -> np.ndarray:
    """OKlab (L, a, b) → Oklch (L, C, h)。 h は radians。"""
    orig_dtype = lab.dtype if lab.dtype in (np.float16, np.float32, np.float64) else np.float32
    lab_f32 = lab.astype(np.float32, copy=False)
    L = lab_f32[..., 0]
    a = lab_f32[..., 1]
    b = lab_f32[..., 2]
    C = np.sqrt(a ** 2 + b ** 2)
    h = np.arctan2(b, a)
    return np.stack([L, C, h], axis=-1).astype(orig_dtype)


def oklch_to_oklab(lch: np.ndarray) -> np.ndarray:
    """Oklch (L, C, h) → OKlab (L, a, b)。 h は radians。"""
    orig_dtype = lch.dtype if lch.dtype in (np.float16, np.float32, np.float64) else np.float32
    lch_f32 = lch.astype(np.float32, copy=False)
    L = lch_f32[..., 0]
    C = lch_f32[..., 1]
    h = lch_f32[..., 2]
    a = C * np.cos(h)
    b = C * np.sin(h)
    return np.stack([L, a, b], axis=-1).astype(orig_dtype)


# ──────────────────────────────────────────────
# CIELAB / CIE LCH 変換 (従来方式の比較用)
# ──────────────────────────────────────────────

# D65 白色点
_D65_Xn = 0.95047
_D65_Yn = 1.00000
_D65_Zn = 1.08883

_LAB_DELTA = 6.0 / 29.0
_LAB_DELTA_SQ = _LAB_DELTA ** 2
_LAB_DELTA_CB = _LAB_DELTA ** 3


def _lab_f(t: np.ndarray) -> np.ndarray:
    """CIELAB の f(t) 関数。"""
    return np.where(
        t > _LAB_DELTA_CB,
        np.cbrt(t),
        t / (3.0 * _LAB_DELTA_SQ) + 4.0 / 29.0,
    )


def _lab_f_inv(t: np.ndarray) -> np.ndarray:
    """CIELAB の f^-1(t) 関数。"""
    return np.where(
        t > _LAB_DELTA,
        t ** 3,
        3.0 * _LAB_DELTA_SQ * (t - 4.0 / 29.0),
    )


def xyz_to_cielab(xyz: np.ndarray) -> np.ndarray:
    """CIE XYZ (D65) → CIELAB。  L∈[0,100], a,b∈[-128,128] 程度。"""
    orig_dtype = xyz.dtype if xyz.dtype in (np.float16, np.float32, np.float64) else np.float32
    xyz = np.asarray(xyz, dtype=orig_dtype)
    fx = _lab_f(xyz[..., 0] / _D65_Xn)
    fy = _lab_f(xyz[..., 1] / _D65_Yn)
    fz = _lab_f(xyz[..., 2] / _D65_Zn)
    L = 116.0 * fy - 16.0
    a = 500.0 * (fx - fy)
    b = 200.0 * (fy - fz)
    return np.stack([L, a, b], axis=-1).astype(orig_dtype)


def cielab_to_xyz(lab: np.ndarray) -> np.ndarray:
    """CIELAB → CIE XYZ (D65)。"""
    orig_dtype = lab.dtype if lab.dtype in (np.float16, np.float32, np.float64) else np.float32
    lab = np.asarray(lab, dtype=orig_dtype)
    fy = (lab[..., 0] + 16.0) / 116.0
    fx = lab[..., 1] / 500.0 + fy
    fz = fy - lab[..., 2] / 200.0
    X = _D65_Xn * _lab_f_inv(fx)
    Y = _D65_Yn * _lab_f_inv(fy)
    Z = _D65_Zn * _lab_f_inv(fz)
    return np.stack([X, Y, Z], axis=-1).astype(orig_dtype)


def cielab_to_cielch(lab: np.ndarray) -> np.ndarray:
    """CIELAB (L, a, b) → CIE LCH (L, C, h)。 L∈[0,100], h は radians。"""
    orig_dtype = lab.dtype if lab.dtype in (np.float16, np.float32, np.float64) else np.float32
    lab = np.asarray(lab, dtype=orig_dtype)
    L = lab[..., 0]
    a = lab[..., 1]
    b = lab[..., 2]
    C = np.sqrt(a ** 2 + b ** 2)
    h = np.arctan2(b, a)
    return np.stack([L, C, h], axis=-1).astype(orig_dtype)


def cielch_to_cielab(lch: np.ndarray) -> np.ndarray:
    """CIE LCH (L, C, h) → CIELAB (L, a, b)。 h は radians。"""
    orig_dtype = lch.dtype if lch.dtype in (np.float16, np.float32, np.float64) else np.float32
    lch = np.asarray(lch, dtype=orig_dtype)
    L = lch[..., 0]
    C = lch[..., 1]
    h = lch[..., 2]
    a = C * np.cos(h)
    b = C * np.sin(h)
    return np.stack([L, a, b], axis=-1).astype(orig_dtype)


def linear_srgb_to_cielch(rgb: np.ndarray) -> np.ndarray:
    """Linear sRGB → CIE LCH (ショートカット)。"""
    xyz = linear_srgb_to_xyz(rgb)
    lab = xyz_to_cielab(xyz)
    return cielab_to_cielch(lab)


def cielch_to_linear_srgb(lch: np.ndarray) -> np.ndarray:
    """CIE LCH → Linear sRGB (ショートカット)。"""
    lab = cielch_to_cielab(lch)
    xyz = cielab_to_xyz(lab)
    return xyz_to_linear_srgb(xyz)


# ──────────────────────────────────────────────
# XYZ 中間変換 (色空間間変換に使用)
# ──────────────────────────────────────────────

def linear_srgb_to_xyz(rgb: np.ndarray) -> np.ndarray:
    """Linear sRGB → CIE XYZ (D65)。"""
    return (np.asarray(rgb, dtype=np.float64) @ SRGB_TO_XYZ.T).astype(np.float32)


def xyz_to_linear_srgb(xyz: np.ndarray) -> np.ndarray:
    """CIE XYZ (D65) → Linear sRGB。"""
    return (np.asarray(xyz, dtype=np.float64) @ XYZ_TO_SRGB.T).astype(np.float32)


def xyz_to_linear_adobe_rgb(xyz: np.ndarray) -> np.ndarray:
    """CIE XYZ (D65) → Linear Adobe RGB。"""
    return (np.asarray(xyz, dtype=np.float64) @ XYZ_TO_ADOBE_RGB.T).astype(np.float32)


def linear_adobe_rgb_to_xyz(rgb: np.ndarray) -> np.ndarray:
    """Linear Adobe RGB → CIE XYZ (D65)。"""
    return (np.asarray(rgb, dtype=np.float64) @ ADOBE_RGB_TO_XYZ.T).astype(np.float32)


def xyz_to_linear_display_p3(xyz: np.ndarray) -> np.ndarray:
    """CIE XYZ (D65) → Linear Display P3。"""
    return (np.asarray(xyz, dtype=np.float64) @ XYZ_TO_DISPLAY_P3.T).astype(np.float32)


def linear_display_p3_to_xyz(rgb: np.ndarray) -> np.ndarray:
    """Linear Display P3 → CIE XYZ (D65)。"""
    return (np.asarray(rgb, dtype=np.float64) @ DISPLAY_P3_TO_XYZ.T).astype(np.float32)


# ──────────────────────────────────────────────
# 統合ヘルパー: Linear sRGB → target 色空間 Linear RGB
# ──────────────────────────────────────────────

# sRGB → target の直接変換行列をキャッシュ
_SRGB_TO_ADOBE = XYZ_TO_ADOBE_RGB @ SRGB_TO_XYZ
_SRGB_TO_P3 = XYZ_TO_DISPLAY_P3 @ SRGB_TO_XYZ

# target → sRGB の直接変換行列
_ADOBE_TO_SRGB = XYZ_TO_SRGB @ ADOBE_RGB_TO_XYZ
_P3_TO_SRGB = XYZ_TO_SRGB @ DISPLAY_P3_TO_XYZ


def linear_srgb_to_target(rgb: np.ndarray, target: str) -> np.ndarray:
    """
    Linear sRGB → ターゲット色空間の Linear RGB へ変換。
    target: "srgb" | "adobe_rgb" | "display_p3"
    """
    if target == "srgb":
        return rgb
    elif target == "adobe_rgb":
        return (np.asarray(rgb, dtype=np.float64) @ _SRGB_TO_ADOBE.T).astype(np.float32)
    elif target == "display_p3":
        return (np.asarray(rgb, dtype=np.float64) @ _SRGB_TO_P3.T).astype(np.float32)
    else:
        raise ValueError(f"Unknown target color space: {target}")


def target_to_linear_srgb(rgb: np.ndarray, source: str) -> np.ndarray:
    """
    ターゲット色空間の Linear RGB → Linear sRGB へ変換。
    source: "srgb" | "adobe_rgb" | "display_p3"
    """
    if source == "srgb":
        return rgb
    elif source == "adobe_rgb":
        return (np.asarray(rgb, dtype=np.float64) @ _ADOBE_TO_SRGB.T).astype(np.float32)
    elif source == "display_p3":
        return (np.asarray(rgb, dtype=np.float64) @ _P3_TO_SRGB.T).astype(np.float32)
    else:
        raise ValueError(f"Unknown source color space: {source}")


def apply_target_oetf(rgb: np.ndarray, color_space: str) -> np.ndarray:
    """ターゲット色空間に対応するガンマエンコードを適用。"""
    if color_space in ("srgb", "display_p3"):
        return srgb_oetf(rgb)
    elif color_space == "adobe_rgb":
        return adobe_rgb_oetf(rgb)
    else:
        raise ValueError(f"Unknown color space: {color_space}")


def apply_target_eotf(rgb: np.ndarray, color_space: str) -> np.ndarray:
    """ターゲット色空間に対応するガンマ解除を適用。"""
    if color_space in ("srgb", "display_p3"):
        return srgb_eotf(rgb)
    elif color_space == "adobe_rgb":
        return adobe_rgb_eotf(rgb)
    else:
        raise ValueError(f"Unknown color space: {color_space}")
