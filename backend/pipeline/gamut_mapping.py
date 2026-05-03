"""
gamut_mapping.py — Okhsl 空間でのガマットマッピング

Okhsl は設計上 sRGB ガマット境界にマッピングされているため、
s ∈ [0, 1] を保てば sRGB 出力は色域内に収まる。

ターゲット色空間 (Adobe RGB, Display P3) への変換で
生じる微小なオーバーフローは、Okhsl 空間上で s をわずかに
下げる補正を行う（値のクリップではない）。
"""

import numpy as np
from .okhsl import okhsl_to_linear_srgb
from .color_space import linear_srgb_to_target


def is_in_gamut(linear_rgb: np.ndarray, tolerance: float = 1e-6) -> np.ndarray:
    """Linear RGB 値が [0, 1] 範囲内かを判定する。"""
    return np.all(
        (linear_rgb >= -tolerance) & (linear_rgb <= 1.0 + tolerance),
        axis=-1,
    )


def gamut_map_okhsl(
    okhsl_image: np.ndarray,
    target_color_space: str = "srgb",
    max_iterations: int = 16,
    tolerance: float = 1e-4,
) -> np.ndarray:
    """
    Okhsl 画像をターゲット色空間にガマットマッピングする。

    手順:
    1. Okhsl → Linear sRGB に逆変換
    2. Linear sRGB → ターゲット色空間の Linear RGB に変換
    3. sRGB ターゲットの場合はそのまま返す（Okhsl保証）
    4. 範囲外ピクセルは Okhsl 空間で s をわずかに下げて再変換

    Parameters
    ----------
    okhsl_image : np.ndarray
        shape=(H, W, 3), dtype=float32/16。Okhsl色空間の画像 [h, s, l]。
        s は [0, 1] 範囲であること。
    target_color_space : str
        "srgb" | "adobe_rgb" | "display_p3"

    Returns
    -------
    np.ndarray
        ガマットマッピング済みの Linear RGB (ターゲット色空間)。
        shape=(H, W, 3), dtype=float32。値は [0, 1] 範囲。
    """
    orig_dtype = okhsl_image.dtype if okhsl_image.dtype in (np.float16, np.float32, np.float64) else np.float32
    H, W, _ = okhsl_image.shape

    # Step 1: Okhsl → Linear sRGB
    linear_srgb = okhsl_to_linear_srgb(okhsl_image)

    # sRGB ターゲットの場合、Okhsl の設計上ガマット内に収まる
    if target_color_space == "srgb":
        return np.clip(linear_srgb, 0.0, 1.0).astype(orig_dtype)

    # Step 2: Linear sRGB → ターゲット色空間
    linear_target = linear_srgb_to_target(linear_srgb, target_color_space)

    # Step 3: ガマット外ピクセルの検出
    out_of_gamut = ~is_in_gamut(linear_target)
    n_oog = np.count_nonzero(out_of_gamut)

    if n_oog == 0:
        return np.clip(linear_target, 0.0, 1.0).astype(orig_dtype)

    # Step 4: ガマット外ピクセルは Okhsl 空間で s を下げて補正
    oog_okhsl = okhsl_image[out_of_gamut].copy()  # (N, 3) — [h, s, l]
    h = oog_okhsl[:, 0]
    s_original = oog_okhsl[:, 1].copy()
    l = oog_okhsl[:, 2]

    s_low = np.zeros_like(s_original)
    s_high = s_original.copy()

    for _ in range(max_iterations):
        s_mid = (s_low + s_high) * 0.5

        test_hsl = np.stack([h, s_mid, l], axis=-1)
        test_srgb = okhsl_to_linear_srgb(test_hsl)
        test_target = linear_srgb_to_target(test_srgb, target_color_space)

        in_gamut = is_in_gamut(test_target)

        s_low = np.where(in_gamut, s_mid, s_low)
        s_high = np.where(in_gamut, s_high, s_mid)

        if np.all((s_high - s_low) < tolerance):
            break

    # 最終値は s_low (ガマット内保証)
    final_hsl = np.stack([h, s_low, l], axis=-1)
    final_srgb = okhsl_to_linear_srgb(final_hsl)
    final_target = linear_srgb_to_target(final_srgb, target_color_space)

    result = linear_target.copy()
    result[out_of_gamut] = final_target

    return np.clip(result, 0.0, 1.0).astype(orig_dtype)
