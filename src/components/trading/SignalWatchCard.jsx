import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useLang } from '../../context/LanguageContext';
import { getJSON } from '../../utils/supa';
import { useStreamDisplay } from '../../utils/useStreamDisplay';
import { LIVE_STREAM_KEYS } from '../../utils/streamMask';
import { fetchWatch, saveWatch } from '../../utils/signalWatch';

// Signal-notification watchlist: per LIVE stream, pick the symbols you want a phone
// push for when a fresh signal fires. Mirrors SymbolPickerCard's stream-segmented
// multi-select, but writes the notification table (user_signal_watch) — NOT the
// executor's user_stream_settings. Renders codenames via useStreamDisplay.
// The master gate is the "Sinyal yayınları" (notify_signals) toggle above it; empty
// across every stream keeps the legacy "all signals" broadcast.

// version key -> stream_universe bucket (executor vocab: opus/midas).
// (d30so8f3vg/NOVA 2026-07-07'de canlıdan çıktı — LIVE_STREAM_KEYS'ten düştüğü için burada
// listelenmez; eski kayıtlı izleme satırları zararsız şekilde pasif kalır.)
const UNI_BUCKET = { d30so8f3h7: 'opus', midas: 'midas' };

export default function SignalWatchCard() {
  const { t } = useLang();
  const { user } = useAuth();
  const sd = useStreamDisplay();
  const [sel, setSel] = useState(LIVE_STREAM_KEYS[0]);
  const [universe, setUniverse] = useState({});   // bucket -> [symbols]
  const [watch, setWatch] = useState({});          // strategyKey -> [symbols]
  const [pending, setPending] = useState(new Set());
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(null);

  const load = useCallback(async () => {
    try {
      const [uni, w] = await Promise.all([
        getJSON('stream_universe?select=stream,symbol&order=symbol.asc'),
        fetchWatch(),
      ]);
      const u = {};
      for (const r of uni || []) (u[r.stream] = u[r.stream] || []).push(r.symbol);
      setUniverse(u);
      setWatch(w);
    } catch (e) {
      setNote({ kind: 'err', text: e.message });
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const uniSyms = universe[UNI_BUCKET[sel]] || [];

  // Preselect the saved list whenever the selected stream / fresh data lands.
  useEffect(() => {
    setPending(new Set(watch[sel] || []));
    setNote(null);
  }, [sel, watch]);

  const toggle = (sym) => {
    if (!uniSyms.includes(sym)) return;
    setPending((p) => {
      const n = new Set(p);
      if (n.has(sym)) n.delete(sym); else n.add(sym);
      return n;
    });
  };

  const save = async () => {
    if (busy || !user?.id) return;
    setBusy(true);
    setNote(null);
    const symbols = [...pending].sort();
    try {
      await saveWatch(user.id, sel, symbols);
      setWatch((w) => ({ ...w, [sel]: symbols }));
      setNote({ kind: 'ok', text: t('Bildirim listesi kaydedildi.') });
    } catch (e) {
      setNote({ kind: 'err', text: e.message });
    } finally {
      setBusy(false);
    }
  };

  const totalWatched = Object.values(watch).reduce((n, arr) => n + (arr?.length || 0), 0);

  return (
    <div className="notif-watch">
      <div className="form-note">
        {t('Seçtiğin strateji + sembollerde sinyal oluşunca telefon bildirimi gelir. Hiçbir sembol seçmezsen tüm sinyaller gelir (eski davranış).')}
      </div>

      <div className="seg seg--rows" role="group" aria-label="strategy">
        {LIVE_STREAM_KEYS.map((k) => (
          <button key={k} type="button" className={sel === k ? 'active' : ''} onClick={() => setSel(k)}>
            {sd.name(k)}
          </button>
        ))}
      </div>

      {uniSyms.length === 0 ? (
        <div className="summary-empty">{t('Bu akış için sembol listesi boş.')}</div>
      ) : (
        <div className="settings-symbols">
          {uniSyms.map((sym) => (
            <label key={sym} className={pending.has(sym) ? 'on' : ''}>
              <input type="checkbox" checked={pending.has(sym)} onChange={() => toggle(sym)} />
              {sym}
            </label>
          ))}
        </div>
      )}

      <div className="settings-symbol-actions">
        <button className="apply-btn" type="button" disabled={busy} onClick={save}>
          {busy ? '…' : t('Kaydet')} ({pending.size} {t('seçili')})
        </button>
      </div>
      {note && <div className={`form-note form-note--${note.kind}`}>{note.text}</div>}
      {totalWatched > 0 && (
        <div className="form-note">{t('Aktif izleme: {n} sembol', { n: totalWatched })}</div>
      )}
    </div>
  );
}
