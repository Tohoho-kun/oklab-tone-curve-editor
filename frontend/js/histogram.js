/**
 * histogram.js — RGB + 明度ヒストグラム描画
 */

class HistogramRenderer {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas.getContext('2d');
    this.dpr = window.devicePixelRatio || 1;
    this.data = null;

    this._setupCanvas();
  }

  _setupCanvas() {
    const rect = this.canvas.parentElement.getBoundingClientRect();
    const w = Math.floor(rect.width);
    const h = Math.floor(rect.height);
    this.canvas.style.width = w + 'px';
    this.canvas.style.height = h + 'px';
    this.canvas.width = w * this.dpr;
    this.canvas.height = h * this.dpr;
    this.w = w;
    this.h = h;
    this.ctx.scale(this.dpr, this.dpr);
  }

  resize() {
    this._setupCanvas();
    if (this.data) this.draw(this.data);
  }

  /**
   * Update histogram with new data.
   * @param {Object} data - { r: [...256], g: [...256], b: [...256], l: [...256] }
   */
  update(data) {
    this.data = data;
    this.draw(data);
  }

  draw(data) {
    const ctx = this.ctx;
    const w = this.w;
    const h = this.h;

    ctx.clearRect(0, 0, w, h);

    // Background
    ctx.fillStyle = '#080c14';
    ctx.fillRect(0, 0, w, h);

    if (!data) return;

    // Find global max for normalization
    const allValues = [
      ...(data.r || []),
      ...(data.g || []),
      ...(data.b || []),
    ];
    const maxVal = Math.max(...allValues, 1);

    const channels = [
      { key: 'r', color: 'rgba(239, 68, 68, 0.45)' },
      { key: 'g', color: 'rgba(34, 197, 94, 0.45)' },
      { key: 'b', color: 'rgba(59, 130, 246, 0.45)' },
      { key: 'l', color: 'rgba(255, 255, 255, 0.3)' },
    ];

    const bins = 256;
    const barW = w / bins;

    for (const ch of channels) {
      const values = data[ch.key];
      if (!values) continue;

      ctx.beginPath();
      ctx.fillStyle = ch.color;
      ctx.moveTo(0, h);

      for (let i = 0; i < bins; i++) {
        const barH = (values[i] / maxVal) * h * 0.95;
        const x = i * barW;
        ctx.lineTo(x, h - barH);
      }

      ctx.lineTo(w, h);
      ctx.closePath();
      ctx.fill();
    }

    // Border
    ctx.strokeStyle = 'rgba(148, 163, 184, 0.1)';
    ctx.lineWidth = 1;
    ctx.strokeRect(0, 0, w, h);
  }
}
