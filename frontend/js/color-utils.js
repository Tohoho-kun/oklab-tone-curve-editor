/**
 * color-utils.js — クライアント側の色空間変換 (インジケーター用)
 *
 * sRGB → Okhsl 変換をブラウザ側で実行し、
 * トーンカーブ上のインジケーター位置を計算する。
 *
 * Björn Ottosson 氏の Okhsl 実装の簡易 JS 移植。
 * 参考: https://bottosson.github.io/posts/colorpicker/
 */

const ColorUtils = (() => {

  const PI = Math.PI;

  // sRGB EOTF (ガンマデコード)
  function srgbEotf(c) {
    return c <= 0.04045
      ? c / 12.92
      : Math.pow((c + 0.055) / 1.055, 2.4);
  }

  // Linear sRGB → OKLab
  function linearSrgbToOklab(r, g, b) {
    const l_ = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b;
    const m_ = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b;
    const s_ = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b;

    const l = Math.cbrt(l_);
    const m = Math.cbrt(m_);
    const s = Math.cbrt(s_);

    return {
      L: 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
      a: 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
      b: 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s,
    };
  }

  // Toe function (L → l)
  const K1 = 0.206, K2 = 0.03, K3 = (1 + K1) / (1 + K2);
  function toe(x) {
    return 0.5 * (K3 * x - K1 + Math.sqrt((K3 * x - K1) * (K3 * x - K1) + 4 * K2 * K3 * x));
  }
  function toeInv(x) {
    return (x * x + K1 * x) / (K3 * (x + K2));
  }

  // Compute max saturation for a given hue
  function computeMaxSaturation(a_, b_) {
    let k0, k1, k2, k3, k4, wl, wm, ws;
    if (-1.88170328 * a_ - 0.80936493 * b_ > 1) {
      k0 = 1.19086277; k1 = 1.76576728; k2 = 0.59662641; k3 = 0.75515197; k4 = 0.56771245;
      wl = 4.0767416621; wm = -3.3077115913; ws = 0.2309699292;
    } else if (1.81444104 * a_ - 1.19445276 * b_ > 1) {
      k0 = 0.73956515; k1 = -0.45954404; k2 = 0.08285427; k3 = 0.12541070; k4 = 0.14503204;
      wl = -1.2684380046; wm = 2.6097574011; ws = -0.3413193965;
    } else {
      k0 = 1.35733652; k1 = -0.00915799; k2 = -1.15130210; k3 = -0.50559606; k4 = 0.00692167;
      wl = -0.0041960863; wm = -0.7034186147; ws = 1.7076147010;
    }

    let S = k0 + k1 * a_ + k2 * b_ + k3 * a_ * a_ + k4 * a_ * b_;

    const kl = 0.3963377774 * a_ + 0.2158037573 * b_;
    const km = -0.1055613458 * a_ - 0.0638541728 * b_;
    const ks = -0.0894841775 * a_ - 1.2914855480 * b_;

    const l_ = 1 + S * kl, m_ = 1 + S * km, s_ = 1 + S * ks;
    const l = l_ * l_ * l_, m = m_ * m_ * m_, s = s_ * s_ * s_;
    const ldS = 3 * kl * l_ * l_, mdS = 3 * km * m_ * m_, sdS = 3 * ks * s_ * s_;
    const ldS2 = 6 * kl * kl * l_, mdS2 = 6 * km * km * m_, sdS2 = 6 * ks * ks * s_;

    const f = wl * l + wm * m + ws * s;
    const f1 = wl * ldS + wm * mdS + ws * sdS;
    const f2 = wl * ldS2 + wm * mdS2 + ws * sdS2;

    S = S - f * f1 / (f1 * f1 - 0.5 * f * f2);
    return S;
  }

  // Find cusp
  function findCusp(a_, b_) {
    const Scusp = computeMaxSaturation(a_, b_);
    const l_ = 1 + Scusp * (0.3963377774 * a_ + 0.2158037573 * b_);
    const m_ = 1 + Scusp * (-0.1055613458 * a_ - 0.0638541728 * b_);
    const s_ = 1 + Scusp * (-0.0894841775 * a_ - 1.2914855480 * b_);
    const l = l_*l_*l_, m = m_*m_*m_, s = s_*s_*s_;
    const r = 4.0767416621*l - 3.3077115913*m + 0.2309699292*s;
    const g = -1.2684380046*l + 2.6097574011*m - 0.3413193965*s;
    const bv = -0.0041960863*l - 0.7034186147*m + 1.7076147010*s;
    const Lcusp = Math.cbrt(1 / Math.max(Math.max(r, g), Math.max(bv, 1e-10)));
    return { L: Lcusp, C: Lcusp * Scusp };
  }

  // Find gamut intersection
  function findGamutIntersection(a_, b_, L1, C1, L0, cusp) {
    if (((L1 - L0) * cusp.C - (cusp.L - L0) * C1) <= 0) {
      return cusp.C * L0 / (C1 * cusp.L + cusp.C * (L0 - L1));
    }
    let t = cusp.C * (L0 - 1) / (C1 * (cusp.L - 1) + cusp.C * (L0 - L1));
    const dL = L1 - L0, dC = C1;
    const kl = 0.3963377774*a_ + 0.2158037573*b_;
    const km = -0.1055613458*a_ - 0.0638541728*b_;
    const ks = -0.0894841775*a_ - 1.2914855480*b_;
    const ldt = dL + dC*kl, mdt = dL + dC*km, sdt = dL + dC*ks;
    const L = L0*(1-t) + t*L1, C = t*C1;
    const l_ = L + C*kl, m_ = L + C*km, s_ = L + C*ks;
    const l = l_*l_*l_, m = m_*m_*m_, s = s_*s_*s_;
    const ld = 3*ldt*l_*l_, md = 3*mdt*m_*m_, sd = 3*sdt*s_*s_;
    const ld2 = 6*ldt*ldt*l_, md2 = 6*mdt*mdt*m_, sd2 = 6*sdt*sdt*s_;
    const rv = 4.0767416621*l - 3.3077115913*m + 0.2309699292*s - 1;
    const r1 = 4.0767416621*ld - 3.3077115913*md + 0.2309699292*sd;
    const r2 = 4.0767416621*ld2 - 3.3077115913*md2 + 0.2309699292*sd2;
    const ur = r1/(r1*r1 - 0.5*rv*r2); const tr = ur >= 0 ? -rv*ur : 1e10;
    const gv = -1.2684380046*l + 2.6097574011*m - 0.3413193965*s - 1;
    const g1 = -1.2684380046*ld + 2.6097574011*md - 0.3413193965*sd;
    const g2 = -1.2684380046*ld2 + 2.6097574011*md2 - 0.3413193965*sd2;
    const ug = g1/(g1*g1 - 0.5*gv*g2); const tg = ug >= 0 ? -gv*ug : 1e10;
    const bv = -0.0041960863*l - 0.7034186147*m + 1.7076147010*s - 1;
    const b1 = -0.0041960863*ld - 0.7034186147*md + 1.7076147010*sd;
    const b2 = -0.0041960863*ld2 - 0.7034186147*md2 + 1.7076147010*sd2;
    const ub = b1/(b1*b1 - 0.5*bv*b2); const tb = ub >= 0 ? -bv*ub : 1e10;
    t += Math.min(tr, Math.min(tg, tb));
    return t;
  }

  function getSTmid(a_, b_) {
    const S = 0.11516993 + 1/(7.44778970 + 4.15901240*b_ + a_*(-2.19557347 + 1.75198401*b_ + a_*(-2.13704948 - 10.02301043*b_ + a_*(-4.24894561 + 5.38770819*b_ + 4.69891013*a_))));
    const T = 0.11239642 + 1/(1.61320320 - 0.68124379*b_ + a_*(0.40370612 + 0.90148123*b_ + a_*(-0.27087943 + 0.61223990*b_ + a_*(0.00299215 - 0.45399568*b_ - 0.14661872*a_))));
    return { S, T };
  }

  function getCs(L, a_, b_) {
    const cusp = findCusp(a_, b_);
    const Cmax = findGamutIntersection(a_, b_, L, 1, L, cusp);
    const Smax = cusp.C / Math.max(cusp.L, 1e-10);
    const Tmax = cusp.C / Math.max(1 - cusp.L, 1e-10);
    const k = Cmax / Math.max(Math.min(L * Smax, (1 - L) * Tmax), 1e-10);

    const stm = getSTmid(a_, b_);
    const Ca = L * stm.S, Cb = (1 - L) * stm.T;
    const Ca4 = Ca*Ca*Ca*Ca, Cb4 = Cb*Cb*Cb*Cb;
    const Cmid = 0.9 * k * Math.sqrt(Math.sqrt(1 / (1/Math.max(Ca4,1e-20) + 1/Math.max(Cb4,1e-20))));

    const Ca0 = L * 0.4, Cb0 = (1 - L) * 0.8;
    const C0 = Math.sqrt(1 / (1/Math.max(Ca0*Ca0,1e-20) + 1/Math.max(Cb0*Cb0,1e-20)));

    return { C0, Cmid, Cmax };
  }

  /**
   * sRGB (0-255) → Okhsl
   * Returns { h: 0-1, s: 0-1, l: 0-1 }
   */
  function srgbToOkhsl(r255, g255, b255) {
    const r = srgbEotf(r255 / 255);
    const g = srgbEotf(g255 / 255);
    const b = srgbEotf(b255 / 255);

    const lab = linearSrgbToOklab(r, g, b);
    const C = Math.sqrt(lab.a * lab.a + lab.b * lab.b);
    const eps = 1e-10;

    let a_, b_;
    if (C < eps) { a_ = 1; b_ = 0; }
    else { a_ = lab.a / C; b_ = lab.b / C; }

    const h = 0.5 + 0.5 * Math.atan2(-lab.b, -lab.a) / PI;
    const L = lab.L;

    const cs = getCs(L, a_, b_);
    const mid = 0.8, midInv = 1.25;
    let s;

    if (C < cs.Cmid) {
      const k1 = mid * cs.C0;
      const k2 = 1 - k1 / Math.max(cs.Cmid, eps);
      const t = C / Math.max(k1 + k2 * C, eps);
      s = t * mid;
    } else {
      const k0 = cs.Cmid;
      const k1 = (1 - mid) * cs.Cmid * cs.Cmid * midInv * midInv / Math.max(cs.C0, eps);
      const k2 = 1 - k1 / Math.max(cs.Cmax - cs.Cmid, eps);
      const Cmk0 = C - k0;
      const t = Cmk0 / Math.max(k1 + k2 * Cmk0, eps);
      s = mid + (1 - mid) * t;
    }

    const l = toe(L);

    return {
      h: Math.max(0, Math.min(1, h)),
      s: Math.max(0, Math.min(1, C < eps ? 0 : s)),
      l: Math.max(0, Math.min(1, l)),
    };
  }

  return { srgbToOkhsl };
})();
