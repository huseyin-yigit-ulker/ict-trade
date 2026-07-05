import { useCallback, useEffect, useState } from 'react';
import { useLang } from '../../context/LanguageContext';
import { getJSON } from '../../utils/supa';
import { useStreamDisplay } from '../../utils/useStreamDisplay';
import {
  STREAM_ROWS, rowKey, netLabel, patchStreamSettings, SETTINGS_EVT, emitSettingsChanged,
} from './streams';

// Per-user stream activation — one real-money row (typed confirmation) + two paper
// (testnet) rows. Stream names resolve through useStreamDisplay (codenames for
// non-admins). Enable/disable updates the user's user_stream_settings row; the DB
// trigger is the real gate (valid key, one-way mode, risk ≤ 25% of balance) and its
// exception text is surfaced VERBATIM.

const CONFIRM_PHRASE = 'GERÇEK PARA';

export default function StreamActivationCard() {
  const { t } = useLang();
  const sd = useStreamDisplay();
  const titleOf = (d) => `${sd.name(d.maskKey)} · ${netLabel(d.network, true)}`;
  const [settings, setSettings] = useState({});     // rowKey -> user_stream_settings row
  const [notes, setNotes] = useState({});           // rowKey -> {kind:'ok'|'err'|'warn', text}
  const [busy, setBusy] = useState({});             // rowKey -> bool
  const [confirming, setConfirming] = useState(null); // rowKey awaiting the typed confirmation
  const [confirmText, setConfirmText] = useState('');
  const [loadErr, setLoadErr] = useState('');

  const load = useCallback(async () => {
    try {
      const rows = await getJSON('user_stream_settings?select=*');
      const map = {};
      for (const r of rows || []) map[`${r.stream}:${r.network}`] = r;
      setSettings(map);
      setLoadErr('');
    } catch (e) {
      setLoadErr(e.message);
    }
  }, []);

  useEffect(() => {
    load();
    window.addEventListener(SETTINGS_EVT, load);
    return () => window.removeEventListener(SETTINGS_EVT, load);
  }, [load]);

  const setNote = (k, kind, text) =>
    setNotes((n) => ({ ...n, [k]: text ? { kind, text } : undefined }));

  const run = async (k, fn, okText) => {
    setBusy((b) => ({ ...b, [k]: true }));
    setNote(k, null, '');
    try {
      await fn();
      setNote(k, 'ok', okText);
      emitSettingsChanged();   // our own listener refetches too
    } catch (e) {
      setNote(k, 'err', e.message);   // DB trigger message, verbatim
    } finally {
      setBusy((b) => ({ ...b, [k]: false }));
    }
  };

  const enable = (def, row) => {
    const k = rowKey(def);
    setConfirming(null);
    setConfirmText('');
    return run(k, () => patchStreamSettings(row.id, { enabled: true, drain: false, kill_requested: false }),
      t('Akış etkin.'));
  };

  const toggle = (def) => {
    const k = rowKey(def);
    const row = settings[k];
    if (busy[k]) return;
    if (row?.enabled) {
      // Disable → drain: open positions keep being managed, no new entries.
      run(k, () => patchStreamSettings(row.id, { enabled: false, drain: true }),
        t('Akış kapatıldı — açık pozisyon varsa drain modunda yönetilip kapanır; yeni giriş açılmaz.'));
      return;
    }
    if (!row || !(row.symbols || []).length) {
      setNote(k, 'err', t('Önce sembol seçin — "Sembol Seçimi" kartından bu akış için en az bir sembol kaydedin.'));
      return;
    }
    if (def.real) {
      // Real money needs the typed confirmation below the row.
      setConfirming(k);
      setConfirmText('');
      setNote(k, null, '');
      return;
    }
    enable(def, row);
  };

  const kill = (def) => {
    const k = rowKey(def);
    const row = settings[k];
    if (!row || busy[k]) return;
    const ok = window.confirm(
      t('{name}: TÜM pozisyonlar piyasa emriyle kapatılacak ve akış devre dışı kalacak. Emin misiniz?', { name: titleOf(def) }),
    );
    if (!ok) return;
    run(k, () => patchStreamSettings(row.id, { kill_requested: true }),
      t('≤2 dk içinde tüm pozisyonlar kapatılacak ve akış devre dışı kalacak.'));
  };

  return (
    <section className="overview-card settings-card">
      <div className="summary-title">{t('Akış Aktivasyonu')}</div>
      {loadErr && <div className="form-note form-note--err">{loadErr}</div>}

      {STREAM_ROWS.map((def) => {
        const k = rowKey(def);
        const row = settings[k];
        const note = notes[k];
        return (
          <div key={k} className="stream-row">
            <div className="stream-row__head">
              <span className="stream-row__name">{titleOf(def)}</span>
              {def.real
                ? <span className="badge-real">{t('GERÇEK PARA')}</span>
                : <span className="chip chip--warn">PAPER</span>}
              {row?.kill_requested && <span className="chip chip--err">KILL</span>}
              {row?.drain && !row?.enabled && <span className="chip chip--warn">DRAIN</span>}
              <div className="stream-row__acts">
                {row?.enabled && (
                  <button className="kill-btn" type="button" disabled={busy[k]} onClick={() => kill(def)}>
                    KILL
                  </button>
                )}
                <button
                  type="button"
                  role="switch"
                  aria-checked={!!row?.enabled}
                  aria-label={titleOf(def)}
                  className={`tog${row?.enabled ? ' on' : ''}`}
                  disabled={busy[k]}
                  onClick={() => toggle(def)}
                />
              </div>
            </div>

            {confirming === k && (
              <div className="stream-confirm">
                <div className="form-note form-note--warn">
                  {t('GERÇEK PARA modunu açıyorsunuz. Onaylamak için kutuya "GERÇEK PARA" yazın.')}
                </div>
                <div className="stream-confirm__row">
                  <input
                    className="tinput"
                    value={confirmText}
                    onChange={(e) => setConfirmText(e.target.value)}
                    placeholder={CONFIRM_PHRASE}
                    autoCapitalize="characters" autoComplete="off" spellCheck={false}
                  />
                  <button
                    className="apply-btn" type="button"
                    disabled={confirmText !== CONFIRM_PHRASE || busy[k]}
                    onClick={() => enable(def, settings[k])}
                  >
                    {t('Onayla')}
                  </button>
                  <button className="apply-btn ghost" type="button"
                    onClick={() => { setConfirming(null); setConfirmText(''); }}>
                    {t('Vazgeç')}
                  </button>
                </div>
              </div>
            )}

            {note && <div className={`form-note form-note--${note.kind}`}>{note.text}</div>}
          </div>
        );
      })}

      <div className="form-note">
        {t('{name} yalnız paper (testnet) çalışır; gerçek-para modu sunucu tarafından reddedilir.', { name: sd.name('midas') })}
      </div>
    </section>
  );
}
