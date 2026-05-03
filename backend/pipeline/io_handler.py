"""
io_handler.py — 多フォーマット画像 I/O

デコード: 各フォーマットをfloat32 Linear sRGB配列に変換
エンコード: float32配列を指定フォーマット・品質・ICCプロファイル付きで出力
"""

import io, logging
import numpy as np
from PIL import Image, ExifTags
from .color_space import srgb_eotf, apply_target_oetf
from .icc_profiles import get_icc_profile

logger = logging.getLogger(__name__)

try:
    import tifffile
    HAS_TIFFFILE = True
except ImportError:
    HAS_TIFFFILE = False

# Optional format support
try:
    import rawpy
    HAS_RAWPY = True
except ImportError:
    HAS_RAWPY = False

try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HAS_HEIF = True
except ImportError:
    HAS_HEIF = False

try:
    import pillow_avif  # noqa: F401
    HAS_AVIF = True
except ImportError:
    HAS_AVIF = False

# Supported extensions
SUPPORTED_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.tiff', '.tif', '.webp', '.bmp',
}
if HAS_RAWPY:
    SUPPORTED_EXTENSIONS.add('.dng')
if HAS_HEIF:
    SUPPORTED_EXTENSIONS.update({'.heic', '.heif'})
if HAS_AVIF:
    SUPPORTED_EXTENSIONS.add('.avif')


def decode_image(file_bytes: bytes, filename: str) -> tuple[np.ndarray, dict]:
    """
    画像をデコードし、Linear sRGB float32 配列とメタデータを返す。

    Returns
    -------
    (array, metadata) : tuple
        array: shape=(H, W, 3), dtype=float32, Linear sRGB [0, 1]
        metadata: dict with keys:
            - 'width', 'height'
            - 'format': original format string
            - 'bit_depth': original bit depth (8 or 16)
            - 'exif': raw exif bytes or None
            - 'icc_profile': original ICC profile bytes or None
    """
    ext = _get_extension(filename)
    metadata = {
        'format': ext.lstrip('.').upper(),
        'exif': None,
        'icc_profile': None,
        'bit_depth': 8,
    }

    if ext == '.dng' and HAS_RAWPY:
        return _decode_dng(file_bytes, metadata)

    return _decode_pillow(file_bytes, metadata)


def _get_extension(filename: str) -> str:
    import os
    return os.path.splitext(filename.lower())[1]


def _decode_pillow(file_bytes: bytes, metadata: dict) -> tuple[np.ndarray, dict]:
    """Pillow を使った汎用デコード。"""
    img = Image.open(io.BytesIO(file_bytes))

    # Extract metadata
    metadata['width'] = img.width
    metadata['height'] = img.height

    # Exif
    exif_data = img.info.get('exif')
    if exif_data:
        metadata['exif'] = exif_data

    # ICC Profile
    icc = img.info.get('icc_profile')
    if icc:
        metadata['icc_profile'] = icc

    # Determine bit depth
    if img.mode == 'I;16' or img.mode == 'I;16B':
        metadata['bit_depth'] = 16
    elif img.mode == 'I':
        metadata['bit_depth'] = 16
    else:
        metadata['bit_depth'] = 8

    # Convert to RGB
    if img.mode == 'RGBA':
        # Flatten alpha
        bg = Image.new('RGB', img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg
    elif img.mode == 'I;16' or img.mode == 'I;16B' or img.mode == 'I':
        # 16-bit grayscale or RGB
        arr = np.array(img, dtype=np.float64)
        if arr.max() > 255:
            arr = arr / 65535.0
        else:
            arr = arr / 255.0
        if len(arr.shape) == 2:
            arr = np.stack([arr, arr, arr], axis=-1)
        return srgb_eotf(arr.astype(np.float32)), metadata
    elif img.mode != 'RGB':
        img = img.convert('RGB')

    # Normalize to [0, 1]
    arr = np.array(img, dtype=np.float32) / 255.0

    # Linearize (sRGB EOTF)
    linear = srgb_eotf(arr)

    return linear, metadata


def _decode_dng(file_bytes: bytes, metadata: dict) -> tuple[np.ndarray, dict]:
    """rawpy を使った DNG デコード。"""
    import tempfile
    import os

    # rawpy requires a file path
    with tempfile.NamedTemporaryFile(suffix='.dng', delete=False) as tmp:
        tmp.write(file_bytes)
        tmp_path = tmp.name

    try:
        raw = rawpy.imread(tmp_path)
        # Postprocess to 16-bit linear RGB
        rgb = raw.postprocess(
            output_bps=16,
            no_auto_bright=True,
            use_camera_wb=True,
            gamma=(1, 1),  # Linear
            output_color=rawpy.ColorSpace.sRGB,
        )
        arr = np.array(rgb, dtype=np.float32) / 65535.0
        metadata['width'] = arr.shape[1]
        metadata['height'] = arr.shape[0]
        metadata['bit_depth'] = 16
        metadata['format'] = 'DNG'
        return arr, metadata
    finally:
        os.unlink(tmp_path)


def encode_image(
    linear_rgb: np.ndarray,
    output_format: str,
    color_space: str = "srgb",
    quality: int = 95,
    bit_depth: int = 8,
    exif: bytes | None = None,
    tiff_compression: str = "none",
) -> bytes:
    """
    Linear RGB float32 配列をエンコードして画像バイトを返す。

    Parameters
    ----------
    linear_rgb : shape=(H, W, 3), float32, [0, 1] ガンマ前のLinear RGB
    output_format : "jpeg" | "tiff" | "webp" | "png" | "avif"
    color_space : "srgb" | "adobe_rgb" | "display_p3"
    quality : JPEG/WebP/AVIF の品質 (1-100)
    bit_depth : 8 or 16
    exif : Exif バイト (Pillow format)
    tiff_compression : TIFF圧縮方式 ("none", "lzw", "zip")
    """
    # Apply gamma encoding
    gamma_rgb = apply_target_oetf(linear_rgb, color_space)

    # Quantize
    # Quantize
    is_tiff = output_format.lower() in ('tif', 'tiff')
    is_png = output_format.lower() == 'png'

    if bit_depth == 16 and (is_tiff or is_png):
        arr_int = np.clip(gamma_rgb * 65535.0, 0, 65535).astype(np.uint16)
    else:
        arr_int = np.clip(gamma_rgb * 255.0, 0, 255).astype(np.uint8)
        bit_depth = 8

    # Get ICC profile
    icc_bytes = get_icc_profile(color_space)

    # TIFF 処理 (tifffile を優先使用)
    if is_tiff and HAS_TIFFFILE:
        logger.info("Using tifffile for export.")
        buf = io.BytesIO()
        comp_map = {'none': 0, 'lzw': 5, 'zip': 8}
        c = comp_map.get(tiff_compression, 0)
        
        # Build tags: ICC profile is tag 34675
        extratags = []
        if icc_bytes:
            # tag, type, count, value, writeonce
            # type 7 is UNDEFINED (raw bytes)
            extratags.append((34675, 7, len(icc_bytes), icc_bytes, True))

        tifffile.imwrite(
            buf, arr_int, 
            photometric='rgb',
            compression=c,
            extratags=extratags
        )
        return buf.getvalue()

    # Create PIL Image for other formats
    # Note: PIL RGB 16-bit support is still flaky, so we fallback to 8-bit 
    # if not using tifffile or if it's not a supported 16-bit mode.
    if arr_int.dtype == np.uint16:
        # Fallback to 8-bit for non-TIFF or if it fails
        arr_8 = np.clip(gamma_rgb * 255.0, 0, 255).astype(np.uint8)
        img = Image.fromarray(arr_8, mode='RGB')
        bit_depth = 8
    else:
        img = Image.fromarray(arr_int, mode='RGB')

    # Build save kwargs
    save_kwargs = {'icc_profile': icc_bytes}

    if exif:
        save_kwargs['exif'] = exif

    fmt = output_format.lower()
    if fmt in ('jpg', 'jpeg'):
        save_kwargs['quality'] = quality
        save_kwargs['subsampling'] = 0  # 4:4:4
        pil_fmt = 'JPEG'
    elif fmt == 'webp':
        save_kwargs['quality'] = quality
        pil_fmt = 'WEBP'
    elif fmt == 'png':
        pil_fmt = 'PNG'
    elif fmt in ('tif', 'tiff'):
        compression_map = {
            'none': 'raw', 'lzw': 'tiff_lzw', 'zip': 'tiff_deflate',
        }
        save_kwargs['compression'] = compression_map.get(tiff_compression, 'raw')
        pil_fmt = 'TIFF'
    elif fmt == 'avif' and HAS_AVIF:
        save_kwargs['quality'] = quality
        pil_fmt = 'AVIF'
    else:
        pil_fmt = 'PNG'  # fallback

    buf = io.BytesIO()
    img.save(buf, format=pil_fmt, **save_kwargs)
    return buf.getvalue()


def create_preview(linear_rgb: np.ndarray, max_edge: int = 1920) -> np.ndarray:
    """
    プレビュー用にリサイズしたLinear RGB配列を返す。

    long edge が max_edge 以下になるようリサイズ。
    Linear 空間のままリサイズする。
    """
    h, w = linear_rgb.shape[:2]
    if max(h, w) <= max_edge:
        return linear_rgb.copy()

    scale = max_edge / max(h, w)
    new_h = int(h * scale)
    new_w = int(w * scale)

    # チャンネルごとにリサイズ (float32 → uint8 だと精度が落ちるため)
    channels = []
    for ch in range(3):
        ch_data = linear_rgb[..., ch]
        # float32 を一旦 0-65535 の uint16 にして単チャンネルでリサイズ
        ch_16 = np.clip(ch_data * 65535.0, 0, 65535).astype(np.uint16)
        ch_img = Image.fromarray(ch_16, mode='I;16')
        ch_resized = ch_img.resize((new_w, new_h), Image.LANCZOS)
        ch_arr = np.array(ch_resized, dtype=np.float32) / 65535.0
        channels.append(ch_arr)

    return np.stack(channels, axis=-1)

