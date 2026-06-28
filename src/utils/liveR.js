// Shared LIVE-R model for the scale-out streams (d30_4h_so + the realistic ·0.5R twins d30so{N}c /
// d30_4h_soc). SINGLE SOURCE: the dashboard list (liveOutcomeR) AND the chart panel (soLiveR) both
// read this, so the R value is identical in both views.
//
// Geometry: 60% booked at +1R (sets the floor), the 40% runner exits at its +N R cap, at breakeven
// (0R), or a 3-day mark. R is in the trade's risk units; the ·0.5R twins enter at the +0.5R confirm
// level, so a +N*raw_risk cap from the breakout is +(N-0.5)/1.5 R of the realistic (1.5×) risk.
// fee = 0.1% round-trip on full notional, expressed in R.

// All scale-out versions: the 30m+4h family (live d30_4h_so + realistic twins d30_4h_soc /
// d30so6c / d30so8c) AND the 1h family (d1h_so4c…). Also the variant suffixes: margin (…cm) and
// close_frac-0.3 (…f3, optionally + a 7-day time-stop …f3h7).
export const isScaleOutStrategy = (s) => /^(d30_4h_so|d30so\d+|d1h_?so\d+)/.test(s || '');

// Runner cap in R from the version tag: d30so6c → 6, d30so8c / d30so8f3h7 → 8, bare d30_4h_so → 4.
export const soCapFromStrategy = (s) => {
  const m = (s || '').match(/so(\d+)/);
  return m ? Number(m[1]) : 4;
};

// Booked fraction at TP1 from the tag: the 'f3' variants book 30%, the rest 60%.
export const soBookFromStrategy = (s) => (/f3/.test(s || '') ? 0.3 : 0.6);

// The realistic-entry (·0.5R) confirm twins: a trailing 'c', or the cm/f3 variants (all confirm-entry).
export const isConfirmStrategy = (s) => !!(s && (s.endsWith('c') || /(cm|f3)/.test(s)));

// Live R for a scale-out trade given its live status, or null if the status isn't a scale-out
// outcome/floor. capR = runner cap in R (4/6/8…); conservative = the ·0.5R realistic-entry twin;
// bookFrac = fraction booked at +1R (0.6 default, 0.3 for the f3 variants).
export const scaleOutLiveR = (entry, sl, status, capR = 4, conservative = true, bookFrac = 0.6) => {
  if (!Number.isFinite(entry) || !Number.isFinite(sl)) return null;
  const risk = Math.abs(entry - sl);
  if (!risk) return null;
  const fee = 0.0005 * (2 * entry) / risk;                       // round-trip fee on full notional, in R
  const runnerR = conservative ? (capR - 0.5) / 1.5 : capR;      // runner profit at the cap, in R
  const runFrac = 1 - bookFrac;
  if (status === 'BE Oldu' || status === 'İşlem Aktif (+1R Alındı · Runner)') return bookFrac - fee; // book@+1R + runner@BE(0)
  if (status === 'SL Oldu' || status === 'TP/SL Aynı Mum') return -1 - fee;                          // -1R before +1R
  if (status === 'TP Oldu') return bookFrac + runFrac * runnerR - fee;                               // runner hit +NR cap
  return null;
};
