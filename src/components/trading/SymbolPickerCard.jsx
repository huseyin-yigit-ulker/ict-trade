import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useLang } from '../../context/LanguageContext';
import { getJSON } from '../../utils/supa';
import { useStreamDisplay } from '../../utils/useStreamDisplay';
import {
  STREAM_ROWS, rowKey, netLabel, DEFAULTS, patchStreamSettings, upsertStreamSettings,
  SETTINGS_EVT, emitSettingsChanged, fetchRanking,
} from './streams';

// Symbol selection per (stream, network) from the server-side stream_universe,
// with the backtest ranking (shared fetchRanking in streams.js) as an
// informational side panel. Clicking a ranking row toggles that symbol's chip.

const fmtR = (v) => `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(1)}R`;

export default function SymbolPickerCard() {
  const { t } = useLang();
  const { user } = useAuth();
  const sd = useStreamDisplay();
  const [sel, setSel] = useState(rowKey(STREAM_ROWS[0]));
  const [universe, setUniverse] = useState({});   // stream -> [symbols]
  const [settings, setSettings] = useState({});   // rowKey -> row
  const [pending, setPending] = useState(new Set());
  const [rank, setRank] = useState(null);         // null = loading
  const [rankFailed, setRankFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(null);

  const load = useCallback(async () => {
    try {
      const [uni, rows] = await Promise.all([
        getJSON('stream_universe?select=stream,symbol&order=symbol.asc'),
        getJSON('user_stream_settings?select=*'),
      ]);
      const u = {};
      for (const r of uni || []) (u[r.stream] = u[r.stream] || []).push(r.symbol);
      setUniverse(u);
      const map = {};
      for (const r of rows || []) map[`${r.stream}:${r.network}`] = r;
      setSettings(map);
    } catch (e) {
      setNote({ kind: 'err', text: e.message });
    }
  }, []);

  useEffect(() => {
    load();
    window.addEventListener(SETTINGS_EVT, load);
    return () => window.removeEventListener(SETTINGS_EVT, load);
  }, [load]);

  const def = STREAM_ROWS.find((d) => rowKey(d) === sel) || STREAM_ROWS[0];
  const cur = settings[sel];
  const uniSyms = universe[def.stream] || [];

  // Preselect the saved list whenever the selection / fresh data lands.
  useEffect(() => {
    setPending(new Set(cur?.symbols || []));
    setNote(null);
  }, [sel, cur]);

  // Ranking follows the STREAM (version tag is sent to the RPC, never displayed).
  useEffect(() => {
    let alive = true;
    setRank(null);
    setRankFailed(false);
    fetchRanking(def.version)
      .then((r) => { if (alive) setRank(r); })
      .catch(() => { if (alive) { setRank([]); setRankFailed(true); } });
    return () => { alive = false; };
  }, [def.version]);

  const toggle = (sym) => {
    if (!uniSyms.includes(sym)) return;   // ranking may list symbols outside the universe
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
      if (cur?.id) await patchStreamSettings(cur.id, { symbols });
      else await upsertStreamSettings(user.id, def.stream, def.network, { ...DEFAULTS, enabled: false, symbols });
      setNote({ kind: 'ok', text: t('Semboller kaydedildi.') });
      emitSettingsChanged();
    } catch (e) {
      setNote({ kind: 'err', text: e.message });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="overview-card settings-card settings-card--wide">
      <div className="summary-title">{t('Sembol Seçimi')}</div>

      <div className="seg seg--rows" role="group" aria-label="stream">
        {STREAM_ROWS.map((d) => (
          <button key={rowKey(d)} type="button" className={sel === rowKey(d) ? 'active' : ''}
            onClick={() => setSel(rowKey(d))}>
            {sd.name(d.maskKey)}·{netLabel(d.network)}
          </button>
        ))}
      </div>

      <div className="sympick">
        <div className="sympick__pick">
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
        </div>

        <div className="sympick__rank">
          <div className="sympick__rank-title">{t('Backtest Sıralaması')}</div>
          {rank === null ? (
            <div className="summary-empty">{t('Yükleniyor…')}</div>
          ) : rankFailed ? (
            <div className="summary-empty">{t('Sıralama alınamadı.')}</div>
          ) : rank.length === 0 ? (
            <div className="summary-empty">{t('Kayıt yok')}</div>
          ) : (
            <div className="rank-wrap">
              <table className="rank-table">
                <thead>
                  <tr>
                    <th>{t('Sembol')}</th>
                    <th>R</th>
                    <th>WR%</th>
                    <th>{t('İşlem')}</th>
                  </tr>
                </thead>
                <tbody>
                  {rank.map((r) => {
                    const inUni = uniSyms.includes(r.symbol);
                    const on = pending.has(r.symbol);
                    return (
                      <tr
                        key={r.symbol}
                        className={`${on ? 'sel' : ''}${inUni ? '' : ' off'}`}
                        onClick={() => toggle(r.symbol)}
                        title={inUni ? r.symbol : `${r.symbol} — ${t('Bu akışın sembol listesinde değil.')}`}
                      >
                        <td>{r.symbol}</td>
                        <td className={Number(r.total_r) >= 0 ? 'win' : 'loss'}>{fmtR(r.total_r)}</td>
                        <td>{r.win_rate != null ? Number(r.win_rate).toFixed(1) : '—'}</td>
                        <td>{r.total_trades ?? '—'}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          <div className="form-note">{t('Sıralama sadece bilgi amaçlı — seçim sizin.')}</div>
        </div>
      </div>
    </section>
  );
}
