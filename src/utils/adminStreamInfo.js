// ADMIN-ONLY stream intelligence — real names, technical labels and the full strategy
// cards. This module is loaded EXCLUSIVELY via streamMask.loadAdminStreamInfo()
// (dynamic import, admin role only), so Vite splits it into a lazy chunk and none of
// these strings ship in the main bundle non-admin users download.
//
// NEVER import this file statically from a component — that would fold it back into
// the shared bundle and defeat the anonymization.

export { STRATEGY_INFO, infoFor } from './strategyInfo';

// key → real display name (what the owner used to see pre-multi-user).
export const REAL_NAMES = {
  d30so8f3h7: 'OPUS',
  d30so8f3vg: 'FABLE',
  midas: 'MIDAS',
  talos: 'TALOS',
  donchianc: 'DONCHIAN 1h',
  d1h_so4c: 'DONCHIAN 1h·WR 4R',
  d1h_so6c: 'DONCHIAN 1h·WR 6R',
  d1h_so8c: 'DONCHIAN 1h·WR 8R',
  d1hso4cm: 'DONCHIAN 1h·WR 4R ·M0.25',
  d1hso6cm: 'DONCHIAN 1h·WR 6R ·M0.25',
  d1hso8cm: 'DONCHIAN 1h·WR 8R ·M0.25',
  dch30_4hc: 'DONCHIAN 30m+4h',
  dch30_4h6c: 'DONCHIAN 30m+4h·6R',
  d30_4h_soc: 'DONCHIAN 30m+4h·WR 4R',
  d30so6c: 'DONCHIAN 30m+4h·WR 6R',
  d30so8c: 'DONCHIAN 30m+4h·WR 8R',
  d30so4cm: 'DONCHIAN 30m+4h·WR 4R ·M0.25',
  d30so6cm: 'DONCHIAN 30m+4h·WR 6R ·M0.25',
  d30so8cm: 'DONCHIAN 30m+4h·WR 8R ·M0.25',
  d30so4f3: 'DONCHIAN 30m+4h·WR 4R ·b30',
  d30so6f3: 'DONCHIAN 30m+4h·WR 6R ·b30',
  d30so8f3: 'DONCHIAN 30m+4h·WR 8R ·b30',
};

// key → real technical sublabel (the old Sidebar/streamStats label text).
export const REAL_LABELS = {
  d30so8f3h7: 'OPUS · DONCHIAN 30m+4h·WR 8R ·b30·7g',
  d30so8f3vg: 'FABLE · DONCHIAN 30m+4h·WR 8R ·b30·7g ·VolGate0.9',
  midas: 'MIDAS · ALTIN VWAP-Trend (XAU 1m·trailing)',
  talos: 'TALOS · ALTIN Keltner-Trend (XAU 1m·trailing)',
  donchianc: 'DONCHIAN 1h ·0.5R',
  d1h_so4c: 'DONCHIAN 1h·WR 4R ·0.5R',
  d1h_so6c: 'DONCHIAN 1h·WR 6R ·0.5R',
  d1h_so8c: 'DONCHIAN 1h·WR 8R ·0.5R',
  d1hso4cm: 'DONCHIAN 1h·WR 4R ·M0.25',
  d1hso6cm: 'DONCHIAN 1h·WR 6R ·M0.25',
  d1hso8cm: 'DONCHIAN 1h·WR 8R ·M0.25',
  dch30_4hc: 'DONCHIAN 30m+4h ·0.5R',
  dch30_4h6c: 'DONCHIAN 30m+4h 6R ·0.5R',
  d30_4h_soc: 'DONCHIAN 30m+4h·WR 4R ·0.5R',
  d30so6c: 'DONCHIAN 30m+4h·WR 6R ·0.5R',
  d30so8c: 'DONCHIAN 30m+4h·WR 8R ·0.5R',
  d30so4cm: 'DONCHIAN 30m+4h·WR 4R ·M0.25',
  d30so6cm: 'DONCHIAN 30m+4h·WR 6R ·M0.25',
  d30so8cm: 'DONCHIAN 30m+4h·WR 8R ·M0.25',
  d30so4f3: 'DONCHIAN 30m+4h·WR 4R ·b30',
  d30so6f3: 'DONCHIAN 30m+4h·WR 6R ·b30',
  d30so8f3: 'DONCHIAN 30m+4h·WR 8R ·b30',
};

// The XAU chart anchor line's REAL identity (renders as streamMask.REFLINE_LABEL
// = 'T-REF' for everyone else).
export const REAL_REFLINE = 'VWAP';

// The XAU live chart's signal-condition checklist — REAL rule text (admin only).
// Non-admins see the neutral "Koşul A/B/C/D/E" pills instead.
export const REAL_MIDAS_CONDS = {
  slopeUp: 'eğim>0 (yukarı trend)',
  above: 'fiyat > VWAP',
  pullLong: "VWAP'a çekilme (low ≤ VWAP+0.25·ATR)",
  bull: 'yükselen mum (close>open)',
  sess: 'seans uygun (07-13 UTC dışı)',
  slopeDn: 'eğim<0 (aşağı trend)',
  below: 'fiyat < VWAP',
  pullShort: "VWAP'a çekilme (high ≥ VWAP−0.25·ATR)",
  bear: 'düşen mum (close<open)',
};

// TALOS live chart's signal-condition checklist — REAL rule text (admin only).
export const REAL_TALOS_CONDS = {
  slopeUp: '15m-EMA20 eğim>0 (yukarı trend)',
  above: 'fiyat > alt Keltner bandı',
  pullLong: 'banda derin çekilme (low ≤ bant+0.25·ATR)',
  bull: 'yükselen mum (close>open)',
  sess: 'seans uygun (07-13 UTC dışı)',
  slopeDn: '15m-EMA20 eğim<0 (aşağı trend)',
  below: 'fiyat < üst Keltner bandı',
  pullShort: 'banda derin çekilme (high ≥ bant−0.25·ATR)',
  bear: 'düşen mum (close<open)',
};

// TOTAL page — admin-only research footnote. Names real streams (MAIN/OPUS/RANGE),
// so the TEXT must live in this lazy chunk, never in the shared translation map.
export const MARKETCAP_NOTE = {
  tr: 'Tek başına temiz bir gate çıkmıyor: etkinin en güçlü olduğu MAIN/OPUS örneklem-dışı (2025) zaten net-negatif, tek istikrarlı kârlı akış RANGE’de dayanıklı bir kazanım yok. Bu yüzden bir lookup + monitör olarak kullanılır; bir akışa bağlamadan önce OOS kazanım göster. Kaynak: sync/marketcap.py + marketcap_analysis.py.',
  en: 'No clean standalone gate emerges: MAIN/OPUS, where the effect is strongest, is already net-negative out-of-sample (2025), and RANGE, the one consistently profitable stream, shows no durable gain. So this serves as a lookup + monitor; show an OOS gain before wiring it to a stream. Source: sync/marketcap.py + marketcap_analysis.py.',
};
