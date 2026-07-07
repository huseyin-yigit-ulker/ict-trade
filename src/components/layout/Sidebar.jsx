import { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useLang } from '../../context/LanguageContext';
import { useTheme } from '../../context/ThemeContext';
import { useTradeContext } from '../../context/TradeContext';
import { useStreamDisplay } from '../../utils/useStreamDisplay';
import { slugFor } from '../../utils/streamMask';
import { useExecActivation } from '../../utils/execActivation';
import PusuLogo from '../PusuLogo';

const IconCommand = () => (
  <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
    <circle cx="10" cy="10" r="6.4" /><circle cx="10" cy="10" r="1.5" fill="currentColor" stroke="none" />
    <line x1="10" y1="1.4" x2="10" y2="4" /><line x1="10" y1="16" x2="10" y2="18.6" />
    <line x1="1.4" y1="10" x2="4" y2="10" /><line x1="16" y1="10" x2="18.6" y2="10" />
  </svg>
);
const IconImpulse = () => (
  <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M11 1.6 3.4 11.2h4.2l-1.6 7.2 8-9.8h-4.4l1.4-7Z" />
  </svg>
);
const IconIntel = () => (
  <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M2.4 10s3-5.2 7.6-5.2S17.6 10 17.6 10s-3 5.2-7.6 5.2S2.4 10 2.4 10Z" />
    <circle cx="10" cy="10" r="2.2" />
  </svg>
);
const IconSettings = () => (
  <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round">
    <line x1="3" y1="6.5" x2="17" y2="6.5" /><circle cx="13" cy="6.5" r="2.1" fill="var(--panel)" />
    <line x1="3" y1="13.5" x2="17" y2="13.5" /><circle cx="7" cy="13.5" r="2.1" fill="var(--panel)" />
  </svg>
);
const IconHome = () => (
  <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2.6" y="2.6" width="6" height="6" rx="1.2" /><rect x="11.4" y="2.6" width="6" height="6" rx="1.2" />
    <rect x="2.6" y="11.4" width="6" height="6" rx="1.2" /><rect x="11.4" y="11.4" width="6" height="6" rx="1.2" />
  </svg>
);
// Strategies: stacked layers (a collection of strategy streams).
const IconStrategies = () => (
  <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M10 2.4 17.4 6.4 10 10.4 2.6 6.4Z" />
    <path d="M2.6 10 10 14 17.4 10" />
    <path d="M2.6 13.6 10 17.6 17.4 13.6" />
  </svg>
);
// Range: price oscillating between two horizontal boundaries (a tradeable range).
const IconRange = () => (
  <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <line x1="2.5" y1="4.5" x2="17.5" y2="4.5" />
    <line x1="2.5" y1="15.5" x2="17.5" y2="15.5" />
    <polyline points="4,10 7,5.5 10,14 13,6 16,11" strokeWidth="1.3" opacity="0.85" />
  </svg>
);
// Regime / Trend map: a price line that chops on the left, then trends up-right + arrow.
const IconRegime = () => (
  <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="2,14 5,12 7,13.5 9.5,8.5 12.5,10 17,3.5" />
    <path d="M17 3.5 H13.6 M17 3.5 V6.9" />
  </svg>
);
// Binance live (testnet): a candlestick — the live execution / open-positions view.
const IconLive = () => (
  <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <line x1="6" y1="2.5" x2="6" y2="17.5" /><rect x="3.6" y="6" width="4.8" height="6.5" rx="1" fill="currentColor" stroke="none" opacity="0.85" />
    <line x1="13.5" y1="3.5" x2="13.5" y2="16.5" /><rect x="11.1" y="7.5" width="4.8" height="5.5" rx="1" />
  </svg>
);
// TOTAL / market-cap breadth: three stacked layers (TOTAL/TOTAL2/TOTAL3) on a baseline.
const IconTotal = () => (
  <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <line x1="2.5" y1="17.5" x2="17.5" y2="17.5" />
    <rect x="3" y="11" width="3.4" height="6.5" rx="0.8" />
    <rect x="8.3" y="7" width="3.4" height="10.5" rx="0.8" />
    <rect x="13.6" y="3" width="3.4" height="14.5" rx="0.8" />
  </svg>
);
// İşlem Merkezi: a gear — per-user execution controls (keys / risk / activation).
const IconGear = () => (
  <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="10" cy="10" r="2.6" />
    <path d="M10 2.6v2.2M10 15.2v2.2M2.6 10h2.2M15.2 10h2.2M4.9 4.9l1.5 1.5M13.6 13.6l1.5 1.5M15.1 4.9l-1.5 1.5M6.4 13.6l-1.5 1.5" />
  </svg>
);
// Yönetim: a shield — the admin console.
const IconShield = () => (
  <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M10 2.4 16.4 5v5c0 4.2-2.7 6.6-6.4 7.6C6.3 16.6 3.6 14.2 3.6 10V5Z" />
    <path d="M7.2 10l2 2 3.6-3.8" />
  </svg>
);

// Stream nav data — IDENTITY-FREE by design (multi-user anonymization, 2026-07-04).
// Entries carry only routing/flag data (key/icon/modes/section/live/paper/real);
// display names + labels resolve at render time through useStreamDisplay(), which
// serves neutral codenames to everyone and the real names only to the admin (whose
// strings live in a separate lazy chunk — see utils/streamMask.js). Leaf URLs use
// the codename slug (slugFor) so raw stream keys never appear in the address bar.
const GROUPS = [
  // ── canlı modül: 2 gerçek-para akışı (2026-07-07: yalnız OPUS + MIDAS canlı; MIDAS-X mainnet) ──
  { key: 'd30so8f3h7', icon: <IconIntel />, modes: ['live', 'backtest'], live: true, real: true, section: 'live' },
  { key: 'midas',      icon: <IconIntel />, modes: ['live', 'backtest'], live: true, real: true, section: 'live' },
  // ── backtest-only araştırma akışları (d30so8f3vg 2026-07-07'de canlıdan buraya indi) ──
  { key: 'd30so8f3vg', icon: <IconIntel />, modes: ['backtest'], section: 'backtest' },
  { key: 'donchianc',  icon: <IconIntel />, modes: ['backtest'], section: 'backtest' },
  { key: 'd1h_so4c',   icon: <IconIntel />, modes: ['backtest'], section: 'backtest' },
  { key: 'd1h_so6c',   icon: <IconIntel />, modes: ['backtest'], section: 'backtest' },
  { key: 'd1h_so8c',   icon: <IconIntel />, modes: ['backtest'], section: 'backtest' },
  { key: 'd1hso4cm',   icon: <IconIntel />, modes: ['backtest'], section: 'backtest' },
  { key: 'd1hso6cm',   icon: <IconIntel />, modes: ['backtest'], section: 'backtest' },
  { key: 'd1hso8cm',   icon: <IconIntel />, modes: ['backtest'], section: 'backtest' },
  { key: 'dch30_4hc',  icon: <IconIntel />, modes: ['backtest'], section: 'backtest' },
  { key: 'dch30_4h6c', icon: <IconIntel />, modes: ['backtest'], section: 'backtest' },
  { key: 'd30_4h_soc', icon: <IconIntel />, modes: ['backtest'], section: 'backtest' },
  { key: 'd30so6c',    icon: <IconIntel />, modes: ['backtest'], section: 'backtest' },
  { key: 'd30so8c',    icon: <IconIntel />, modes: ['backtest'], section: 'backtest' },
  { key: 'd30so4cm',   icon: <IconIntel />, modes: ['backtest'], section: 'backtest' },
  { key: 'd30so6cm',   icon: <IconIntel />, modes: ['backtest'], section: 'backtest' },
  { key: 'd30so8cm',   icon: <IconIntel />, modes: ['backtest'], section: 'backtest' },
  { key: 'd30so4f3',   icon: <IconIntel />, modes: ['backtest'], section: 'backtest' },
  { key: 'd30so6f3',   icon: <IconIntel />, modes: ['backtest'], section: 'backtest' },
  { key: 'd30so8f3',   icon: <IconIntel />, modes: ['backtest'], section: 'backtest' },
];

const Sidebar = () => {
  const { user, logout, isActive, isAdmin, features } = useAuth();
  const { t, lang, setLang } = useLang();
  const { theme, setTheme } = useTheme();
  const { closeMobileNav } = useTradeContext();
  const sd = useStreamDisplay();   // codenames for everyone; real names lazy-load for admins
  const act = useExecActivation(); // ağ-bazlı kişisel aktivasyon: pano linkleri buna göre görünür

  const leafLabel = { live: t('Live'), backtest: t('Backtest') };

  // Admin-only technical sublabel; drops the redundant "NAME · " prefix when present.
  const techLabel = (key) => {
    if (!sd.isAdmin) return null;
    const n = sd.name(key);
    const l = sd.label(key);
    if (!l || l === n) return null;
    return l.startsWith(`${n} · `) ? l.slice(n.length + 3) : l;
  };

  // Collapsible nav sections, purpose-ordered (2026-07-07 standardization):
  //   STRATEJİLER — the live strategy streams — default OPEN
  //   İŞLEM       — Binance boards (per-user activation) + İşlem Merkezi — default OPEN
  //   PİYASA      — market context (Rejim Haritası / TOTAL / İstihbarat) — default OPEN
  //   ARAŞTIRMA   — the backtest-only lab streams (opt-in) — default COLLAPSED
  // Collapse state persists like the other PUSU prefs (legacy localStorage keys kept).
  const [liveOpen, setLiveOpen] = useState(() => {
    try { return localStorage.getItem('pusu.navLive') !== '0'; } catch { return true; }
  });
  const [execOpen, setExecOpen] = useState(() => {
    try { return localStorage.getItem('pusu.navExec') !== '0'; } catch { return true; }
  });
  const [marketOpen, setMarketOpen] = useState(() => {
    try { return localStorage.getItem('pusu.navMarket') !== '0'; } catch { return true; }
  });
  const [btOpen, setBtOpen] = useState(() => {
    try { return localStorage.getItem('pusu.navBacktest') === '1'; } catch { return false; }
  });
  const toggleLive = () => setLiveOpen((o) => {
    const next = !o;
    try { localStorage.setItem('pusu.navLive', next ? '1' : '0'); } catch { /* ignore */ }
    return next;
  });
  const toggleExec = () => setExecOpen((o) => {
    const next = !o;
    try { localStorage.setItem('pusu.navExec', next ? '1' : '0'); } catch { /* ignore */ }
    return next;
  });
  const toggleBacktest = () => setBtOpen((o) => {
    const next = !o;
    try { localStorage.setItem('pusu.navBacktest', next ? '1' : '0'); } catch { /* ignore */ }
    return next;
  });
  const toggleMarket = () => setMarketOpen((o) => {
    const next = !o;
    try { localStorage.setItem('pusu.navMarket', next ? '1' : '0'); } catch { /* ignore */ }
    return next;
  });

  // Shared renderer for a strategy-stream group (icons / leafLabel / badges preserved).
  // Names come from useStreamDisplay: codename for everyone, real name (+ technical
  // sublabel) only for the admin. Leaf links navigate by codename SLUG, not raw key.
  const renderGroup = (g) => (
    <div key={g.key} className={`sidebar__group sidebar__group--${g.key}${g.live ? ' sidebar__group--live' : ''}${g.paper ? ' sidebar__group--paper' : ''}`}>
      <div className="sidebar__group-label">
        <span className="sidebar__icon">{g.icon}</span>
        {g.section === 'live'
          ? <><b className="sidebar__group-name">{sd.name(g.key)}</b>{techLabel(g.key)}</>
          : <span>{sd.isAdmin ? sd.label(g.key) : sd.name(g.key)}</span>}
        {g.live && (g.real
          ? <span className="sidebar__live-badge sidebar__live-badge--binance">● {t('Binance · GERÇEK')}</span>
          : <span className={`sidebar__live-badge${g.paper ? ' sidebar__live-badge--paper' : ''}`}>● {g.paper ? t('PAPER') : t('CANLI')}</span>)}
      </div>
      {g.modes.map((m) => (
        <NavLink key={m} to={`/${slugFor(g.key)}/${m}`} end className="sidebar__link sidebar__leaf">
          <span className={`sidebar__leaf-dot sidebar__leaf-dot--${m}`} />
          <span>{leafLabel[m]}</span>
        </NavLink>
      ))}
    </div>
  );

  return (
    <aside className="sidebar">
      <div className="sidebar__brand">
        <PusuLogo size={38} animated />
        <div className="sidebar__brand-text">
          <div className="sidebar__name">PUSU</div>
        </div>
      </div>

      {/* Tapping any destination closes the phone drawer; the strategies-section
          toggle stops propagation so expanding it keeps the drawer open. */}
      <nav className="sidebar__nav" onClick={closeMobileNav}>
        <NavLink to="/" end className="sidebar__link sidebar__home">
          <span className="sidebar__icon"><IconHome /></span><span>{t('Genel Bakış')}</span>
        </NavLink>

        {/* ── STRATEJİLER — ONLY the live strategy streams ── */}
        <button
          className="sidebar__section"
          onClick={(e) => { e.stopPropagation(); toggleLive(); }}
          aria-expanded={liveOpen}
          title={liveOpen ? t('Gizle') : t('Göster')}
        >
          <span className="sidebar__icon"><IconImpulse /></span>
          <span className="sidebar__section-label">{t('STRATEJİLER')}</span>
          <span className="sidebar__section-chev" aria-hidden="true">{liveOpen ? '▾' : '▸'}</span>
        </button>

        {liveOpen && (
          <div className="sidebar__strategies">
            {GROUPS.filter((g) => g.section === 'live').map(renderGroup)}
          </div>
        )}

        {/* ── İŞLEM — Binance position boards (per-user activation) + trading controls ── */}
        <button
          className="sidebar__section"
          onClick={(e) => { e.stopPropagation(); toggleExec(); }}
          aria-expanded={execOpen}
          title={execOpen ? t('Gizle') : t('Göster')}
        >
          <span className="sidebar__icon"><IconLive /></span>
          <span className="sidebar__section-label">{t('İŞLEM')}</span>
          <span className="sidebar__section-chev" aria-hidden="true">{execOpen ? '▾' : '▸'}</span>
        </button>

        {execOpen && (
          <div className="sidebar__strategies">
            {/* Pano linkleri KİŞİSEL aktivasyona bağlı (2026-07-07): bir ağın linki ancak
                kullanıcı o ağda geçerli anahtar + aktif akış/sembol kurduysa görünür —
                "diğer türlü boş olsun". İşlem Merkezi her zaman durur (aktivasyon orada yapılır). */}
            {act.mainnet && (
              <NavLink to="/binance" className="sidebar__link sidebar__link--binance">
                <span className="sidebar__icon"><IconLive /></span><span>{t('Binance Canlı')}</span>
                <span className="sidebar__live-badge sidebar__live-badge--binance">● {t('GERÇEK')}</span>
              </NavLink>
            )}
            {act.testnet && (
              <NavLink to="/binance-paper" className="sidebar__link sidebar__link--binance-paper">
                <span className="sidebar__icon"><IconLive /></span><span>Binance Paper</span>
                <span className="sidebar__live-badge sidebar__live-badge--paper">● {t('PAPER')}</span>
              </NavLink>
            )}

            {/* 2026-07-07: ayrı "Binance · Altın" linki kaldırıldı (kullanıcı: "Binance Mainnet'te
                de olur zaten") — altın pozisyonları artık pano sayfasının Altın bölümünde;
                /binance-altin detay sayfası oradaki "Detay →" linkiyle erişilir. */}

            {/* İşlem Merkezi — per-user keys/risk/activation (active accounts only;
                admin user_features.trading ile kullanıcı-başına kapatabilir) */}
            {isActive && features?.trading !== false && (
              <NavLink to="/trading" className="sidebar__link">
                <span className="sidebar__icon"><IconGear /></span><span>{t('İşlem Merkezi')}</span>
              </NavLink>
            )}
          </div>
        )}

        {/* ── PİYASA — market context views (regime map / marketcap breadth / intel) ── */}
        <button
          className="sidebar__section"
          onClick={(e) => { e.stopPropagation(); toggleMarket(); }}
          aria-expanded={marketOpen}
          title={marketOpen ? t('Gizle') : t('Göster')}
        >
          <span className="sidebar__icon"><IconRegime /></span>
          <span className="sidebar__section-label">{t('PİYASA')}</span>
          <span className="sidebar__section-chev" aria-hidden="true">{marketOpen ? '▾' : '▸'}</span>
        </button>

        {marketOpen && (
          <div className="sidebar__strategies">
            <NavLink to="/trend" className="sidebar__link">
              <span className="sidebar__icon"><IconRegime /></span><span>{t('Rejim Haritası')}</span>
            </NavLink>
            <NavLink to="/total" className="sidebar__link">
              <span className="sidebar__icon"><IconTotal /></span><span>TOTAL</span>
            </NavLink>
            {features?.intelligence !== false && (
              <NavLink to="/intelligence" className="sidebar__link">
                <span className="sidebar__icon"><IconIntel /></span><span>{t('İstihbarat')}</span>
              </NavLink>
            )}
          </div>
        )}

        {/* ── ARAŞTIRMA — backtest-only lab streams (leaf links go to /:key/backtest).
              OPT-IN: yalnız admin, ya da admin'in backtest yüzeyini açtığı kullanıcı görür
              (19 araştırma varyantı = laboratuvar, ürün değil). Canlı akışların kendi
              backtest sekmesi STRATEJİLER'de, bu bölümden bağımsız. ── */}
        {(isAdmin || features?.backtest === true) && (
          <>
            <button
              className="sidebar__section"
              onClick={(e) => { e.stopPropagation(); toggleBacktest(); }}
              aria-expanded={btOpen}
              title={btOpen ? t('Gizle') : t('Göster')}
            >
              <span className="sidebar__icon"><IconStrategies /></span>
              <span className="sidebar__section-label">{t('ARAŞTIRMA')}</span>
              <span className="sidebar__section-chev" aria-hidden="true">{btOpen ? '▾' : '▸'}</span>
            </button>

            {btOpen && (
              <div className="sidebar__strategies">
                {GROUPS.filter((g) => g.section === 'backtest').map(renderGroup)}
              </div>
            )}
          </>
        )}

        <div className="sidebar__navsep" />
        <NavLink to="/settings" className="sidebar__link">
          <span className="sidebar__icon"><IconSettings /></span><span>{t('Ayarlar')}</span>
        </NavLink>
        {/* Yönetim — admin console (sistem/hesap yönetimi → Ayarlar'ın yanında) */}
        {isAdmin && (
          <NavLink to="/admin" className="sidebar__link">
            <span className="sidebar__icon"><IconShield /></span><span>{t('Yönetim')}</span>
          </NavLink>
        )}
      </nav>

      <div className="sidebar__foot">
        <div className="sidebar__prefs">
          <div className="sidebar__ctl">
            <span className="sidebar__ctl-label">{t('Tema')}</span>
            <div className="seg seg--sm" role="group" aria-label="theme">
              <button className={theme === 'dark' ? 'active' : ''} onClick={() => setTheme('dark')} title={t('Koyu')}>☾</button>
              <button className={theme === 'light' ? 'active' : ''} onClick={() => setTheme('light')} title={t('Açık')}>☀</button>
            </div>
          </div>
          <div className="sidebar__ctl">
            <span className="sidebar__ctl-label">{t('Dil')}</span>
            <div className="seg seg--sm" role="group" aria-label="language">
              <button className={lang === 'tr' ? 'active' : ''} onClick={() => setLang('tr')}>TR</button>
              <button className={lang === 'en' ? 'active' : ''} onClick={() => setLang('en')}>EN</button>
            </div>
          </div>
        </div>

        <div className="sidebar__user">
          <span className="sidebar__avatar">{(user?.name || 'P').slice(0, 1).toUpperCase()}</span>
          <span className="sidebar__user-meta">
            <span className="sidebar__uname">{user?.name || 'pusu'}</span>
            <span className="sidebar__urole">{t('Operatör')}</span>
          </span>
          <button className="sidebar__logout" onClick={logout} title={t('Çıkış Yap')} aria-label={t('Çıkış Yap')}>⏻</button>
        </div>
      </div>
    </aside>
  );
};

export default Sidebar;
