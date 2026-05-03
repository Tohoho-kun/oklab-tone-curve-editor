/**
 * app.js — メインアプリケーション制御 (Okhsl版)
 */

const API_BASE = '';

let state = {
  sessionId: null,
  colorSpace: 'srgb',
  saturationMode: 'slider',
  saturationScale: 1.0,
  hueShift: 0,
  lightnessMode: 'curve',
  lightnessShift: 0,
  outputFormat: 'jpeg',
  quality: 95,
  bitDepth: 8,
  tiffCompression: 'none',
  imageInfo: null,
  debounceTimer: null,
  showOriginal: false,
  showSatMap: false,
  splitView: false,
  lang: localStorage.getItem('lang') || 'en',
};

const i18n = {
  en: {
    load: "📂 Load", zoom_in: "➕ Zoom", zoom_out: "➖ Zoom", zoom_fit: "🖼 Fit", zoom_11: "🔍 1:1",
    original: "👁 Original", split_view: "↔ Split", sat_map: "📊 SatMap", upload_title: "Drop or Click to Upload",
    upload_subtitle: "Perceptual tone curve in Okhsl space",
    lightness: "Lightness (l)", saturation: "Saturation (S)", hue: "Hue (h)",
    slider: "Slider", curves: "Curves", exposure: "Exposure", scale: "Scale", shift: "Shift",
    output_l: "Output Lightness", input_l: "Input Lightness",
    output_s: "Output Saturation", input_s: "Input Saturation", s_scale: "Saturation Scale",
    reset: "↺ Reset", export_settings: "Export Settings", output_cs: "Output Color Space",
    output_fmt: "Output Format", quality: "Quality", bit_depth: "Bit Depth",
    compression: "Compression", dithering: "Blue Noise Dithering", export_btn: "⬇ Export Image",
    label_orig_l: "Original Lightness", label_adj_l: "Adjusted Lightness",
    label_orig_s: "Original Saturation", label_adj_s: "Saturation (after S×S)",
    label_final_s: "Final Saturation (after l×S)",
    processing: "Processing...",
  },
  ja: {
    load: "📂 読み込み", zoom_in: "➕ 拡大", zoom_out: "➖ 縮小", zoom_fit: "🖼 全体", zoom_11: "🔍 1:1",
    original: "👁 元画像", split_view: "↔ 分割比較", sat_map: "📊 彩度マップ", upload_title: "画像をドロップまたはクリック",
    upload_subtitle: "Okhsl空間での知覚的トーン補正",
    lightness: "明度 (Lightness)", saturation: "彩度 (Saturation)", hue: "色相 (Hue)",
    slider: "スライダー", curves: "カーブ", exposure: "露光量", scale: "倍率", shift: "シフト",
    output_l: "出力明度", input_l: "入力明度",
    output_s: "出力彩度", input_s: "入力彩度", s_scale: "彩度倍率",
    reset: "↺ リセット", export_settings: "書き出し設定", output_cs: "出力カラースペース",
    output_fmt: "出力形式", quality: "画質", bit_depth: "ビット深度",
    compression: "圧縮", dithering: "ブルーノイズディザリング", export_btn: "⬇ 画像を保存",
    label_orig_l: "元の明度", label_adj_l: "調整後明度",
    label_orig_s: "元の彩度", label_adj_s: "調整後彩度 (S×S後)",
    label_final_s: "最終彩度 (l×S後)",
    processing: "処理中...",
  }
};

let lCurve = null, ssCurve = null, lsCurve = null;
let viewer = null;
let isProcessing = false;
let pendingRequest = false;

document.addEventListener('DOMContentLoaded', () => {
  lCurve = new ToneCurveEditor('curve-canvas', () => {
    if (state.lightnessMode !== 'curve') setLightnessMode('curve');
    onAnyChange();
  });
  lCurve.labels = [
    { text: '明度 (後)', chipColor: 'rgba(129, 140, 248, 0.8)' },
    { text: '明度 (元)', chipColor: 'rgba(255, 255, 255, 0.4)' }
  ];
  viewer = new ImageViewer('viewer-panel');

  ssCurve = new ToneCurveEditor('ss-curve-canvas', () => {
    if (state.saturationMode !== 'curve') setSaturationMode('curve');
    onAnyChange();
  });
  ssCurve.labels = [
    { text: '彩度 (後)', chipColor: 'rgba(244, 114, 182, 0.8)' },
    { text: '彩度 (元)', chipColor: 'rgba(255, 255, 255, 0.4)' }
  ];

  lsCurve = new ToneCurveEditor('ls-curve-canvas', () => {
    if (state.saturationMode !== 'curve') setSaturationMode('curve');
    onAnyChange();
  });
  updateLabels();
  updateUI();

  document.getElementById('btn-lang-jp')?.addEventListener('click', () => setLanguage('ja'));
  document.getElementById('btn-lang-en')?.addEventListener('click', () => setLanguage('en'));

  setupBgSwitcher();
  lsCurve.points = [{ x: 0, y: 0.5, locked: true }, { x: 1, y: 0.5, locked: true }];
  lsCurve.draw();

  viewer.onPixelSample = (color) => {
    // color has { h, s, l, r, g, b } (Okhsl)
    // L curve: input is l
    lCurve.setIndicator(color.l);

    // S curve: input is s (already 0-1)
    ssCurve.setIndicator(color.s);

    // l-S curve: input is l
    lsCurve.setIndicator(color.l);
  };

  setupUpload();
  setupToolbar();
  setupHueSlider();
  setupExportControls();

  window.addEventListener('resize', () => {
    if (state.lightnessMode === 'curve') lCurve.resize();
    if (state.saturationMode === 'curve') { ssCurve.resize(); lsCurve.resize(); }
    viewer.resize();
  });

  document.getElementById('btn-reset-curve')?.addEventListener('click', () => lCurve.reset());
  document.getElementById('btn-reset-saturation')?.addEventListener('click', resetSaturation);
  document.getElementById('btn-reset-hue')?.addEventListener('click', resetHue);
  document.getElementById('btn-load-image')?.addEventListener('click', () => {
    document.getElementById('file-input')?.click();
  });

  // View controls
  document.getElementById('btn-zoom-in')?.addEventListener('click', () => viewer.zoomIn());
  document.getElementById('btn-zoom-out')?.addEventListener('click', () => viewer.zoomOut());
  document.getElementById('btn-zoom-fit')?.addEventListener('click', () => viewer.zoomFit());
  document.getElementById('btn-zoom-11')?.addEventListener('click', () => viewer.zoom11());

  document.getElementById('btn-export')?.addEventListener('click', exportImage);
});

// ── Upload ──
function setupUpload() {
  const zone = document.getElementById('upload-zone');
  const fileInput = document.getElementById('file-input');
  if (!zone || !fileInput) return;
  zone.addEventListener('click', () => fileInput.click());
  zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('dragover'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('dragover'));
  zone.addEventListener('drop', e => {
    e.preventDefault(); zone.classList.remove('dragover');
    if (e.dataTransfer.files.length > 0) uploadFile(e.dataTransfer.files[0]);
  });
  fileInput.addEventListener('change', e => {
    if (e.target.files.length > 0) uploadFile(e.target.files[0]);
    e.target.value = '';
  });
}

async function uploadFile(file) {
  showLoading(true);
  const fd = new FormData(); fd.append('file', file);
  try {
    const res = await fetch(`${API_BASE}/api/upload`, { method: 'POST', body: fd });
    if (!res.ok) throw new Error(`Upload failed (${res.status}): ${await res.text()}`);
    const data = await res.json();
    state.sessionId = data.session_id;
    state.imageInfo = {
      width: data.width, height: data.height,
      preview_width: data.preview_width, preview_height: data.preview_height,
      format: data.format, bitDepth: data.bit_depth
    };
    const fmtMap = {JPEG:'jpeg',JPG:'jpeg',PNG:'png',TIFF:'tiff',TIF:'tiff',WEBP:'webp',AVIF:'avif',HEIC:'jpeg',HEIF:'jpeg',DNG:'tiff'};
    state.outputFormat = fmtMap[data.format] || 'jpeg';
    state.bitDepth = data.bit_depth;
    updateImageInfo(); updateFormatSelect();
    const url = `data:image/png;base64,${data.preview}`;
    viewer.setOriginalImage(url); viewer.setProcessedImage(url);
    if (data.histogram) updateHistograms(data.histogram);
    document.getElementById('upload-overlay')?.classList.add('hidden');
    lCurve.reset(); resetSaturation(); resetHue();
    setControlsEnabled(true);
    // Enable dithering checkbox
    const d = document.getElementById('check-dithering');
    if (d) d.disabled = false;
  } catch (err) {
    console.error('Upload error:', err); alert('アップロード失敗: ' + err.message);
  } finally { showLoading(false); }
}

// ── Toolbar ──
function setupToolbar() {
  document.getElementById('btn-toggle-original')?.addEventListener('click', () => {
    state.showOriginal = !state.showOriginal;
    if (state.showOriginal) state.splitView = false;
    updateToolbarUI(); viewer.setShowOriginal(state.showOriginal);
  });
  document.getElementById('btn-toggle-split')?.addEventListener('click', () => {
    console.log("App: Split button clicked. Current state:", state.splitView);
    state.splitView = !state.splitView;
    if (state.splitView) state.showOriginal = false;
    updateToolbarUI(); viewer.setSplitEnabled(state.splitView);
  });
  document.getElementById('btn-toggle-sat-map')?.addEventListener('click', () => {
    state.showSatMap = !state.showSatMap; updateToolbarUI(); debouncePreview();
  });
}

function setLanguage(lang) {
  state.lang = lang;
  localStorage.setItem('lang', lang);
  document.documentElement.lang = lang;
  updateUI();
  updateLabels();
  lCurve.draw();
  ssCurve.draw();
  lsCurve.draw();
}

function updateUI() {
  const dict = i18n[state.lang];
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.getAttribute('data-i18n');
    if (dict[key]) {
      // Preserve icons but exclude CJK characters (Kanji, Hiragana, Katakana)
      const iconMatch = el.innerHTML.match(/^(?:&#x[0-9a-fA-F]+;|[\uD800-\uDBFF][\uDC00-\uDFFF]|[^\w\s\u4e00-\u9faf\u3040-\u309f\u30a0-\u30ff\uff00-\uffef])/);
      if (iconMatch) {
        el.innerHTML = iconMatch[0] + ' ' + dict[key].replace(/^[^\w\s]+\s*/, '');
      } else {
        el.textContent = dict[key];
      }
    }
  });
  document.getElementById('btn-lang-jp')?.classList.toggle('active', state.lang === 'ja');
  document.getElementById('btn-lang-en')?.classList.toggle('active', state.lang === 'en');
}

function updateLabels() {
  const dict = i18n[state.lang];
  lCurve.labels = [
    { text: dict.label_adj_l, chipColor: 'rgba(129, 140, 248, 0.8)' },
    { text: dict.label_orig_l, chipColor: 'rgba(255, 255, 255, 0.4)' }
  ];
  ssCurve.labels = [
    { text: dict.label_adj_s, chipColor: 'rgba(244, 114, 182, 0.8)' },
    { text: dict.label_orig_s, chipColor: 'rgba(255, 255, 255, 0.4)' }
  ];
  lsCurve.labels = [
    { text: dict.label_final_s, chipColor: 'rgba(244, 114, 182, 0.8)' },
    { text: dict.label_adj_l, chipColor: 'rgba(129, 140, 248, 0.8)' }
  ];
}

function setupBgSwitcher() {
  const btns = document.querySelectorAll('.bg-btn');
  const panel = document.getElementById('viewer-panel');
  btns.forEach(btn => {
    btn.addEventListener('click', () => {
      const color = btn.getAttribute('data-bg');
      if (panel) panel.style.background = color;
      btns.forEach(b => b.classList.toggle('active', b === btn));
      localStorage.setItem('viewerBg', color);
    });
  });
  // Restore saved bg
  const saved = localStorage.getItem('viewerBg');
  if (saved && panel) {
    panel.style.background = saved;
    btns.forEach(b => b.classList.toggle('active', b.getAttribute('data-bg') === saved));
  }
}

function updateToolbarUI() {
  const dict = i18n[state.lang];
  const o = document.getElementById('btn-toggle-original');
  const s = document.getElementById('btn-toggle-sat-map');
  const sp = document.getElementById('btn-toggle-split');
  if (o) {
    const label = state.showOriginal ? `${dict.original} ON` : dict.original;
    o.textContent = `👁 ${label}`;
    o.classList.toggle('active', state.showOriginal);
  }
  if (s) { s.classList.toggle('active', state.showSatMap); }
  if (sp) { sp.classList.toggle('active', state.splitView); }
}

function resetLightness() {
  state.lightnessShift = 0; state.lightnessMode = 'curve';
  lCurve?.reset();
}

// ── Saturation ──
function resetSaturation() {
  state.saturationScale = 1.0; state.saturationMode = 'curve';
  ssCurve?.reset();
  if (lsCurve) { lsCurve.points = [{ x: 0, y: 0.5, locked: true }, { x: 1, y: 0.5, locked: true }]; lsCurve.draw(); }
}

// ── Hue ──
function setupHueSlider() {
  const sl = document.getElementById('range-hue');
  const vl = document.getElementById('hue-value');
  sl?.addEventListener('input', e => {
    state.hueShift = parseInt(e.target.value);
    if (vl) vl.textContent = state.hueShift + '°';
    debouncePreview();
  });
}

function resetHue() {
  state.hueShift = 0;
  const s = document.getElementById('range-hue'), v = document.getElementById('hue-value');
  if (s) s.value = 0; if (v) v.textContent = '0°';
  debouncePreview();
}

// ── Preview ──
function onAnyChange() { debouncePreview(); }

function debouncePreview() {
  if (!state.sessionId) return;
  clearTimeout(state.debounceTimer);
  state.debounceTimer = setTimeout(requestPreview, 150);
}

async function requestPreview() {
  if (!state.sessionId) return;
  if (isProcessing) {
    pendingRequest = true;
    return;
  }
  isProcessing = true;
  pendingRequest = false;
  const loadingEl = document.getElementById('preview-loading');
  if (loadingEl) loadingEl.style.display = 'inline-block';
  try {
    const res = await fetch(`${API_BASE}/api/preview`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: state.sessionId,
        control_points: lCurve.getControlPoints(),
        lightness_mode: state.lightnessMode,
        lightness_shift: state.lightnessShift,
        color_space: state.colorSpace,
        saturation_mode: state.saturationMode,
        saturation_scale: state.saturationScale,
        ss_points: state.saturationMode === 'curve' ? ssCurve.getControlPoints() : [],
        ls_points: state.saturationMode === 'curve' ? lsCurve.getControlPoints() : [],
        hue_shift: state.hueShift,
        view_mode: state.showSatMap ? 'saturation' : 'color',
      }),
    });
    if (!res.ok) throw new Error(`Preview: ${res.status}`);
    const data = await res.json();
    viewer.setProcessedImage(`data:image/png;base64,${data.preview}`);
    if (data.histogram) updateHistograms(data.histogram);
  } catch (err) {
    console.error('Preview error:', err);
  } finally {
    isProcessing = false;
    if (loadingEl) loadingEl.style.display = 'none';
    if (pendingRequest) {
      requestPreview();
    }
  }
}

function updateHistograms(hist) {
  if (!hist) return;
  // Okhsl lightness histogram
  if (hist.okhsl_l) {
    lCurve.setHistogram(hist.okhsl_l, 'rgba(255, 255, 255, 0.12)', hist.okhsl_l_adj, 'rgba(129, 140, 248, 0.2)');
    // LxS: Bottom = Lightness Adjusted (Indigo), Top = Saturation Adjusted (Rose)
    lsCurve.setHistogram(hist.okhsl_l_adj, 'rgba(129, 140, 248, 0.15)', hist.okhsl_s_adj, 'rgba(244, 114, 182, 0.2)');
  }
  // Okhsl saturation histogram
  if (hist.okhsl_s) {
    // Top histogram shows saturation after SxS (intermediate)
    const s_adj = hist.okhsl_s_after_ss || hist.okhsl_s_adj;
    ssCurve.setHistogram(hist.okhsl_s, 'rgba(255, 255, 255, 0.12)', s_adj, 'rgba(244, 114, 182, 0.2)');
  }
}

// ── Export ──
async function exportImage() {
  if (!state.sessionId) return;
  showLoading(true);
  try {
    const res = await fetch(`${API_BASE}/api/export`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: state.sessionId,
        control_points: lCurve.getControlPoints(),
        lightness_mode: state.lightnessMode,
        lightness_shift: state.lightnessShift,
        color_space: state.colorSpace, saturation_mode: state.saturationMode,
        saturation_scale: state.saturationScale,
        ss_points: state.saturationMode === 'curve' ? ssCurve.getControlPoints() : [],
        ls_points: state.saturationMode === 'curve' ? lsCurve.getControlPoints() : [],
        hue_shift: state.hueShift,
        output_format: state.outputFormat, quality: state.quality,
        bit_depth: state.bitDepth, tiff_compression: state.tiffCompression,
        use_dithering: document.getElementById('check-dithering')?.checked ?? true,
      }),
    });
    if (!res.ok) throw new Error(`Export: ${res.status}`);
    const blob = await res.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = `exported.${state.outputFormat}`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(a.href);
  } catch (err) {
    console.error('Export error:', err); alert('エクスポート失敗: ' + err.message);
  } finally { showLoading(false); }
}

// ── Export Controls ──
function setupExportControls() {
  document.getElementById('select-color-space')?.addEventListener('change', e => { state.colorSpace = e.target.value; debouncePreview(); });
  document.getElementById('select-format')?.addEventListener('change', e => { state.outputFormat = e.target.value; updateFormatOptions(); updateProcessingBadge(); });
  document.getElementById('range-quality')?.addEventListener('input', e => { state.quality = parseInt(e.target.value); document.getElementById('quality-value').textContent = state.quality; });
  document.getElementById('select-bit-depth')?.addEventListener('change', e => { state.bitDepth = parseInt(e.target.value); updateProcessingBadge(); });
  document.getElementById('select-compression')?.addEventListener('change', e => { state.tiffCompression = e.target.value; });
}

function updateFormatSelect() { const s = document.getElementById('select-format'); if (s) s.value = state.outputFormat; updateFormatOptions(); }

function updateFormatOptions() {
  const f = state.outputFormat;
  const q = document.getElementById('quality-group'), b = document.getElementById('bit-depth-group'), c = document.getElementById('compression-group');
  if (q) q.style.display = ['jpeg','webp','avif'].includes(f) ? 'block' : 'none';
  if (b) b.style.display = ['tiff','png'].includes(f) ? 'block' : 'none';
  if (c) c.style.display = f === 'tiff' ? 'block' : 'none';
  updateProcessingBadge();
}

function updateProcessingBadge() {
  const el = document.getElementById('processing-badge');
  if (!el) return;
  const is32bit = (state.outputFormat === 'tiff' || state.outputFormat === 'tif') && state.bitDepth === 16;
  el.textContent = is32bit ? '32-bit Float' : '16-bit Float';
}

// ── UI ──
function updateImageInfo() {
  const el = document.getElementById('image-info');
  if (!el || !state.imageInfo) return;
  el.innerHTML = `
    <div class="info-item"><span class="info-label">ORIG:</span> <span class="info-value">${state.imageInfo.width}×${state.imageInfo.height}</span> <span style="margin-left:8px; opacity:0.7;">${state.imageInfo.format} ${state.imageInfo.bitDepth}bit</span></div>
    <div class="info-item"><span class="info-label">PREV:</span> <span class="info-value">${state.imageInfo.preview_width}×${state.imageInfo.preview_height}</span></div>`;
}
function showLoading(show) { document.getElementById('loading-overlay')?.classList.toggle('active', show); }
function setControlsEnabled(en) {
  console.log("Setting controls enabled:", en);
  const elements = document.querySelectorAll('.control-panel select, .control-panel input, .control-panel button, .toolbar-btn, .form-range');
  elements.forEach(el => {
    el.disabled = !en;
    if (en) el.removeAttribute('disabled');
    else el.setAttribute('disabled', 'disabled');
  });
  
  // Explicitly target toggle buttons
  ['btn-toggle-original', 'btn-toggle-sat-map', 'btn-toggle-split'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.disabled = !en;
  });
  
  // Explicitly target the remaining sliders (Hue)
  const rangeH = document.getElementById('range-hue');
  if (rangeH) {
    rangeH.disabled = !en;
    rangeH.style.pointerEvents = en ? 'auto' : 'none';
    rangeH.style.opacity = en ? '1' : '0.4';
  }

  if (lCurve) lCurve.setEnabled(en);
  if (ssCurve) ssCurve.setEnabled(en);
  if (lsCurve) lsCurve.setEnabled(en);
  
  updateToolbarUI();
}
