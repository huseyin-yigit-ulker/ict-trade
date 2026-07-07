import { useCallback, useEffect, useMemo, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useLang } from '../../context/LanguageContext';
import { getJSON } from '../../utils/supa';
import { useStreamDisplay } from '../../utils/useStreamDisplay';
import {
  STREAM_ROWS, rowKey, netLabel, patchStreamSettings, upsertStreamSettings,
  SETTINGS_EVT, emitSettingsChanged, fetchRanking, MAJORS,
} from './streams';

// Hazır Şablonlar — one-click presets for new users: each template bundles a
// symbol suggestion (top-N of the stream's backtest ranking, intersected with
// the server-side universe; majors-first fallback if the ranking RPC is down)
// with matching risk limits. Applying NEVER enables the stream — activation
// stays an explicit separate step. Anonymization: templates are described only
// in risk terms (how much / how many); nothing about how any stream trades.

const TEMPLATES = [
  {
    id: 'starter',
    topN: 3,
    fields: { risk_usd: 2, max_concurrent: 2, max_total_risk_usd: 4, daily_loss_cap_usd: 6 },
  },
  {
    id: 'balanced',
    topN: 5,
    fields: { risk_usd: 5, max_concurrent: 3, max_total_risk_usd: 15, daily_loss_cap_usd: 20 },
  },
  {
    id: 'wide',
    topN: Infinity,
    fields: { risk_usd: 5, max_concurrent: 5, max_total_risk_usd: 25, daily_loss_cap_usd: null },
  },
];

export default function TemplatesCard() {
  const { t } = useLang();
  const { user } = useAuth();
  const sd = useStreamDisplay();
  const [sel, setSel] = useState(rowKey(STREAM_ROWS[0]));
  const [universe, setUniverse] = useState({});   // stream -> [symbols]
  const [settings, setSettings] = useState({});   // rowKey -> row
  const [ranked, setRanked] = useState(null);     // ranked symbols for the selected stream (null = loading)
  const [busy, setBusy] = useState(null);         // template id being applied
  const [note, setNote] = useState(null);

  const TPL_TEXT = {
    starter:  { name: t('Temkinli Başlangıç'), desc: t('Küçük risk, az sembol — sistemi tanımak için.') },
    balanced: { name: t('Dengeli'),            desc: t('Orta risk, önerilen sembol seti — çoğu kullanıcı için.') },
    wide:     { name: t('Geniş Portföy'),      desc: t('Tüm sembol listesi, standart limitler — deneyimli kullanıcı için.') },
  };

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
  const uniSyms = useMemo(() => universe[def.stream] || [], [universe, def.stream]);

  // Suggested symbol order for the selected stream: backtest ranking ∩ universe,
  // topped up with the rest of the universe; majors-first if the RPC fails.
  useEffect(() => {
    let alive = true;
    setRanked(null);
    fetchRanking(def.version)
      .then((rows) => { if (alive) setRanked(rows.map((r) => r.symbol)); })
      .catch(() => { if (alive) setRanked(MAJORS); });
    return () => { alive = false; };
  }, [def.version]);

  const suggestedOrder = useMemo(() => {
    const pref = (ranked || MAJORS).filter((s) => uniSyms.includes(s));
    const rest = uniSyms.filter((s) => !pref.includes(s));
    return [...pref, ...rest];
  }, [ranked, uniSyms]);

  const symbolsFor = (tpl) =>
    suggestedOrder.slice(0, Math.min(tpl.topN, suggestedOrder.length));

  const apply = async (tpl) => {
    if (busy || !user?.id) return;
    const symbols = symbolsFor(tpl).slice().sort();
    if (!symbols.length) {
      setNote({ kind: 'err', text: t('Bu akış için sembol listesi boş.') });
      return;
    }
    setBusy(tpl.id);
    setNote(null);
    const cur = settings[sel];
    try {
      if (cur?.id) await patchStreamSettings(cur.id, { ...tpl.fields, symbols });
      else await upsertStreamSettings(user.id, def.stream, def.network, { ...tpl.fields, enabled: false, symbols });
      setNote({ kind: 'ok', text: t('“{name}” şablonu uygulandı — akışı “Akış Aktivasyonu” kartından açabilirsiniz.', { name: TPL_TEXT[tpl.id].name }) });
      emitSettingsChanged();
    } catch (e) {
      setNote({ kind: 'err', text: e.message });
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="overview-card settings-card settings-card--wide">
      <div className="summary-title">{t('Hazır Şablonlar')}</div>
      <p className="setup-step__desc">
        {t('Sembol seti + risk limitlerini tek tıkla ayarlayan paketler. Uygulamak akışı BAŞLATMAZ — aktivasyon ayrı ve onaylı bir adımdır.')}
      </p>

      <div className="seg seg--rows" role="group" aria-label="stream">
        {STREAM_ROWS.map((d) => (
          <button key={rowKey(d)} type="button" className={sel === rowKey(d) ? 'active' : ''}
            onClick={() => setSel(rowKey(d))}>
            {sd.name(d.maskKey)}·{netLabel(d.network)}
          </button>
        ))}
      </div>

      <div className="tpl-grid">
        {TEMPLATES.map((tpl) => {
          const syms = symbolsFor(tpl);
          const txt = TPL_TEXT[tpl.id];
          return (
            <div key={tpl.id} className="tpl-card">
              <div className="tpl-card__name">{txt.name}</div>
              <div className="tpl-card__desc">{txt.desc}</div>
              <ul className="tpl-card__meta">
                <li><span>{t('İşlem başına risk (USD)')}</span><b>{tpl.fields.risk_usd}</b></li>
                <li><span>{t('Maks. eşzamanlı pozisyon')}</span><b>{tpl.fields.max_concurrent}</b></li>
                <li><span>{t('Maks. toplam risk (USD)')}</span><b>{tpl.fields.max_total_risk_usd}</b></li>
                <li>
                  <span>{t('Günlük zarar limiti (USD)')}</span>
                  <b>{tpl.fields.daily_loss_cap_usd ?? t('kapalı')}</b>
                </li>
              </ul>
              <div className="tpl-card__syms">
                {ranked === null && uniSyms.length === 0
                  ? <span className="tpl-sym tpl-sym--ghost">{t('Yükleniyor…')}</span>
                  : syms.map((s) => <span key={s} className="tpl-sym">{s.replace(/USDT$/, '')}</span>)}
              </div>
              <button className="apply-btn" type="button" disabled={!!busy || !syms.length}
                onClick={() => apply(tpl)}>
                {busy === tpl.id ? '…' : t('Uygula')}
              </button>
            </div>
          );
        })}
      </div>

      {note && <div className={`form-note form-note--${note.kind}`}>{note.text}</div>}
      <div className="form-note">
        {t('Sembol önerisi backtest sıralamasından gelir; limitleri bakiyenize göre seçin — sunucu, toplam riskin bakiyenin %25’ini aşmasını engeller.')}
      </div>
    </section>
  );
}
