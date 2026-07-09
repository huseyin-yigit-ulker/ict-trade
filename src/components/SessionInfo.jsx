import { useEffect, useMemo, useState } from 'react';
import { useLang } from '../context/LanguageContext';
import { marketSessions, etParts, US_HOLIDAYS, usSignalsActive } from '../utils/sessions';

// "Seanslar" info window — which markets are active vs closed right now, the schedule, and
// US holidays. The US gate (pre-market+regular, ex-holidays) actually filters stock-perp
// signals (backend: sync/donchian/strategy.py); metals/crypto are shown for information only.
const STATE_STYLE = {
  open:      { dot: '#0ECB81', label: '#0ECB81' },
  premarket: { dot: '#F5B942', label: '#F5B942' },
  break:     { dot: '#F5B942', label: '#F5B942' },
  closed:    { dot: '#5E6673', label: '#848E9C' },
};

const fmtHoliday = (iso) => {
  const [y, m, d] = iso.split('-');
  const mo = ['Oca', 'Şub', 'Mar', 'Nis', 'May', 'Haz', 'Tem', 'Ağu', 'Eyl', 'Eki', 'Kas', 'Ara'][+m - 1];
  return `${+d} ${mo} ${y}`;
};

const SessionInfo = ({ onClose }) => {
  const { t } = useLang();
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 15_000);
    const onEsc = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onEsc);
    return () => { clearInterval(id); window.removeEventListener('keydown', onEsc); };
  }, [onClose]);

  const sessions = marketSessions(now);
  const et = etParts(now);
  const utc = `${String(now.getUTCHours()).padStart(2, '0')}:${String(now.getUTCMinutes()).padStart(2, '0')}`;
  const todayET = et.date;
  const isHolidayToday = US_HOLIDAYS.has(todayET);
  const usActive = usSignalsActive(now);

  const upcoming = useMemo(() => {
    return [...US_HOLIDAYS].filter((d) => d >= todayET).sort().slice(0, 3);
  }, [todayET]);

  const card = { background: 'var(--panel)', border: '1px solid var(--border)', borderRadius: 8 };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} style={{
        ...card, width: 'min(560px, 94vw)', maxHeight: '88vh', overflowY: 'auto',
        padding: 0, boxShadow: '0 12px 40px rgba(0,0,0,0.5)',
      }}>
        {/* header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          padding: '14px 18px', borderBottom: '1px solid var(--border)', background: 'var(--panel-2)' }}>
          <div>
            <div style={{ fontWeight: 700, letterSpacing: '0.04em' }}>🕑 {t('Seans Durumu')}</div>
            <div style={{ fontSize: 11, color: 'var(--muted, #848E9C)', marginTop: 2, fontFamily: 'var(--mono)' }}>
              {utc} UTC · {et.hhmm} ET ({['Paz', 'Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt'][et.weekday]})
            </div>
          </div>
          <button className="close-modern" onClick={onClose}>
            <span className="close-label">{t('Kapat')}</span><span className="esc-pill neo">ESC</span>
          </button>
        </div>

        {/* market rows */}
        <div style={{ padding: 16, display: 'grid', gap: 10 }}>
          {sessions.map((s) => {
            const st = STATE_STYLE[s.state] || STATE_STYLE.closed;
            return (
              <div key={s.key} style={{ ...card, padding: '12px 14px', display: 'flex',
                alignItems: 'center', justifyContent: 'space-between', gap: 12 }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <span style={{ width: 9, height: 9, borderRadius: '50%', background: st.dot,
                      boxShadow: s.state !== 'closed' ? `0 0 8px ${st.dot}` : 'none' }} />
                    <b>{s.name}</b>
                    {s.gated && (
                      <span title={t('Sinyaller bu seansa göre filtrelenir')} style={{ fontSize: 9,
                        padding: '1px 5px', borderRadius: 3, border: '1px solid var(--border)',
                        color: 'var(--muted,#848E9C)', letterSpacing: '0.06em' }}>SİNYAL GATE</span>
                    )}
                  </div>
                  <div style={{ fontSize: 11, color: 'var(--muted,#848E9C)', marginTop: 3 }}>
                    {s.symbols} · {s.note}
                  </div>
                </div>
                <div style={{ color: st.label, fontWeight: 700, fontSize: 13, whiteSpace: 'nowrap' }}>
                  {s.label}
                </div>
              </div>
            );
          })}
        </div>

        {/* what it means for signals */}
        <div style={{ padding: '0 16px 14px' }}>
          <div style={{ ...card, padding: '11px 14px', fontSize: 12, lineHeight: 1.5 }}>
            <b style={{ color: usActive ? '#0ECB81' : '#F6465D' }}>
              {usActive ? t('ABD hisse sinyalleri ŞU AN aktif') : t('ABD hisse sinyalleri ŞU AN pasif')}
            </b>
          </div>
        </div>

        {/* holidays */}
        <div style={{ padding: '0 16px 18px' }}>
          <div style={{ fontSize: 11, color: 'var(--muted,#848E9C)', letterSpacing: '0.06em',
            marginBottom: 6, textTransform: 'uppercase' }}>{t('ABD Borsa Tatilleri (NYSE)')}</div>
          {isHolidayToday && (
            <div style={{ color: '#F6465D', fontWeight: 700, fontSize: 12, marginBottom: 6 }}>
              ● {t('Bugün tatil — ABD hisse sinyali yok')}
            </div>
          )}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {upcoming.length ? upcoming.map((d) => (
              <span key={d} style={{ ...card, padding: '4px 9px', fontSize: 11,
                fontFamily: 'var(--mono)', color: 'var(--text)' }}>{fmtHoliday(d)}</span>
            )) : <span style={{ fontSize: 11, color: 'var(--muted,#848E9C)' }}>{t('Yaklaşan tatil yok')}</span>}
          </div>
        </div>
      </div>
    </div>
  );
};

export default SessionInfo;
