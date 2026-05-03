/**
 * image-viewer.js — 画像ビューア (Okhsl版)
 *
 * 分割比較表示機能を追加。
 */

class ImageViewer {
  constructor(containerId) {
    this.container = document.getElementById(containerId);
    this.canvas = document.getElementById('viewer-canvas');
    this.labelRight = document.getElementById('label-right');

    this.originalImg = null;
    this.processedImg = null;

    this.canvasWidth = 0;
    this.canvasHeight = 0;

    this.zoom = 1.0;
    this.panX = 0;
    this.panY = 0;
    this._wasDragging = false;

    this.showOriginal = false;
    this.splitEnabled = false;
    this.splitRatio = 0.5;

    // Pixel sampling callback
    this.onPixelSample = null;
    // Hidden canvas for pixel sampling from original image
    this._sampleCanvas = document.createElement('canvas');
    this._sampleCtx = this._sampleCanvas.getContext('2d', { willReadFrequently: true });

    this._bindPixelSample();
    this._bindPanning();
  }

  zoomIn() {
    this.zoom = Math.min(this.zoom * 1.5, 20.0);
    this._applyTransform();
  }

  zoomOut() {
    this.zoom = Math.max(this.zoom / 1.5, 0.1);
    this._applyTransform();
  }

  zoomFit() {
    this.zoom = 1.0;
    this.panX = 0;
    this.panY = 0;
    this._applyTransform();
  }

  zoom11() {
    if (!this.originalImg) return;
    const rect = this.container.getBoundingClientRect();
    const baseScale = Math.min(rect.width / this.originalImg.width, rect.height / this.originalImg.height, 1);
    this.zoom = 1.0 / baseScale;
    this.panX = 0;
    this.panY = 0;
    this._applyTransform();
  }

  _applyTransform() {
    const cc = this.container.querySelector('.viewer-canvas-container');
    if (cc) {
      cc.style.transform = `translate(${this.panX}px, ${this.panY}px) scale(${this.zoom})`;
      cc.style.transformOrigin = 'center center';
    }
  }

  setOriginalImage(url) {
    this._loadImg(url, (img) => {
      this.originalImg = img;
      // Update hidden sampling canvas
      this._sampleCanvas.width = img.width;
      this._sampleCanvas.height = img.height;
      this._sampleCtx.drawImage(img, 0, 0);
      this._updateAll();
    });
  }

  setProcessedImage(url) {
    this._loadImg(url, (img) => { this.processedImg = img; this._updateAll(); });
  }

  setShowOriginal(show) {
    this.showOriginal = show;
    if (show) this.splitEnabled = false; // Disable split if full original
    this._updateAll();
  }

  setSplitEnabled(enabled) {
    console.log("ImageViewer: setSplitEnabled =", enabled);
    this.splitEnabled = enabled;
    if (enabled) this.showOriginal = false;
    this._updateAll();
  }

  resize() {
    this._updateCanvasSize();
    this._drawAll();
  }

  // ── Internal ──

  _loadImg(url, cb) {
    const img = new Image();
    img.onload = () => cb(img);
    img.src = url;
  }

  _updateAll() {
    this._updateCanvasSize();
    this._drawAll();
    this._updateLabels();
  }

  _updateCanvasSize() {
    const ref = this.originalImg || this.processedImg;
    if (!ref) return;

    const rect = this.container.getBoundingClientRect();
    const scale = Math.min(rect.width / ref.width, rect.height / ref.height, 1);
    this.canvasWidth = Math.floor(ref.width * scale);
    this.canvasHeight = Math.floor(ref.height * scale);

    const dpr = window.devicePixelRatio || 1;
    if (this.canvas) {
      this.canvas.style.width = this.canvasWidth + 'px';
      this.canvas.style.height = this.canvasHeight + 'px';
      this.canvas.width = this.canvasWidth * dpr;
      this.canvas.height = this.canvasHeight * dpr;
    }

    const cc = this.container.querySelector('.viewer-canvas-container');
    if (cc) {
      cc.style.width = this.canvasWidth + 'px';
      cc.style.height = this.canvasHeight + 'px';
      this._applyTransform();
    }
  }

  _drawAll() {
    const dpr = window.devicePixelRatio || 1;
    if (!this.canvas) return;
    const ctx = this.canvas.getContext('2d');
    const w = this.canvas.width;
    const h = this.canvas.height;
    ctx.clearRect(0, 0, w, h);

    const img1 = this.originalImg;
    const img2 = this.processedImg || this.originalImg;
    if (!img1 || !img2) return;

    ctx.save();
    ctx.scale(dpr, dpr);

    if (this.splitEnabled) {
      const splitX = this.canvasWidth * this.splitRatio;

      // 1. Draw original on left half (source-cropped)
      const sWidth1 = img1.width * this.splitRatio;
      ctx.drawImage(img1, 0, 0, sWidth1, img1.height, 0, 0, splitX, this.canvasHeight);

      // 2. Draw processed on right half (source-cropped)
      const sStartX2 = img2.width * this.splitRatio;
      const sWidth2 = img2.width * (1 - this.splitRatio);
      ctx.drawImage(img2, sStartX2, 0, sWidth2, img2.height, splitX, 0, this.canvasWidth - splitX, this.canvasHeight);

      // 3. Draw visible divider line
      ctx.beginPath();
      ctx.strokeStyle = '#ffffff';
      ctx.lineWidth = 2;
      ctx.moveTo(splitX, 0);
      ctx.lineTo(splitX, this.canvasHeight);
      ctx.stroke();

      // 4. Draw handle
      const hy = this.canvasHeight / 2;
      ctx.beginPath();
      ctx.arc(splitX, hy, 18, 0, Math.PI * 2);
      ctx.fillStyle = '#ffffff';
      ctx.fill();
      ctx.strokeStyle = '#000000';
      ctx.lineWidth = 1;
      ctx.stroke();
      
      ctx.fillStyle = '#000';
      ctx.font = 'bold 16px sans-serif';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText('◀▶', splitX, hy);
    } else {
      const img = this.showOriginal ? img1 : img2;
      ctx.drawImage(img, 0, 0, this.canvasWidth, this.canvasHeight);
    }

    ctx.restore();
  }

  _updateLabels() {
    if (this.labelRight) {
      if (this.splitEnabled) {
        this.labelRight.innerHTML = `<span style="opacity:0.6">Original</span> | Okhsl`;
      } else {
        this.labelRight.textContent = this.showOriginal ? 'Original' : 'Okhsl';
      }
    }
  }

  _bindPixelSample() {
    const cc = this.container.querySelector('.viewer-canvas-container');
    if (!cc) return;

    cc.addEventListener('click', (e) => {
      if (!this.originalImg || !this.onPixelSample || this._wasDragging || this._isSplitDragging) return;

      const rect = cc.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      const clickY = e.clientY - rect.top;

      const imgX = Math.floor((clickX / rect.width) * this.originalImg.width);
      const imgY = Math.floor((clickY / rect.height) * this.originalImg.height);

      if (imgX < 0 || imgX >= this.originalImg.width || imgY < 0 || imgY >= this.originalImg.height) return;

      const pixel = this._sampleCtx.getImageData(imgX, imgY, 1, 1).data;
      const r = pixel[0], g = pixel[1], b = pixel[2];

      if (typeof ColorUtils !== 'undefined') {
        const okhsl = ColorUtils.srgbToOkhsl(r, g, b);
        this.onPixelSample({ r, g, b, h: okhsl.h, s: okhsl.s, l: okhsl.l });
      }
    });
  }

  _bindPanning() {
    let isPanning = false;
    let isSplitDragging = false;
    let startX, startY;
    let startPanX, startPanY;

    const start = (e) => {
      if (e.target.closest('.viewer-controls') || e.target.closest('.viewer-label')) return;
      
      const rect = this.container.getBoundingClientRect();
      const clientX = e.touches ? e.touches[0].clientX : e.clientX;
      const clientY = e.touches ? e.touches[0].clientY : e.clientY;
      
      // Check if clicking near the split handle
      if (this.splitEnabled) {
        const cc = this.container.querySelector('.viewer-canvas-container');
        const ccRect = cc.getBoundingClientRect();
        const splitX_screen = ccRect.left + (ccRect.width * this.splitRatio);
        const mouseX_rel = clientX - splitX_screen;
        
        if (Math.abs(mouseX_rel) < 20) {
          isSplitDragging = true;
          this._isSplitDragging = true;
          this.container.style.cursor = 'col-resize';
          return;
        }
      }

      isPanning = true;
      startX = clientX;
      startY = clientY;
      startPanX = this.panX;
      startPanY = this.panY;
      this.container.style.cursor = 'grabbing';
    };

    const move = (e) => {
      const x = e.touches ? e.touches[0].clientX : e.clientX;
      const y = e.touches ? e.touches[0].clientY : e.clientY;

      if (isSplitDragging) {
        const cc = this.container.querySelector('.viewer-canvas-container');
        const ccRect = cc.getBoundingClientRect();
        const relX = (x - ccRect.left) / ccRect.width;
        this.splitRatio = Math.max(0.01, Math.min(0.99, relX));
        this._drawAll();
        return;
      }

      if (!isPanning) return;
      e.preventDefault();
      this.panX = startPanX + (x - startX);
      this.panY = startPanY + (y - startY);
      this._applyTransform();
    };

    const end = (e) => {
      if (!isPanning && !isSplitDragging) return;
      isPanning = false;
      isSplitDragging = false;
      setTimeout(() => this._isSplitDragging = false, 50);
      this.container.style.cursor = '';

      if (startX !== undefined) {
        const x = e.changedTouches ? e.changedTouches[0].clientX : e.clientX;
        const y = e.changedTouches ? e.changedTouches[0].clientY : e.clientY;
        const dist = Math.hypot(x - startX, y - startY);
        if (dist > 5) {
          this._wasDragging = true;
          setTimeout(() => this._wasDragging = false, 50);
        }
      }
    };

    this.container.addEventListener('mousedown', start);
    this.container.addEventListener('touchstart', start, { passive: false });
    window.addEventListener('mousemove', move);
    window.addEventListener('touchmove', move, { passive: false });
    window.addEventListener('mouseup', end);
    window.addEventListener('touchend', end);

    this.container.addEventListener('wheel', (e) => {
      e.preventDefault();
      const zoomFactor = Math.exp(-e.deltaY * 0.003);
      const rect = this.container.getBoundingClientRect();
      const mouseX = e.clientX - rect.left - rect.width / 2;
      const mouseY = e.clientY - rect.top - rect.height / 2;
      const newZoom = Math.min(Math.max(this.zoom * zoomFactor, 0.1), 20.0);
      const ratio = newZoom / this.zoom;
      this.panX = mouseX - (mouseX - this.panX) * ratio;
      this.panY = mouseY - (mouseY - this.panY) * ratio;
      this.zoom = newZoom;
      this._applyTransform();
    }, { passive: false });
  }
}
