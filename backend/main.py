"""
main.py — FastAPI アプリケーション

Okhsl 空間での知覚的トーンカーブ補正
プレビューは常にsRGBで表示（カラープロファイルによる色ずれ防止）
"""

import uuid, time, base64, io, logging
from pathlib import Path
import numpy as np
from PIL import Image as PILImage
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool
import sys

from pipeline.okhsl import linear_srgb_to_okhsl, okhsl_to_linear_srgb
from pipeline.color_space import srgb_oetf, apply_target_oetf
from pipeline.tone_curve import generate_lut_from_control_points, apply_tone_curve_okhsl
from pipeline.gamut_mapping import gamut_map_okhsl
from pipeline.dither import apply_blue_noise_dithering
from pipeline.io_handler import decode_image, encode_image, create_preview
from pipeline.icc_profiles import get_icc_profile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Okhsl Tone Curve Editor")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SESSION_TIMEOUT = 3600

class Session:
    def __init__(self):
        self.session_id = str(uuid.uuid4())
        self.created_at = time.time()
        self.last_accessed = time.time()
        self.full_linear = None
        self.full_okhsl = None
        self.preview_linear = None
        self.preview_okhsl = None
        self.metadata = {}
    def touch(self): self.last_accessed = time.time()
    def is_expired(self): return (time.time() - self.last_accessed) > SESSION_TIMEOUT

sessions: dict[str, Session] = {}

def get_session(sid):
    if sid not in sessions: raise HTTPException(404, "Session not found")
    s = sessions[sid]
    if s.is_expired(): del sessions[sid]; raise HTTPException(410, "Session expired")
    s.touch(); return s

def cleanup_sessions():
    for k in [k for k, v in sessions.items() if v.is_expired()]: del sessions[k]

# ── Models ──
class PreviewRequest(BaseModel):
    session_id: str
    control_points: list[list[float]]
    color_space: str = "srgb"
    lightness_mode: str = "curve"
    lightness_shift: float = 0.0
    saturation_mode: str = "slider"
    saturation_scale: float = 1.0
    ss_points: list[list[float]] = []
    ls_points: list[list[float]] = []
    hue_shift: float = 0.0
    view_mode: str = "color"

class ExportRequest(BaseModel):
    session_id: str
    control_points: list[list[float]]
    color_space: str = "srgb"
    lightness_mode: str = "curve"
    lightness_shift: float = 0.0
    saturation_mode: str = "slider"
    saturation_scale: float = 1.0
    ss_points: list[list[float]] = []
    ls_points: list[list[float]] = []
    hue_shift: float = 0.0
    output_format: str = "jpeg"
    quality: int = 95
    bit_depth: int = 8
    tiff_compression: str = "none"
    use_dithering: bool = True

# ── Pipeline ──

def _build_saturation_luts(req):
    ss_lut = ls_lut = None
    if req.saturation_mode == "curve":
        if req.ss_points:
            ss_lut = generate_lut_from_control_points([(p[0], p[1]) for p in req.ss_points])
        if req.ls_points:
            ls_lut = generate_lut_from_control_points([(p[0], p[1]) for p in req.ls_points])
    return ss_lut, ls_lut

def _okhsl_core(image_data, control_points, lightness_mode, lightness_shift,
                saturation_mode, saturation_scale,
                ss_lut, ls_lut, hue_shift, is_okhsl=False, view_mode="color"):
    """Okhsl 処理コア → 調整済み Okhsl を返す"""
    logger.debug(f"OkhslCore: LMode={lightness_mode}, SMode={saturation_mode}, SScale={saturation_scale:.2f}, View={view_mode}")
    if is_okhsl:
        okhsl = image_data.copy()
    else:
        okhsl = linear_srgb_to_okhsl(image_data)

    if lightness_mode == "slider":
        # 簡易露出調整（lに対する乗算的な処理）
        shift_factor = 2.0 ** lightness_shift
        l_ch = okhsl[..., 2].astype(np.float32, copy=False)
        # Avoid in-place modification of the array we might reuse
        l_new = np.clip(l_ch * shift_factor, 0.0, 1.0).astype(okhsl.dtype)
        okhsl_work = okhsl.copy()
        okhsl_work[..., 2] = l_new
        l_lut = None
    else:
        okhsl_work = okhsl
        pts = [(p[0], p[1]) for p in control_points]
        l_lut = generate_lut_from_control_points(pts)

    return apply_tone_curve_okhsl(
        okhsl_work, l_lut, saturation_scale=saturation_scale,
        ss_lut=ss_lut, ls_lut=ls_lut,
        saturation_mode=saturation_mode, hue_shift=hue_shift,
    )

def _okhsl_to_srgb_preview(okhsl_adj, color_space, view_mode="color"):
    """Okhsl → ガマットマッピング → sRGB ガンマ (プレビュー用)"""
    if view_mode == "saturation":
        # S チャンネルをグレースケールとして抽出 (s=1.0 -> white)
        s_ch = okhsl_adj[..., 1]
        gray = np.stack([s_ch, s_ch, s_ch], axis=-1)
        return gray.astype(np.float32)

    target_linear = gamut_map_okhsl(okhsl_adj, color_space)
    # プレビューは常に sRGB ガンマで表示
    return srgb_oetf(target_linear)

def _compute_histogram(gamma_rgb, session_okhsl=None, adj_okhsl=None, s_after_ss=None):
    hist = {}
    for i, ch in enumerate(['r', 'g', 'b']):
        h, _ = np.histogram(gamma_rgb[..., i], bins=256, range=(0, 1))
        hist[ch] = h.tolist()
    lum = 0.2126*gamma_rgb[...,0] + 0.7152*gamma_rgb[...,1] + 0.0722*gamma_rgb[...,2]
    h, _ = np.histogram(lum, bins=256, range=(0, 1))
    hist['l'] = h.tolist()

    if session_okhsl is not None:
        # Okhsl lightness histogram (index 2)
        h_l, _ = np.histogram(session_okhsl[..., 2], bins=256, range=(0, 1))
        # Okhsl saturation histogram (index 1)
        h_s, _ = np.histogram(session_okhsl[..., 1], bins=256, range=(0, 1))

        hist['okhsl_l'] = h_l.tolist()
        hist['okhsl_s'] = h_s.tolist()

        # Adjusted
        if adj_okhsl is not None:
            h_l_adj, _ = np.histogram(adj_okhsl[..., 2], bins=256, range=(0, 1))
            h_s_adj, _ = np.histogram(adj_okhsl[..., 1], bins=256, range=(0, 1))
            hist['okhsl_l_adj'] = h_l_adj.tolist()
            hist['okhsl_s_adj'] = h_s_adj.tolist()
        
        if s_after_ss is not None:
            h_s_ss, _ = np.histogram(s_after_ss, bins=256, range=(0, 1))
            hist['okhsl_s_after_ss'] = h_s_ss.tolist()

    return hist

def _to_png_b64(gamma_rgb):
    """常にsRGBタグでPNG出力（ブラウザ互換性のため）"""
    arr = np.clip(gamma_rgb * 255, 0, 255).astype(np.uint8)
    img = PILImage.fromarray(arr, 'RGB')
    buf = io.BytesIO()
    img.save(buf, format='PNG', icc_profile=get_icc_profile("srgb"))
    return base64.b64encode(buf.getvalue()).decode('ascii')

# ── Endpoints ──

@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...)):
    cleanup_sessions()
    contents = await file.read()
    filename = file.filename or "unknown.jpg"
    logger.info(f"Upload: {filename} ({len(contents)} bytes)")

    def process():
        linear, meta = decode_image(contents, filename)
        # Store preview in float16 to save memory
        preview = create_preview(linear, max_edge=1280).astype(np.float16)
        # Cache Okhsl for the preview to save CPU time during slider movements
        okhsl = linear_srgb_to_okhsl(preview)

        s = Session()
        s.full_linear = linear; s.preview_linear = preview
        s.preview_okhsl = okhsl
        s.metadata = meta
        sessions[s.session_id] = s

        gamma = srgb_oetf(preview)
        return {
            "session_id": s.session_id,
            "width": meta.get('width', linear.shape[1]),
            "height": meta.get('height', linear.shape[0]),
            "preview_width": preview.shape[1],
            "preview_height": preview.shape[0],
            "format": meta.get('format', 'UNKNOWN'),
            "bit_depth": meta.get('bit_depth', 8),
            "preview": _to_png_b64(gamma),
            "histogram": _compute_histogram(gamma, okhsl, adj_okhsl=okhsl),
        }
    return JSONResponse(await run_in_threadpool(process))


@app.post("/api/preview")
async def preview_image(req: PreviewRequest):
    s = get_session(req.session_id)
    def process():
        ss_lut, ls_lut = _build_saturation_luts(req)
        # Use cached Okhsl for preview
        okhsl_adj, s_after_ss = _okhsl_core(
            s.preview_okhsl.copy(), req.control_points,
            req.lightness_mode, req.lightness_shift,
            req.saturation_mode, req.saturation_scale, ss_lut, ls_lut, req.hue_shift,
            is_okhsl=True, view_mode=req.view_mode
        )
        okhsl_g = _okhsl_to_srgb_preview(okhsl_adj, req.color_space, view_mode=req.view_mode)
        return {
            "preview": _to_png_b64(okhsl_g),
            "histogram": _compute_histogram(okhsl_g, s.preview_okhsl, adj_okhsl=okhsl_adj, s_after_ss=s_after_ss),
        }
    return JSONResponse(await run_in_threadpool(process))


@app.post("/api/export")
async def export_image(req: ExportRequest):
    s = get_session(req.session_id)
    def process():
        ss_lut, ls_lut = _build_saturation_luts(req)

        # Determine processing dtype
        proc_dtype = np.float32 if (req.output_format in ('tiff', 'tif') and req.bit_depth == 16) else np.float16

        okhsl_adj, _ = _okhsl_core(
            s.full_linear.astype(proc_dtype), req.control_points,
            req.lightness_mode, req.lightness_shift,
            req.saturation_mode, req.saturation_scale, ss_lut, ls_lut, req.hue_shift,
            is_okhsl=False
        )
        logger.info("Export: Tone curve applied.")
        
        target_linear = gamut_map_okhsl(okhsl_adj, req.color_space)
        del okhsl_adj # Free memory
        logger.info("Export: Gamut mapping done.")

        # ディザリング適用 (量子化の直前)
        if req.use_dithering:
            target_linear = apply_blue_noise_dithering(target_linear, bit_depth=req.bit_depth)

        fmt = req.output_format
        if s.metadata.get('format') == 'DNG' and fmt == 'dng': fmt = 'tiff'
        logger.info(f"Export: Encoding started as {fmt} ({req.bit_depth}bit)...")
        img_data = encode_image(
            target_linear, fmt, req.color_space, req.quality,
            req.bit_depth, s.metadata.get('exif'), req.tiff_compression,
        )
        del target_linear # Free memory
        return img_data, fmt
    
    try:
        img_bytes, fmt = await run_in_threadpool(process)
    except Exception as e:
        logger.error(f"Export Critical Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    logger.info(f"Export Success: {fmt} ({len(img_bytes)} bytes)")
    mime = {'jpeg':'image/jpeg','jpg':'image/jpeg','png':'image/png',
            'webp':'image/webp','tiff':'image/tiff','tif':'image/tiff','avif':'image/avif'}
    return StreamingResponse(
        io.BytesIO(img_bytes), media_type=mime.get(fmt, 'application/octet-stream'),
        headers={'Content-Disposition': f'attachment; filename="exported.{fmt}"'},
    )

def get_frontend_dir():
    # PyInstaller が展開する一時ディレクトリ (_MEIPASS) を優先
    if hasattr(sys, '_MEIPASS'):
        return Path(sys._MEIPASS) / "frontend"
    # 通常実行時は親ディレクトリの frontend を参照
    return Path(__file__).parent.parent / "frontend"

FRONTEND_DIR = get_frontend_dir()
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
else:
    logger.warning(f"Frontend directory not found at: {FRONTEND_DIR}")
