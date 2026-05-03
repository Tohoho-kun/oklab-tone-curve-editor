"""
tone_curve.py — Okhsl 空間でのトーンカーブ・彩度調整

SciPy への依存を排除し、NumPy のみで単調三次スプライン補間 (Monotonic Cubic Spline) を実装。
"""

import numpy as np

def generate_lut_from_control_points(
    points: list[tuple[float, float]],
    size: int = 4096,
) -> np.ndarray:
    """
    制御点リストから1D LUT を生成する。
    SciPy の PchipInterpolator の代わりに、NumPy ベースの単調三次スプライン補間を使用。
    """
    pts = sorted(points, key=lambda p: p[0])

    # 境界値の補完
    if pts[0][0] > 0.0:
        pts.insert(0, (0.0, pts[0][1])) # 最初の点のy値を維持
    if pts[-1][0] < 1.0:
        pts.append((1.0, pts[-1][1])) # 最後の点のy値を維持

    xs = np.array([p[0] for p in pts], dtype=np.float64)
    ys = np.array([p[1] for p in pts], dtype=np.float64)

    # 単調三次スプライン補間 (Fritsch-Carlson 法の簡略版)
    # PCHIP と同様に、オーバーシュートのない滑らかな補間を行う
    
    n = len(xs)
    if n < 2:
        return np.linspace(0.0, 1.0, size).astype(np.float32)
    
    # 勾配の計算
    dx = np.diff(xs)
    dy = np.diff(ys)
    m = dy / dx # 隣接点間の傾き
    
    # 各点での接線勾配 ms を計算
    ms = np.zeros(n)
    for i in range(1, n - 1):
        # 傾きが正負で異なる場合は 0 にする（単調性を維持）
        if m[i-1] * m[i] <= 0:
            ms[i] = 0
        else:
            # 加重平均勾配
            w1 = 2 * dx[i] + dx[i-1]
            w2 = dx[i] + 2 * dx[i-1]
            ms[i] = (w1 + w2) / (w1 / m[i-1] + w2 / m[i])
            
    # 端点の勾配
    ms[0] = m[0] # 簡易的な端点処理
    ms[-1] = m[-1]

    # LUT の生成
    lut_x = np.linspace(0.0, 1.0, size)
    
    # xs の各区間を特定
    idx = np.searchsorted(xs, lut_x)
    idx = np.clip(idx, 1, n - 1)
    
    # 各区間でのエルミートスプライン補間
    x_low = xs[idx-1]
    x_high = xs[idx]
    y_low = ys[idx-1]
    y_high = ys[idx]
    m_low = ms[idx-1]
    m_high = ms[idx]
    
    h = x_high - x_low
    t = (lut_x - x_low) / h
    
    # エルミート基底関数
    h00 = 2*t**3 - 3*t**2 + 1
    h10 = t**3 - 2*t**2 + t
    h01 = -2*t**3 + 3*t**2
    h11 = t**3 - t**2
    
    lut_y = h00*y_low + h10*h*m_low + h01*y_high + h11*h*m_high
    return np.clip(lut_y, 0.0, 1.0).astype(np.float32)


def _apply_lut(channel: np.ndarray, lut: np.ndarray) -> np.ndarray:
    """チャンネルに LUT を線形補間で適用する。入力は [0, 1] 範囲。"""
    lut_size = len(lut)
    indices = np.clip(channel, 0.0, 1.0) * (lut_size - 1)
    idx_low = np.floor(indices).astype(np.int32)
    idx_high = np.minimum(idx_low + 1, lut_size - 1)
    frac = (indices - idx_low).astype(channel.dtype, copy=False)
    lut_cast = lut.astype(channel.dtype, copy=False)
    return lut_cast[idx_low] * (1.0 - frac) + lut_cast[idx_high] * frac


def apply_tone_curve_okhsl(
    okhsl_image: np.ndarray,
    l_lut: np.ndarray,
    saturation_scale: float = 1.0,
    ss_lut: np.ndarray | None = None,
    ls_lut: np.ndarray | None = None,
    saturation_mode: str = "slider",
    hue_shift: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Okhsl 画像に対してトーンカーブ・彩度調整・色相シフトを適用する。
    """
    result = okhsl_image.copy()

    # ── l チャンネルにトーンカーブ LUT 適用 ──
    if l_lut is not None:
        result[..., 2] = _apply_lut(result[..., 2], l_lut)

    # ── s チャンネル調整 ──
    s_input = result[..., 1]
    s_after_ss = s_input.copy()

    if saturation_mode == "slider":
        if saturation_scale != 1.0:
            s_after_ss = np.clip(s_input * saturation_scale, 0.0, 1.0)
            result[..., 1] = s_after_ss
    elif saturation_mode == "curve":
        s_work = s_input.copy()
        if ss_lut is not None:
            s_work = _apply_lut(s_work, ss_lut)
        s_after_ss = s_work.copy()
        if ls_lut is not None:
            l_adj = result[..., 2]
            ls_factor = _apply_lut(l_adj, ls_lut) * 2.0
            s_work = s_work * ls_factor
        result[..., 1] = np.clip(s_work, 0.0, 1.0)

    # ── h チャンネルにシフト適用 ──
    if hue_shift != 0.0:
        h_shift_norm = hue_shift / 360.0
        result[..., 0] = (result[..., 0] + h_shift_norm) % 1.0

    return result, s_after_ss


def identity_curve_points() -> list[tuple[float, float]]:
    return [(0.0, 0.0), (1.0, 1.0)]

def identity_ls_curve_points() -> list[tuple[float, float]]:
    return [(0.0, 0.5), (1.0, 0.5)]
