/**
 * tone-curve.js — トーンカーブ Canvas UI
 *
 * 制御点のドラッグ操作、Cubic Spline 描画、LUT 生成を担当。
 */

class ToneCurveEditor {
  constructor(canvasId, onChange) {
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas.getContext('2d');
    this.onChange = onChange;

    // High-DPI support
    this.dpr = window.devicePixelRatio || 1;
    this.padding = 1;

    // Control points (normalized 0-1)
    this.points = [
      { x: 0, y: 0, locked: true },
      { x: 1, y: 1, locked: true },
    ];

    this.dragging = null;
    this.hovered = null;
    this.pointRadius = 6;

    // Indicator line (pixel sample)
    this.indicator = null;  // { value: 0-1 } or null
    this.indicatorColor = 'rgba(251, 191, 36, 0.7)';  // amber
    this.labels = []; // Array of { text: string, color: string }
    this.axisXTitle = '';
    this.axisYTitle = '';

    // Histogram
    this.histogramData = null;
    this.histogramColor = 'rgba(255, 255, 255, 0.15)';
    this.histogramAdjData = null;
    this.histogramAdjColor = 'rgba(129, 140, 248, 0.25)';

    this._setupCanvas();
    this._bindEvents();
    this.enabled = true;
    this.draw();
  }

  setEnabled(enabled) {
    this.enabled = enabled;
    this.canvas.style.pointerEvents = enabled ? 'auto' : 'none';
    this.canvas.style.opacity = enabled ? '1' : '0.6';
  }

  _setupCanvas() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    const w = Math.floor(rect.width);
    const h = w; // Force square aspect ratio
    this.canvas.style.width = w + 'px';
    this.canvas.style.height = h + 'px';
    this.canvas.width = w * this.dpr;
    this.canvas.height = h * this.dpr;
    this.width = w;
    this.height = h;
    this.size = w; // for backward compat
    this.ctx.scale(this.dpr, this.dpr);
  }

  resize() {
    this._setupCanvas();
    this.draw();
  }

  // Convert normalized (0-1) to canvas px
  _toCanvas(nx, ny) {
    const p = this.padding;
    const w = this.width - p * 2;
    const h = this.height - p * 2;
    return {
      x: p + nx * w,
      y: p + (1 - ny) * h,
    };
  }

  // Convert canvas px to normalized
  _toNorm(cx, cy) {
    const p = this.padding;
    const w = this.width - p * 2;
    const h = this.height - p * 2;
    return {
      x: Math.max(0, Math.min(1, (cx - p) / w)),
      y: Math.max(0, Math.min(1, 1 - (cy - p) / h)),
    };
  }

  _getMousePos(e) {
    const rect = this.canvas.getBoundingClientRect();
    return {
      x: (e.clientX - rect.left),
      y: (e.clientY - rect.top),
    };
  }

  _findPoint(mx, my) {
    const threshold = 12;
    for (let i = 0; i < this.points.length; i++) {
      const cp = this._toCanvas(this.points[i].x, this.points[i].y);
      const dx = mx - cp.x;
      const dy = my - cp.y;
      if (Math.sqrt(dx * dx + dy * dy) < threshold) {
        return i;
      }
    }
    return -1;
  }

  _bindEvents() {
    this.canvas.addEventListener('mousedown', (e) => {
      const pos = this._getMousePos(e);
      const idx = this._findPoint(pos.x, pos.y);

      if (idx >= 0) {
        if (e.button === 2 && !this.points[idx].locked) {
          // Right-click to delete
          e.preventDefault();
          this.points.splice(idx, 1);
          this.draw();
          this._notify();
          return;
        }
        this.dragging = idx;
      } else {
        // Add new point
        const norm = this._toNorm(pos.x, pos.y);
        this.points.push({ x: norm.x, y: norm.y, locked: false });
        this.points.sort((a, b) => a.x - b.x);
        this.dragging = this.points.findIndex(
          (p) => p.x === norm.x && p.y === norm.y
        );
        this.draw();
        this._notify();
      }
    });

    this.canvas.addEventListener('mousemove', (e) => {
      const pos = this._getMousePos(e);

      if (this.dragging !== null) {
        const norm = this._toNorm(pos.x, pos.y);
        const pt = this.points[this.dragging];

        if (pt.locked) {
          // Locked points: only move y
          pt.y = norm.y;
        } else {
          // Don't cross neighbors
          const prev = this.dragging > 0 ? this.points[this.dragging - 1].x + 0.005 : 0;
          const next =
            this.dragging < this.points.length - 1
              ? this.points[this.dragging + 1].x - 0.005
              : 1;
          pt.x = Math.max(prev, Math.min(next, norm.x));
          pt.y = norm.y;
        }
        this.draw();
        this._notify();
      } else {
        const idx = this._findPoint(pos.x, pos.y);
        if (idx !== this.hovered) {
          this.hovered = idx >= 0 ? idx : null;
          this.canvas.style.cursor = idx >= 0 ? 'grab' : 'crosshair';
          this.draw();
        }
      }
    });

    this.canvas.addEventListener('mouseup', () => {
      this.dragging = null;
      this.canvas.style.cursor = 'crosshair';
    });

    this.canvas.addEventListener('mouseleave', () => {
      this.dragging = null;
      this.hovered = null;
      this.canvas.style.cursor = 'crosshair';
      this.draw();
    });

    this.canvas.addEventListener('contextmenu', (e) => e.preventDefault());

    // Touch support
    this.canvas.addEventListener('touchstart', (e) => {
      e.preventDefault();
      const touch = e.touches[0];
      const rect = this.canvas.getBoundingClientRect();
      const pos = { x: touch.clientX - rect.left, y: touch.clientY - rect.top };
      const idx = this._findPoint(pos.x, pos.y);

      if (idx >= 0) {
        this.dragging = idx;
      } else {
        const norm = this._toNorm(pos.x, pos.y);
        this.points.push({ x: norm.x, y: norm.y, locked: false });
        this.points.sort((a, b) => a.x - b.x);
        this.dragging = this.points.findIndex(
          (p) => p.x === norm.x && p.y === norm.y
        );
        this.draw();
        this._notify();
      }
    }, { passive: false });

    this.canvas.addEventListener('touchmove', (e) => {
      e.preventDefault();
      if (this.dragging === null) return;
      const touch = e.touches[0];
      const rect = this.canvas.getBoundingClientRect();
      const pos = { x: touch.clientX - rect.left, y: touch.clientY - rect.top };
      const norm = this._toNorm(pos.x, pos.y);
      const pt = this.points[this.dragging];

      if (pt.locked) {
        pt.y = norm.y;
      } else {
        const prev = this.dragging > 0 ? this.points[this.dragging - 1].x + 0.005 : 0;
        const next =
          this.dragging < this.points.length - 1
            ? this.points[this.dragging + 1].x - 0.005
            : 1;
        pt.x = Math.max(prev, Math.min(next, norm.x));
        pt.y = norm.y;
      }
      this.draw();
      this._notify();
    }, { passive: false });

    this.canvas.addEventListener('touchend', () => {
      this.dragging = null;
    });

    // Double-click to delete
    this.canvas.addEventListener('dblclick', (e) => {
      const pos = this._getMousePos(e);
      const idx = this._findPoint(pos.x, pos.y);
      if (idx >= 0 && !this.points[idx].locked) {
        this.points.splice(idx, 1);
        this.draw();
        this._notify();
      }
    });
  }

  _notify() {
    if (this.onChange) {
      this.onChange(this.getControlPoints());
    }
  }

  getControlPoints() {
    return this.points.map((p) => [p.x, p.y]);
  }

  reset() {
    this.points = [
      { x: 0, y: 0, locked: true },
      { x: 1, y: 1, locked: true },
    ];
    this.indicator = null;
    this.draw();
    this._notify();
  }

  /**
   * Set indicator line at normalized value (0-1).
   * Shows a vertical line at the input value and
   * a horizontal crosshair at the curve's output.
   */
  setIndicator(value) {
    this.indicator = value != null ? { value: Math.max(0, Math.min(1, value)) } : null;
    this.draw();
  }

  clearIndicator() {
    this.indicator = null;
    this.draw();
  }

  setHistogram(data, color, adjData, adjColor) {
    this.histogramData = data;
    this.histogramAdjData = adjData || null;
    if (color) this.histogramColor = color;
    if (adjColor) this.histogramAdjColor = adjColor;
    this.draw();
  }

  // ── Drawing ──

  draw() {
    const ctx = this.ctx;
    const w = this.width;
    const h = this.height;
    const p = this.padding;
    const areaW = w - p * 2;
    const areaH = h - p * 2;

    ctx.clearRect(0, 0, w, h);

    // Background
    ctx.fillStyle = '#080c14';
    ctx.fillRect(0, 0, w, h);

    // Histogram
    this._drawHistogram(ctx, p, areaW, areaH);

    // Grid
    this._drawGrid(ctx, p, areaW, areaH);

    // Diagonal guide
    ctx.beginPath();
    ctx.strokeStyle = 'rgba(148, 163, 184, 0.12)';
    ctx.lineWidth = 1;
    ctx.moveTo(p, p + areaH);
    ctx.lineTo(p + areaW, p);
    ctx.stroke();

    // Curve
    this._drawCurve(ctx, p, areaW, areaH);

    // Indicator
    this._drawIndicator(ctx, p, areaW, areaH);

    // Points
    this._drawPoints(ctx);

    // Labels
    this._drawLabels(ctx, p);
  }

  _drawLabels(ctx, p) {
    if (!this.labels || this.labels.length === 0) return;
    ctx.save();
    ctx.font = 'bold 14px "Inter", "Roboto", sans-serif';
    ctx.textBaseline = 'middle';
    let yOffset = p + 14;
    for (const label of this.labels) {
      // Color chip
      ctx.fillStyle = label.chipColor || label.color || 'rgba(255, 255, 255, 0.7)';
      ctx.fillRect(p + 10, yOffset - 4, 8, 8);
      
      // Text
      ctx.fillStyle = 'rgba(255, 255, 255, 0.8)';
      ctx.fillText(label.text, p + 22, yOffset);
      yOffset += 18;
    }
    ctx.restore();
  }

  _drawIndicator(ctx, p, areaW, areaH) {
    if (!this.indicator) return;
    const val = this.indicator.value;
    const color = this.indicatorColor;

    // Vertical line at input value
    const xPx = p + val * areaW;
    ctx.save();
    ctx.setLineDash([4, 3]);
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(xPx, p);
    ctx.lineTo(xPx, p + areaH);
    ctx.stroke();

    // Find curve output at this input value
    const curvePoints = this._interpolate(200);
    let outY = val; // fallback to identity
    for (let i = 0; i < curvePoints.length - 1; i++) {
      if (curvePoints[i].x <= val && curvePoints[i + 1].x >= val) {
        const t = (val - curvePoints[i].x) / (curvePoints[i + 1].x - curvePoints[i].x);
        outY = curvePoints[i].y + t * (curvePoints[i + 1].y - curvePoints[i].y);
        break;
      }
    }

    // Horizontal line at output value
    const yPx = p + (1 - outY) * areaH;
    ctx.beginPath();
    ctx.moveTo(p, yPx);
    ctx.lineTo(p + areaW, yPx);
    ctx.stroke();
    ctx.setLineDash([]);

    // Crosshair dot
    ctx.beginPath();
    ctx.arc(xPx, yPx, 4, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = '#000';
    ctx.lineWidth = 1;
    ctx.stroke();

    // Value labels
    ctx.fillStyle = color;
    ctx.font = '13px Inter, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(val.toFixed(2), xPx, p + areaH + 12);
    ctx.textAlign = 'right';
    ctx.fillText(outY.toFixed(2), p - 4, yPx + 3);

    ctx.restore();
  }

  _drawHistogram(ctx, p, areaW, areaH) {
    if (!this.histogramData || this.histogramData.length === 0) return;
    
    const midY = p + areaH / 2;

    const drawHalf = (data, color, isTop) => {
      if (!data || data.length === 0) return;
      const bins = data.length;
      const maxVal = Math.max(...data, 1);
      
      ctx.beginPath();
      if (isTop) {
        ctx.moveTo(p, midY);
        for (let i = 0; i < bins; i++) {
          const x = p + (i / (bins - 1)) * areaW;
          const normHeight = data[i] / maxVal;
          const logHeight = Math.pow(normHeight, 0.35);
          const y = midY - (logHeight * (areaH / 2) * 0.95);
          ctx.lineTo(x, y);
        }
        ctx.lineTo(p + areaW, midY);
      } else {
        ctx.moveTo(p, p + areaH);
        for (let i = 0; i < bins; i++) {
          const x = p + (i / (bins - 1)) * areaW;
          const normHeight = data[i] / maxVal;
          const logHeight = Math.pow(normHeight, 0.35);
          const y = p + areaH - (logHeight * (areaH / 2) * 0.95);
          ctx.lineTo(x, y);
        }
        ctx.lineTo(p + areaW, p + areaH);
      }
      ctx.closePath();
      ctx.fillStyle = color;
      ctx.fill();
    };

    // Draw Input (Bottom) - normalized to its own max to stay stable
    drawHalf(this.histogramData, this.histogramColor, false);
    
    // Draw Adjusted (Top) - normalized to its own max
    if (this.histogramAdjData) {
      drawHalf(this.histogramAdjData, this.histogramAdjColor, true);
    }

    // Center divider line
    ctx.beginPath();
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.05)';
    ctx.setLineDash([2, 4]);
    ctx.moveTo(p, midY);
    ctx.lineTo(p + areaW, midY);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  _drawGrid(ctx, p, areaW, areaH) {
    const divisions = 4;
    for (let i = 0; i <= divisions; i++) {
      const xPos = p + (i / divisions) * areaW;
      const yPos = p + (i / divisions) * areaH;
      ctx.beginPath();
      ctx.strokeStyle =
        i === 0 || i === divisions
          ? 'var(--curve-grid-major)'
          : 'rgba(148, 163, 184, 0.06)';
      ctx.lineWidth = 1;

      ctx.moveTo(xPos, p);
      ctx.lineTo(xPos, p + areaH);
      ctx.stroke();

      ctx.moveTo(p, yPos);
      ctx.lineTo(p + areaW, yPos);
      ctx.stroke();
    }
  }

  _drawCurve(ctx, p, areaW, areaH) {
    const pts = this.points;
    if (pts.length < 2) return;

    // Generate interpolated curve using monotone cubic
    const steps = 200;
    const curvePoints = this._interpolate(steps);

    ctx.beginPath();
    ctx.strokeStyle = '#818cf8';
    ctx.lineWidth = 2.5;
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';

    for (let i = 0; i < curvePoints.length; i++) {
      const cp = this._toCanvas(curvePoints[i].x, curvePoints[i].y);
      if (i === 0) ctx.moveTo(cp.x, cp.y);
      else ctx.lineTo(cp.x, cp.y);
    }
    ctx.stroke();

    // Glow effect
    ctx.strokeStyle = 'rgba(129, 140, 248, 0.2)';
    ctx.lineWidth = 6;
    ctx.stroke();
  }

  _drawPoints(ctx) {
    for (let i = 0; i < this.points.length; i++) {
      const pt = this.points[i];
      const cp = this._toCanvas(pt.x, pt.y);
      const isHovered = this.hovered === i;
      const isDragging = this.dragging === i;
      const r = this.pointRadius + (isHovered || isDragging ? 2 : 0);

      // Outer glow
      if (isHovered || isDragging) {
        ctx.beginPath();
        ctx.arc(cp.x, cp.y, r + 4, 0, Math.PI * 2);
        ctx.fillStyle = 'rgba(129, 140, 248, 0.2)';
        ctx.fill();
      }

      // Point
      ctx.beginPath();
      ctx.arc(cp.x, cp.y, r, 0, Math.PI * 2);
      ctx.fillStyle = isDragging
        ? '#a5b4fc'
        : isHovered
        ? '#c4b5fd'
        : '#818cf8';
      ctx.fill();

      // Border
      ctx.strokeStyle = '#1e1b4b';
      ctx.lineWidth = 2;
      ctx.stroke();
    }
  }

  /**
   * Monotone cubic interpolation (Fritsch-Carlson)
   */
  _interpolate(steps) {
    const pts = this.points;
    const n = pts.length;
    if (n < 2) return pts;

    const xs = pts.map((p) => p.x);
    const ys = pts.map((p) => p.y);

    // Compute slopes
    const dx = [];
    const dy = [];
    const m = [];

    for (let i = 0; i < n - 1; i++) {
      dx.push(xs[i + 1] - xs[i]);
      dy.push(ys[i + 1] - ys[i]);
      m.push(dy[i] / dx[i]);
    }

    // Compute tangents
    const tangents = [m[0]];
    for (let i = 1; i < n - 1; i++) {
      if (m[i - 1] * m[i] <= 0) {
        tangents.push(0);
      } else {
        tangents.push(
          (3 * (dx[i - 1] + dx[i])) /
            ((2 * dx[i] + dx[i - 1]) / m[i - 1] +
              (dx[i] + 2 * dx[i - 1]) / m[i])
        );
      }
    }
    tangents.push(m[n - 2]);

    // Generate points
    const result = [];
    for (let step = 0; step <= steps; step++) {
      const t = step / steps;
      const x = t;

      // Find segment
      let seg = 0;
      for (let i = 0; i < n - 1; i++) {
        if (x >= xs[i] && x <= xs[i + 1]) {
          seg = i;
          break;
        }
        if (i === n - 2) seg = i;
      }

      const segDx = dx[seg];
      if (segDx === 0) {
        result.push({ x, y: ys[seg] });
        continue;
      }

      const localT = (x - xs[seg]) / segDx;
      const t2 = localT * localT;
      const t3 = t2 * localT;

      const h00 = 2 * t3 - 3 * t2 + 1;
      const h10 = t3 - 2 * t2 + localT;
      const h01 = -2 * t3 + 3 * t2;
      const h11 = t3 - t2;

      let y =
        h00 * ys[seg] +
        h10 * segDx * tangents[seg] +
        h01 * ys[seg + 1] +
        h11 * segDx * tangents[seg + 1];

      y = Math.max(0, Math.min(1, y));
      result.push({ x, y });
    }

    return result;
  }

  /**
   * Generate a 256-entry LUT from current control points.
   */
  generateLUT() {
    const curvePoints = this._interpolate(255);
    return curvePoints.map((p) => p.y);
  }
}
