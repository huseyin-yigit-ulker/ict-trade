import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useLang } from '../../context/LanguageContext';
import { getJSON } from '../../utils/supa';
import { useStreamDisplay } from '../../utils/useStreamDisplay';
import {
  STREAM_ROWS, rowKey, netLabel, DEFAULTS, patchStreamSettings, upsertStreamSettings,
  SETTINGS_EVT, emitSettingsChanged,
} from './streams';

// Per-(stream, network) risk limits. Client-side advisory only — the DB trigger
// hard-blocks risk_usd × max_concurrent > 25% of the verified key balance; here we
// warn amber from 10% so the user sees it coming. Stream names resolve through
// useStreamDisplay (codenames for non-admins).

export default function RiskCard() {
  const { t } = useLang();
  const { user } = useAuth();
  const sd = useStreamDisplay();
  const [sel, setSel] = useState(rowKey(STREAM_ROWS[0]));
  const [settings, setSettings] = useState({});   // rowKey -> row
  const [balances, setBalances] = useState({});   // network -> balance_usdt of latest valid key
  const [form, setForm] = useState({ risk_usd: '', max_concurrent: '', max_total_risk_usd: '', daily_loss_cap_usd: '' });
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(null);         // {kind:'ok'|'err', text}

  const load = useCallback(async () => {
    try {
      const [rows, keys] = await Promise.all([
        getJSON('user_stream_settings?select=*'),
        getJSON('user_api_keys_public?select=network,status,balance_usdt,created_at&order=created_at.desc'),
      ]);
      const map = {};
      for (const r of rows || []) map[`${r.stream}:${r.network}`] = r;
      setSettings(map);
      const bal = {};
      for (const kr of keys || []) {
        if (kr.status === 'valid' && bal[kr.network] === undefined) bal[kr.network] = kr.balance_usdt;
      }
      setBalances(bal);
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

  // Mirror the selected row into the editors whenever selection/data changes.
  useEffect(() => {
    setForm({
      risk_usd: cur?.risk_usd ?? DEFAULTS.risk_usd,
      max_concurrent: cur?.max_concurrent ?? DEFAULTS.max_concurrent,
      max_total_risk_usd: cur?.max_total_risk_usd ?? DEFAULTS.max_total_risk_usd,
      daily_loss_cap_usd: cur?.daily_loss_cap_usd ?? '',
    });
    setNote(null);
  }, [sel, cur]);

  const set = (field) => (e) => setForm((f) => ({ ...f, [field]: e.target.value }));

  const bal = balances[def.network];
  const exposure = (Number(form.risk_usd) || 0) * (Number(form.max_concurrent) || 0);
  const pct = bal != null && Number(bal) > 0 ? (exposure / Number(bal)) * 100 : null;

  const valid = Number(form.risk_usd) > 0
    && Number(form.max_concurrent) >= 1
    && Number(form.max_total_risk_usd) > 0
    && (form.daily_loss_cap_usd === '' || Number(form.daily_loss_cap_usd) > 0);

  const save = async () => {
    if (busy || !valid || !user?.id) return;
    setBusy(true);
    setNote(null);
    const fields = {
      risk_usd: Number(form.risk_usd),
      max_concurrent: Math.round(Number(form.max_concurrent)),
      max_total_risk_usd: Number(form.max_total_risk_usd),
      daily_loss_cap_usd: form.daily_loss_cap_usd === '' ? null : Number(form.daily_loss_cap_usd),
    };
    try {
      if (cur?.id) await patchStreamSettings(cur.id, fields);
      else await upsertStreamSettings(user.id, def.stream, def.network, { ...fields, enabled: false, symbols: [] });
      setNote({ kind: 'ok', text: t('Kaydedildi.') });
      emitSettingsChanged();
    } catch (e) {
      setNote({ kind: 'err', text: e.message });   // trigger message verbatim
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="overview-card settings-card">
      <div className="summary-title">{t('Risk Ayarları')}</div>

      <div className="seg seg--rows" role="group" aria-label="stream">
        {STREAM_ROWS.map((d) => (
          <button key={rowKey(d)} type="button" className={sel === rowKey(d) ? 'active' : ''}
            onClick={() => setSel(rowKey(d))}>
            {sd.name(d.maskKey)}·{netLabel(d.network)}
          </button>
        ))}
      </div>

      <div className="settings-row">
        <span>{t('Bakiye')} · {def.network === 'mainnet' ? 'Mainnet' : 'Testnet'}</span>
        <b>{bal != null ? `${Number(bal).toFixed(2)} USDT` : '—'}</b>
      </div>

      <div className="settings-row">
        <span>{t('İşlem başına risk (USD)')}</span>
        <input className="tinput tinput--num" type="number" min="0" step="0.5" inputMode="decimal"
          value={form.risk_usd} onChange={set('risk_usd')} />
      </div>
      <div className="settings-row">
        <span>{t('Maks. eşzamanlı pozisyon')}</span>
        <input className="tinput tinput--num" type="number" min="1" step="1" inputMode="numeric"
          value={form.max_concurrent} onChange={set('max_concurrent')} />
      </div>
      <div className="settings-row">
        <span>{t('Maks. toplam risk (USD)')}</span>
        <input className="tinput tinput--num" type="number" min="0" step="1" inputMode="decimal"
          value={form.max_total_risk_usd} onChange={set('max_total_risk_usd')} />
      </div>
      <div className="settings-row">
        <span>{t('Günlük zarar limiti (USD)')}</span>
        <input className="tinput tinput--num" type="number" min="0" step="1" inputMode="decimal"
          placeholder={t('kapalı')} value={form.daily_loss_cap_usd} onChange={set('daily_loss_cap_usd')} />
      </div>

      {pct != null && pct > 10 && (
        <div className="form-note form-note--warn">
          {t("Balansın %{pct}'i riske giriyor (risk × eşzamanlı).", { pct: pct.toFixed(1) })}
        </div>
      )}
      {pct != null && pct > 25 && (
        <div className="form-note form-note--err">{t('%25 üzeri sunucu tarafından engellenir.')}</div>
      )}

      <button className="apply-btn" type="button" disabled={busy || !valid} onClick={save}>
        {busy ? '…' : t('Kaydet')}
      </button>
      {note && <div className={`form-note form-note--${note.kind}`}>{note.text}</div>}
    </section>
  );
}
