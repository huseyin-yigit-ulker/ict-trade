// Shared constants + PostgREST helpers for the İşlem Merkezi (per-user trading) cards.
// The activatable (stream, network) combos. 2026-07-07: the gold stream's MAINNET mode is
// OPEN (migration 012 dropped the testnet-only CHECK) — both streams now offer real + paper.
//
// NO display names live here (stream anonymization): `maskKey` is the stream key the
// components resolve through useStreamDisplay() — codename for users, real name for
// the admin. `version` is the backtest-project RPC tag for the ranking panel; it is
// SENT to the RPC, never displayed.

import { authedFetch } from '../../utils/supa';

export const STREAM_ROWS = [
  { stream: 'opus',  network: 'mainnet', maskKey: 'd30so8f3h7', version: 'd30so8f3h7', real: true },
  { stream: 'opus',  network: 'testnet', maskKey: 'd30so8f3h7', version: 'd30so8f3h7', real: false },
  { stream: 'midas', network: 'mainnet', maskKey: 'midas',      version: 'midas',      real: true },
  { stream: 'midas', network: 'testnet', maskKey: 'midas',      version: 'midas',      real: false },
];

export const rowKey = (d) => `${d.stream}:${d.network}`;

/** Network suffix rendered next to the (masked) stream name. */
export const netLabel = (network, long = false) =>
  (network === 'mainnet' ? (long ? 'Mainnet' : 'Main') : 'Paper');

// Defaults for a freshly-created user_stream_settings row.
export const DEFAULTS = { risk_usd: 5, max_concurrent: 5, max_total_risk_usd: 25 };

/** authedFetch + throw-with-PostgREST-message (trigger `raise exception` text included). */
export async function reqJSON(path, opts = {}) {
  const res = await authedFetch(path, opts);
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const body = await res.json();
      msg = body?.message || body?.hint || body?.details || msg;
    } catch { /* non-JSON error body */ }
    throw new Error(msg);
  }
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

/** Upsert on the (user_id, stream, network) unique key — first write creates the row. */
export function upsertStreamSettings(userId, stream, network, fields) {
  return reqJSON('user_stream_settings?on_conflict=user_id,stream,network', {
    method: 'POST',
    headers: { Prefer: 'resolution=merge-duplicates,return=representation' },
    body: JSON.stringify({ user_id: userId, stream, network, ...fields }),
  });
}

export function patchStreamSettings(id, fields) {
  return reqJSON(`user_stream_settings?id=eq.${id}`, {
    method: 'PATCH',
    headers: { Prefer: 'return=representation' },
    body: JSON.stringify(fields),
  });
}

// Cross-card sync: any card that saves settings emits this; the others refetch.
export const SETTINGS_EVT = 'pusu:stream-settings-changed';
export function emitSettingsChanged() {
  try { window.dispatchEvent(new Event(SETTINGS_EVT)); } catch { /* ignore */ }
}

// ── Backtest per-symbol ranking (SEPARATE backtest Supabase project) ──
// Shared by SymbolPickerCard (info panel) and TemplatesCard (symbol suggestions).
// The version tag is SENT to the RPC, never displayed (anonymization).

const BT_URL = import.meta.env.BACKTESTING_VITE_SUPABASE_URL;
const BT_KEY = import.meta.env.BACKTESTING_VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY;

const rankCache = {};   // version -> rows sorted by total R desc (session cache)

export async function fetchRanking(version) {
  if (rankCache[version]) return rankCache[version];
  if (!BT_URL || !BT_KEY) throw new Error('config');
  const res = await fetch(`${BT_URL}/rest/v1/rpc/backtest_symbol_metrics`, {
    method: 'POST',
    headers: {
      apikey: BT_KEY,
      Authorization: `Bearer ${BT_KEY}`,
      'Accept-Profile': 'ict_trade',
      'Content-Profile': 'ict_trade',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ p_version: version }),
  });
  if (!res.ok) throw new Error(`rpc ${res.status}`);
  const rows = await res.json();
  const sorted = (Array.isArray(rows) ? rows : [])
    .slice()
    .sort((a, b) => Number(b.total_r) - Number(a.total_r));
  rankCache[version] = sorted;
  return sorted;
}

// Fallback symbol preference when the ranking RPC is unreachable: liquid majors first.
export const MAJORS = ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT'];
