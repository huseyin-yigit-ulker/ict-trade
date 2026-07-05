// Signal-notification watchlist client layer (ict_trade.user_signal_watch).
// Per LIVE stream, the set of symbols the user wants a phone push for when a fresh
// signal fires. Distinct from the executor's user_stream_settings (SymbolPickerCard):
// this steers sync/push_notify.push_signal_watchers, not order placement.
import { getJSON, authedFetch } from './supa';

/** { strategyKey -> [symbols] } for the current user (RLS-scoped). */
export async function fetchWatch() {
  const rows = await getJSON('user_signal_watch?select=strategy,symbols');
  const m = {};
  for (const r of rows || []) m[r.strategy] = r.symbols || [];
  return m;
}

/** Upsert one stream's symbol list (on_conflict=user_id,strategy). Throws on failure. */
export async function saveWatch(userId, strategy, symbols) {
  const res = await authedFetch('user_signal_watch?on_conflict=user_id,strategy', {
    method: 'POST',
    headers: { Prefer: 'resolution=merge-duplicates,return=minimal' },
    body: JSON.stringify({ user_id: userId, strategy, symbols, updated_at: new Date().toISOString() }),
  });
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try { const b = await res.json(); msg = b?.message || b?.hint || b?.details || msg; } catch { /* non-JSON */ }
    throw new Error(msg);
  }
}
