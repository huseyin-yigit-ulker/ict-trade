// Paylaşılabilir PUSU sonuç kartı — Canvas 2D ile çizilir.
//
// Neden DOM→görüntü değil: html2canvas/html-to-image gibi araçlar yeni bir bağımlılık
// getirir ve foreignObject üzerinden color-mix()/radial-gradient/web-font'ları güvenilmez
// biçimde render eder. Kartı doğrudan canvas'a çizmek deterministik, bağımlılıksız ve
// Telegram'a giden matplotlib kartıyla aynı görsel kimliği verir.
//
// sharePng() önce Web Share API (mobil native paylaşım sayfası) dener; desteklenmiyorsa
// PNG'yi indirir. İkisi de olmazsa false döner.

const W = 1080;
const H = 608;

const BG = '#0b0e11';
const TEXT = '#e8eaed';
const MUTED = '#848E9C';
const BORDER = '#2a2f3a';
const GOLD = '#F5B942';
const UP = '#0ECB81';
const DOWN = '#F6465D';

const MONO = '"JetBrains Mono", "SF Mono", Menlo, Consolas, monospace';
const SANS = '"Space Grotesk", "Segoe UI", system-ui, -apple-system, sans-serif';

const withLetterSpacing = (ctx, px, fn) => {
  const had = 'letterSpacing' in ctx;
  const prev = had ? ctx.letterSpacing : null;
  if (had) ctx.letterSpacing = `${px}px`;
  fn();
  if (had) ctx.letterSpacing = prev;
};

/** PUSU nişangâhı — iç içe halkalar + dört çeyrek çizgisi. */
const reticle = (ctx, cx, cy, r) => {
  ctx.save();
  ctx.strokeStyle = GOLD;
  ctx.globalAlpha = 0.09;
  [1, 0.66, 0.3].forEach((k, i) => {
    ctx.lineWidth = i === 0 ? 2 : 1.4;
    ctx.beginPath();
    ctx.arc(cx, cy, r * k, 0, Math.PI * 2);
    ctx.stroke();
  });
  ctx.lineWidth = 2;
  ctx.lineCap = 'round';
  [[1, 0], [-1, 0], [0, 1], [0, -1]].forEach(([dx, dy]) => {
    ctx.beginPath();
    ctx.moveTo(cx + dx * r * 0.78, cy + dy * r * 0.78);
    ctx.lineTo(cx + dx * r * 1.25, cy + dy * r * 1.25);
    ctx.stroke();
  });
  ctx.restore();
};

/** İşlemin fiyat yolu — kartın sağında, eksensiz. Renk SONUCU kodlar, fiyat yönünü değil. */
const sparkline = (ctx, closes, entryPx, acc, x, y, w, h) => {
  if (!Array.isArray(closes) || closes.length < 2) return;
  const pts = closes.filter((c) => Number.isFinite(c));
  if (pts.length < 2) return;
  const lo = Math.min(...pts, entryPx ?? Infinity);
  const hi = Math.max(...pts, entryPx ?? -Infinity);
  const span = hi - lo || 1;
  const px = (i) => x + (i / (pts.length - 1)) * w;
  const py = (v) => y + h - ((v - lo) / span) * h;

  if (Number.isFinite(entryPx)) {                       // kesikli giriş çizgisi
    ctx.save();
    ctx.setLineDash([6, 6]);
    ctx.strokeStyle = MUTED;
    ctx.globalAlpha = 0.55;
    ctx.lineWidth = 1.5;
    ctx.beginPath(); ctx.moveTo(x, py(entryPx)); ctx.lineTo(x + w, py(entryPx)); ctx.stroke();
    ctx.restore();
  }

  ctx.save();                                            // dolgu
  ctx.beginPath();
  ctx.moveTo(px(0), py(pts[0]));
  pts.forEach((v, i) => ctx.lineTo(px(i), py(v)));
  ctx.lineTo(x + w, y + h); ctx.lineTo(x, y + h); ctx.closePath();
  ctx.fillStyle = `${acc}1f`;
  ctx.fill();
  ctx.restore();

  ctx.strokeStyle = acc;                                 // çizgi
  ctx.lineWidth = 2.5;
  ctx.lineJoin = 'round';
  ctx.beginPath();
  pts.forEach((v, i) => (i ? ctx.lineTo(px(i), py(v)) : ctx.moveTo(px(i), py(v))));
  ctx.stroke();

  const dot = (cxx, cyy, col, r = 6) => {                // giriş (altın) / şimdi (mavi)
    ctx.beginPath(); ctx.arc(cxx, cyy, r, 0, Math.PI * 2);
    ctx.fillStyle = col; ctx.fill();
    ctx.lineWidth = 2; ctx.strokeStyle = BG; ctx.stroke();
  };
  dot(px(0), py(pts[0]), GOLD);
  dot(px(pts.length - 1), py(pts[pts.length - 1]), '#5C93FF', 7);
};

/**
 * Kartı çizip PNG Blob döndürür.
 * d: { symbol, long, lev, roi, total, margin, entry, mark, dur, r, kicker, note, footer, t,
 *      closes?, entryPx? }
 */
export async function renderCardBlob(d) {
  try { await document.fonts?.ready; } catch { /* fontlar hazır değilse sistem yazı tipiyle çiz */ }

  const cv = document.createElement('canvas');
  cv.width = W;
  cv.height = H;
  const ctx = cv.getContext('2d');
  const acc = (d.total ?? 0) >= 0 ? UP : DOWN;

  // zemin
  ctx.fillStyle = BG;
  ctx.fillRect(0, 0, W, H);

  // taktik ızgara
  ctx.save();
  ctx.strokeStyle = GOLD;
  ctx.globalAlpha = 0.03;
  ctx.lineWidth = 1;
  for (let i = 1; i < 16; i++) {
    ctx.beginPath(); ctx.moveTo((W / 16) * i, 0); ctx.lineTo((W / 16) * i, H); ctx.stroke();
  }
  for (let i = 1; i < 10; i++) {
    ctx.beginPath(); ctx.moveTo(0, (H / 10) * i); ctx.lineTo(W, (H / 10) * i); ctx.stroke();
  }
  ctx.restore();

  // sonuç parıltısı + nişangâh
  const cx = W * 0.26;
  const cy = H * 0.52;
  const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, W * 0.34);
  glow.addColorStop(0, `${acc}22`);
  glow.addColorStop(1, `${acc}00`);
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, W, H);
  reticle(ctx, cx, cy, W * 0.17);

  // çerçeve + üst altın şerit
  ctx.strokeStyle = BORDER; ctx.lineWidth = 2;
  ctx.strokeRect(1, 1, W - 2, H - 2);
  ctx.fillStyle = GOLD; ctx.fillRect(0, 0, W, 8);

  const L = 52;
  const R = W - 52;

  // marka
  ctx.textBaseline = 'alphabetic';
  ctx.fillStyle = GOLD;
  ctx.font = `800 30px ${SANS}`;
  withLetterSpacing(ctx, 6, () => ctx.fillText('PUSU', L, 84));
  ctx.fillStyle = MUTED;
  ctx.font = `500 13px ${SANS}`;
  withLetterSpacing(ctx, 3, () => ctx.fillText(d.kicker, L, 112));

  // sembol + yön/kaldıraç
  ctx.textAlign = 'right';
  ctx.fillStyle = TEXT;
  ctx.font = `800 30px ${SANS}`;
  ctx.fillText(d.symbol, R, 84);
  ctx.fillStyle = d.long ? UP : DOWN;
  ctx.font = `800 17px ${SANS}`;
  ctx.fillText(`${d.long ? 'LONG' : 'SHORT'}  ·  ${d.lev}x`, R, 114);
  ctx.textAlign = 'left';

  // kahraman: ROI
  ctx.fillStyle = acc;
  ctx.font = `800 96px ${SANS}`;
  ctx.fillText(d.roi == null ? '—' : `${d.roi >= 0 ? '+' : ''}${d.roi.toFixed(1)}%`, L, 300);

  // net $ + marj
  ctx.font = `700 38px ${MONO}`;
  const usd = d.total == null ? '—' : `${d.total >= 0 ? '+' : '−'}$${Math.abs(d.total).toFixed(2)}`;
  ctx.fillText(usd, L, 362);
  const usdW = ctx.measureText(usd).width;
  ctx.fillStyle = MUTED;
  ctx.font = `500 17px ${SANS}`;
  if (d.margin) ctx.fillText(`· ${d.t('marj')} $${d.margin.toFixed(2)}`, L + usdW + 16, 362);
  ctx.font = `500 15px ${SANS}`;
  ctx.fillText(d.note, L, 396);

  // işlemin fiyat yolu (sağ)
  sparkline(ctx, d.closes, d.entryPx, acc, W * 0.56, 190, W * 0.39, 190);

  // ayırıcı
  ctx.strokeStyle = BORDER; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(L, 436); ctx.lineTo(R, 436); ctx.stroke();

  // hücreler
  const cells = [
    [d.t('Giriş'), d.entry],
    [d.t('Anlık'), d.mark],
    [d.t('Süre'), d.dur],
    ['R', d.r],
  ];
  const step = (R - L) / cells.length;
  cells.forEach(([k, val], i) => {
    const x = L + i * step;
    ctx.fillStyle = MUTED;
    ctx.font = `600 13px ${SANS}`;
    withLetterSpacing(ctx, 1, () => ctx.fillText(String(k).toUpperCase(), x, 474));
    ctx.fillStyle = TEXT;
    ctx.font = `700 24px ${MONO}`;
    ctx.fillText(val ?? '—', x, 510);
  });

  // imza
  ctx.fillStyle = MUTED;
  ctx.font = `500 14px ${SANS}`;
  ctx.fillText(d.footer, L, 566);
  ctx.textAlign = 'right';
  ctx.fillStyle = GOLD;
  ctx.globalAlpha = 0.8;
  ctx.font = `700 14px ${SANS}`;
  withLetterSpacing(ctx, 1.5, () => ctx.fillText('WAIT · TRAP · EXECUTE', R, 566));
  ctx.globalAlpha = 1;

  return new Promise((resolve) => cv.toBlob(resolve, 'image/png'));
}

/**
 * Kartı paylaş: önce native paylaşım sayfası, olmazsa indir.
 * Döner: 'shared' | 'downloaded' | 'cancelled' | 'failed'
 */
export async function sharePng(blob, filename, shareTitle) {
  if (!blob) return 'failed';
  const file = new File([blob], filename, { type: 'image/png' });

  // Web Share API Level 2 (dosya) — mobil Safari/Chrome. Güvenli bağlam (HTTPS) gerekir.
  if (navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file], title: shareTitle });
      return 'shared';
    } catch (e) {
      // Kullanıcı vazgeçtiyse sessizce çık; başka hatada indirmeye düş.
      if (e?.name === 'AbortError') return 'cancelled';
    }
  }

  try {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    return 'downloaded';
  } catch {
    return 'failed';
  }
}
