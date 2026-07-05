import { useState } from 'react';
import { useTradeContext } from '../context/TradeContext';
import { useLang } from '../context/LanguageContext';
import { useStreamDisplay } from '../utils/useStreamDisplay';

// Slim, collapsible intro card shown at the top of every strategy view ("girişte").
// PRIVACY: the real strategy card renders ONLY for the admin (adminStreamInfo lazy
// chunk); everyone else sees the codename + a "details private" line — outsiders
// must get no idea what the mechanics are.
const StrategyIntro = () => {
  const { strategy } = useTradeContext();
  const { lang, t } = useLang();
  const sd = useStreamDisplay();
  // Default COLLAPSED — the header is just a trigger; detail appears on click.
  const [open, setOpen] = useState(() => {
    try { return localStorage.getItem('pusu.introOpen') === '1'; } catch { return false; }
  });
  const toggle = () => {
    setOpen((o) => {
      const next = !o;
      try { localStorage.setItem('pusu.introOpen', next ? '1' : '0'); } catch { /* ignore */ }
      return next;
    });
  };

  const info = sd.info(strategy, lang) || {
    icon: '◆',
    accent: '#F0B90B',
    title: sd.name(strategy),
    tagline: t('Otonom işlem akışı · detaylar gizli'),
    summary: t('Bu akışın kuralları tescillidir ve görüntülenmez. Performansı Live/Backtest sekmelerinden izleyebilirsiniz.'),
    sections: null,
    caveat: null,
  };

  return (
    <div
      className="strategy-intro"
      style={{
        border: '1px solid var(--border, #2a2f3a)',
        borderLeft: `3px solid ${info.accent}`,
        borderRadius: 10,
        padding: open ? '12px 14px' : '8px 14px',
        margin: '0 0 14px',
        background: 'var(--panel, rgba(255,255,255,0.02))',
      }}
    >
      <div
        style={{ display: 'flex', alignItems: 'center', gap: 10, cursor: 'pointer' }}
        onClick={toggle}
        role="button"
        aria-expanded={open}
        title={open ? t('Gizle') : t('Göster')}
      >
        <span style={{ fontSize: 18 }} aria-hidden="true">{info.icon}</span>
        <span style={{ fontWeight: 700, letterSpacing: 0.4, color: info.accent }}>{info.title}</span>
        <span style={{ opacity: 0.75, fontSize: 13 }}>· {info.tagline}</span>
        <span style={{ marginLeft: 'auto', opacity: 0.6, fontSize: 12 }}>{open ? '▾' : '▸'}</span>
      </div>

      {open && (
        <div style={{ marginTop: 10 }}>
          {info.summary && (
            <p style={{ margin: '0 0 10px', fontSize: 13, lineHeight: 1.6, opacity: 0.92 }}>
              {info.summary}
            </p>
          )}
          {Array.isArray(info.sections) && info.sections.map((s, i) => (
            <div key={i} style={{ marginBottom: 8 }}>
              <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: 0.5, textTransform: 'uppercase', color: info.accent, opacity: 0.9 }}>
                {s.h}
              </div>
              <div style={{ fontSize: 13, lineHeight: 1.55, opacity: 0.85 }}>{s.t}</div>
            </div>
          ))}
          {/* backward-compat: old bullet-only entries still render */}
          {!info.sections && Array.isArray(info.bullets) && (
            <ul style={{ margin: 0, paddingLeft: 18, lineHeight: 1.55, fontSize: 13 }}>
              {info.bullets.map((b, i) => <li key={i} style={{ opacity: 0.9, marginBottom: 3 }}>{b}</li>)}
            </ul>
          )}
          {info.caveat && (
            <div style={{
              marginTop: 10, padding: '7px 10px', fontSize: 12, lineHeight: 1.5,
              opacity: 0.85, fontStyle: 'italic', borderRadius: 7,
              background: 'rgba(245,185,66,0.10)', border: '1px solid rgba(245,185,66,0.25)',
            }}>
              ⚠ {info.caveat}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default StrategyIntro;
