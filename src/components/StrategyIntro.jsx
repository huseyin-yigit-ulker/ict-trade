import { useState } from 'react';
import { useTradeContext } from '../context/TradeContext';
import { useLang } from '../context/LanguageContext';
import { infoFor } from '../utils/strategyInfo';

// Slim, collapsible intro card shown at the top of every strategy view ("girişte").
// Content is bilingual (tr/en) via strategyInfo + the active lang. Collapse state is
// remembered globally so it doesn't nag on every visit.
const StrategyIntro = () => {
  const { strategy } = useTradeContext();
  const { lang, t } = useLang();
  const [open, setOpen] = useState(() => {
    try { return localStorage.getItem('pusu.introOpen') !== '0'; } catch { return true; }
  });
  const toggle = () => {
    setOpen((o) => {
      const next = !o;
      try { localStorage.setItem('pusu.introOpen', next ? '1' : '0'); } catch { /* ignore */ }
      return next;
    });
  };

  const info = infoFor(strategy, lang);
  if (!info) return null;

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
        <>
          <ul style={{ margin: '10px 0 0', paddingLeft: 18, lineHeight: 1.55, fontSize: 13 }}>
            {info.bullets.map((b, i) => (
              <li key={i} style={{ opacity: 0.9, marginBottom: 3 }}>{b}</li>
            ))}
          </ul>
          {info.caveat && (
            <div style={{ marginTop: 8, fontSize: 12, opacity: 0.7, fontStyle: 'italic' }}>
              ⚠ {info.caveat}
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default StrategyIntro;
