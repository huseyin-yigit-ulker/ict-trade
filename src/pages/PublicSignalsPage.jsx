import { useState, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useTradeContext } from '../context/TradeContext';
import { useLang } from '../context/LanguageContext';
import { useTheme } from '../context/ThemeContext';
import {
  scaleOutLiveR,
  isScaleOutStrategy,
  soCapFromStrategy,
  isConfirmStrategy,
  soBookFromStrategy,
} from '../utils/liveR';
import PusuLogo from '../components/PusuLogo';
import ChartModal from '../components/ChartModal';
import './PublicSignalsPage.css';

// Public Strategy Definitions (Transparently showing real names & mechanisms)
const PUBLIC_STRATEGIES = [
  {
    key: 'd30so8f3h7',
    code: 'ATLAS',
    name: 'OPUS',
    market: 'Kripto Vadeli (Multi-Coin)',
    tf: '30m + 4h',
    badge: 'AKTİF MOTOR',
    desc: 'Donchian(55) kanal kırılımı + 4h Kaufman ER filtreli trend takibi. 8R kademeli kâr al (scale-out) ve breakeven koruması uygular.',
    tags: ['BTC/ETH/SOL', 'Trend-Breakout', 'Scale-Out 8R', '4h Gate'],
  },
  {
    key: 'talos_ichi',
    code: 'MENKAR',
    name: 'TALOS-ICHI',
    market: 'Altın (XAUUSDT)',
    tf: '1m Seans',
    badge: 'CANLI / PAPER',
    desc: 'Keltner kanalları ve Ichimoku Kumo bulutunu birleştiren momentum takip motoru. 1.5×ATR başlangıç stopu ve 3.5×ATR dinamik trailing uygular.',
    tags: ['XAUUSDT', 'Keltner', 'Ichimoku Kumo', 'Trailing Stop'],
  },
  {
    key: 'midas',
    code: 'SIRIUS',
    name: 'MIDAS',
    market: 'Altın (XAUUSDT)',
    tf: '1m Seans',
    badge: 'ARAŞTIRMA',
    desc: 'New York ve Londra seanslarında hacim ağırlıklı ortalama fiyat (VWAP) sapmalarını ve geri dönüş hareketlerini yakalayan model.',
    tags: ['XAUUSDT', 'Seans VWAP', 'Mean-Reversion', 'Trailing Stop'],
  },
  {
    key: 'talos',
    code: 'ANTARES',
    name: 'TALOS',
    market: 'Altın (XAUUSDT)',
    tf: '1m Seans',
    badge: 'ARAŞTIRMA',
    desc: 'Keltner kanalı bazlı klasik altın trend takip modeli. Oynaklık genişlemelerinde yönlü pozisyon açar.',
    tags: ['XAUUSDT', 'Keltner Breakout', 'Trailing Stop'],
  },
  {
    key: 'donchianc',
    code: 'VEGA',
    name: 'DONCHIAN 1h',
    market: 'Kripto Çoklu Varlık',
    tf: '1h',
    badge: 'KLASİK MODEL',
    desc: '1 saatlik barlarda Donchian 55 periyot kanal kırılımları. 0.5R teyit mekanizmasıyla sahte kırılımları filtreler.',
    tags: ['Kripto Portföy', '1h Breakout', '0.5R Teyit', 'Trend Takip'],
  },
];

const STATUS_FILTERS = [
  { key: 'all', label: 'Tümü' },
  { key: 'active', label: 'Aktif İşlemler' },
  { key: 'tp', label: 'TP Alındı' },
  { key: 'sl', label: 'SL Vuruldu' },
  { key: 'cancelled', label: 'İptal Edilenler' },
];

const intervalMs = (tf) => {
  const m = String(tf || '1h').match(/^(\d+)([smhd])$/i);
  if (!m) return 3_600_000;
  const u = { s: 1000, m: 60_000, h: 3_600_000, d: 86_400_000 };
  return Number(m[1]) * (u[m[2].toLowerCase()] || 0);
};

const effTimeOf = (sig) => new Date(sig.dateObj.getTime() + intervalMs(sig.ltfTimeframe));

const formatPrice = (value) => {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '—';
  const abs = Math.abs(value);
  if (abs === 0) return '0';
  if (abs >= 100) return value.toFixed(2);
  if (abs >= 1) return value.toFixed(4);
  if (abs >= 0.01) return value.toFixed(5);
  if (abs >= 0.0001) return value.toFixed(7);
  return value.toPrecision(4);
};

const timeAgo = (date) => {
  if (!(date instanceof Date)) return '—';
  const diffMs = Date.now() - date.getTime();
  if (diffMs < 0) return 'şimdi';
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return 'az önce';
  if (mins < 60) return `${mins} dk önce`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} sa ${mins % 60} dk`;
  const days = Math.floor(hrs / 24);
  return `${days} gün ${hrs % 24} sa`;
};

export default function PublicSignalsPage() {
  const {
    filteredSignals,
    liveStatuses,
    setActiveSignal,
    activeSignal,
    strategy,
    setView,
    isLoaded,
    liveError,
  } = useTradeContext();

  const { t, lang, setLang } = useLang();
  const { theme, toggleTheme } = useTheme();

  const [statusFilter, setStatusFilter] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');

  const currentStratDef = useMemo(
    () => PUBLIC_STRATEGIES.find((s) => s.key === strategy) || PUBLIC_STRATEGIES[0],
    [strategy],
  );

  const isTrailing = ['midas', 'talos', 'talos_ichi'].includes(strategy);
  const isSO = isScaleOutStrategy(strategy);
  const soCapR = soCapFromStrategy(strategy);
  const soConservative = isConfirmStrategy(strategy);
  const soBookFrac = soBookFromStrategy(strategy);

  const getStatusCategory = (sig) => {
    const s = liveStatuses[sig.id]?.status || '';
    if (s === 'TP Oldu' || s === 'BE Oldu') return 'tp';
    if (s === 'SL Oldu' || s === 'TP/SL Aynı Mum') return 'sl';
    if (s.startsWith('İptal')) return 'cancelled';
    if (s.startsWith('İşlem Aktif')) return 'active';
    return 'open';
  };

  const getStatusBadge = (sig) => {
    const s = liveStatuses[sig.id]?.status || '';
    if (s === 'TP Oldu') return { label: 'TP ALINDI', cls: 'st-tp' };
    if (s === 'BE Oldu') return { label: 'BE (BAŞABAŞ)', cls: 'st-tp' };
    if (s === 'SL Oldu') return { label: 'SL OLDU', cls: 'st-sl' };
    if (s === 'TP/SL Aynı Mum') return { label: 'TP+SL', cls: 'st-sl' };
    if (s.startsWith('İşlem Aktif')) return { label: 'İŞLEM AKTİF', cls: 'st-active' };
    if (s.startsWith('İptal')) return { label: 'İPTAL', cls: 'st-cancel' };
    return { label: 'BEKLİYOR', cls: 'st-wait' };
  };

  const calculateSignalR = (sig, cat) => {
    if (isTrailing) return Number.isFinite(sig.pnlR) ? sig.pnlR : null;
    if (!isSO) return null;
    const r = scaleOutLiveR(sig.entry, sig.sl, liveStatuses[sig.id]?.status, soCapR, soConservative, soBookFrac);
    return r != null ? r : (cat === 'sl' ? -1 : null);
  };

  // KPIs across current filtered signals
  const stats = useMemo(() => {
    let tp = 0;
    let sl = 0;
    let active = 0;
    let cancelled = 0;
    let totalR = 0;
    let rCount = 0;

    for (const sig of filteredSignals) {
      const cat = getStatusCategory(sig);
      if (cat === 'tp') tp += 1;
      else if (cat === 'sl') sl += 1;
      else if (cat === 'active') active += 1;
      else if (cat === 'cancelled') cancelled += 1;

      if (cat === 'tp' || cat === 'sl') {
        const r = calculateSignalR(sig, cat);
        if (r != null) {
          totalR += r;
          rCount += 1;
        }
      }
    }

    const closed = tp + sl;
    const wr = closed > 0 ? Math.round((tp / closed) * 100) : null;

    return {
      total: filteredSignals.length,
      active,
      tp,
      sl,
      cancelled,
      wr,
      totalR,
      hasR: rCount > 0,
    };
  }, [filteredSignals, liveStatuses, isTrailing, isSO, soCapR, soConservative, soBookFrac]);

  // Filter signals by status & search term
  const displayedSignals = useMemo(() => {
    return filteredSignals.filter((sig) => {
      const cat = getStatusCategory(sig);
      if (statusFilter !== 'all' && cat !== statusFilter) return false;
      if (searchTerm) {
        const s = searchTerm.toUpperCase().trim();
        if (!sig.symbol.toUpperCase().includes(s)) return false;
      }
      return true;
    });
  }, [filteredSignals, statusFilter, searchTerm, liveStatuses]);

  // Group signals by day
  const groupedSignals = useMemo(() => {
    const groups = [];
    const map = new Map();
    const today = new Date().toDateString();
    const yesterday = new Date(Date.now() - 86_400_000).toDateString();

    for (const sig of displayedSignals) {
      const eff = effTimeOf(sig);
      const ds = eff.toDateString();
      let label = ds === today ? 'Bugün' : ds === yesterday ? 'Dün' : eff.toLocaleDateString('tr-TR', { day: 'numeric', month: 'long', weekday: 'short' });
      if (!map.has(label)) {
        const groupObj = { label, items: [] };
        map.set(label, groupObj);
        groups.push(groupObj);
      }
      map.get(label).items.push({ sig, eff });
    }
    return groups;
  }, [displayedSignals]);

  const handleStrategyChange = (key) => {
    setView(key, 'live');
  };

  return (
    <div className="pub-page">
      {/* Top Navigation */}
      <header className="pub-header">
        <div className="pub-header__left">
          <Link to="/" className="pub-logo-link">
            <PusuLogo size={28} />
            <span className="pub-logo-title">PUSU</span>
          </Link>
          <div className="pub-badge-live">
            <span className="pub-badge-dot" />
            <span>CANLI SİNYAL AKIŞI</span>
          </div>
        </div>

        <div className="pub-header__right">
          <button
            type="button"
            className="pub-icon-btn"
            onClick={toggleTheme}
            title={theme === 'dark' ? 'Açık Tema' : 'Koyu Tema'}
          >
            {theme === 'dark' ? '☀️' : '🌙'}
          </button>

          <button
            type="button"
            className="pub-icon-btn"
            onClick={() => setLang(lang === 'tr' ? 'en' : 'tr')}
            title="Dili Değiştir"
          >
            {lang === 'tr' ? 'EN' : 'TR'}
          </button>

          <a
            href="https://github.com/huseyin-yigit-ulker/ict-trade"
            target="_blank"
            rel="noreferrer"
            className="pub-icon-btn"
            title="GitHub Repository"
          >
            GitHub
          </a>

          <Link to="/login" className="pub-icon-btn pub-login-btn">
            Yönetici Girişi
          </Link>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="pub-content">
        {/* Hero Section */}
        <div className="pub-hero">
          <div className="pub-hero__top">
            <div>
              <h1 className="pub-hero__title">
                Şeffaf Algoritmik İşlem ve Sinyal Paneli
              </h1>
              <p className="pub-hero__subtitle">
                Bu repo artık tamamen kamuya açıktır. Canlı piyasalardaki sinyalleri, uygulanan algoritmik
                stratejilerin anlık durumunu (Giriş, Kâr Al, Zarar Durdur seviyeleri) ve performans sonuçlarını
                giriş yapmaya gerek olmadan doğrudan buradan takip edebilirsiniz.
              </p>
            </div>
            <div className="pub-hero__meta">
              <span>● Otomatik Canlı Fiyat Taraması</span>
            </div>
          </div>

          {/* Strategy Selector Pills */}
          <div className="pub-strat-bar">
            {PUBLIC_STRATEGIES.map((st) => {
              const active = st.key === strategy;
              return (
                <button
                  key={st.key}
                  type="button"
                  className={`pub-strat-pill ${active ? 'active' : ''}`}
                  onClick={() => handleStrategyChange(st.key)}
                >
                  <span>{st.name}</span>
                  <span className="pub-strat-pill__badge">{st.code}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Selected Strategy Details */}
        <div className="pub-strat-desc">
          <div className="pub-strat-desc__header">
            <div className="pub-strat-desc__title">
              <span>{currentStratDef.name} ({currentStratDef.code})</span>
              <span className="pub-tag" style={{ color: 'var(--accent)', borderColor: 'var(--accent)' }}>
                {currentStratDef.badge}
              </span>
            </div>
            <div className="pub-strat-desc__tags">
              <span className="pub-tag">{currentStratDef.market}</span>
              <span className="pub-tag">{currentStratDef.tf}</span>
              {currentStratDef.tags.map((tag) => (
                <span key={tag} className="pub-tag">{tag}</span>
              ))}
            </div>
          </div>
          <div className="pub-strat-desc__text">
            {currentStratDef.desc}
          </div>
        </div>

        {/* KPI Metrics */}
        <div className="pub-kpi-grid">
          <div className="pub-kpi-card">
            <span className="pub-kpi-card__label">Kazanma Oranı</span>
            <span className={`pub-kpi-card__val ${stats.wr != null && stats.wr >= 50 ? 'pos' : 'neg'}`}>
              {stats.wr != null ? `%${stats.wr}` : '—'}
            </span>
            <span className="pub-kpi-card__sub">{stats.tp} TP / {stats.sl} SL (Kapanan)</span>
          </div>

          <div className="pub-kpi-card">
            <span className="pub-kpi-card__label">Net R Getiri</span>
            <span className={`pub-kpi-card__val ${stats.totalR >= 0 ? 'pos' : 'neg'}`}>
              {stats.hasR ? `${stats.totalR >= 0 ? '+' : ''}${stats.totalR.toFixed(1)}R` : '—'}
            </span>
            <span className="pub-kpi-card__sub">Risk Çarpanı PnL</span>
          </div>

          <div className="pub-kpi-card">
            <span className="pub-kpi-card__label">Aktif Pozisyonlar</span>
            <span className="pub-kpi-card__val pos">{stats.active}</span>
            <span className="pub-kpi-card__sub">Şu an piyasada açık</span>
          </div>

          <div className="pub-kpi-card">
            <span className="pub-kpi-card__label">Toplam Sinyal</span>
            <span className="pub-kpi-card__val">{stats.total}</span>
            <span className="pub-kpi-card__sub">Son 48 saat akışı</span>
          </div>
        </div>

        {/* Filters and Search */}
        <div className="pub-filter-bar">
          <div className="pub-filter-chips">
            {STATUS_FILTERS.map((f) => (
              <button
                key={f.key}
                type="button"
                className={`pub-filter-chip ${statusFilter === f.key ? 'active' : ''}`}
                onClick={() => setStatusFilter(f.key)}
              >
                {f.label}
              </button>
            ))}
          </div>

          <div className="pub-search-box">
            <span>🔍</span>
            <input
              type="text"
              placeholder="Sembol ara (örn: BTC, SOL, XAU)..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
            {searchTerm && (
              <button
                type="button"
                style={{ background: 'none', border: 'none', color: 'var(--muted)', cursor: 'pointer' }}
                onClick={() => setSearchTerm('')}
              >
                ✕
              </button>
            )}
          </div>
        </div>

        {/* Live Errors / Info */}
        {liveError && (
          <div style={{ padding: '12px 16px', background: 'var(--loss-soft)', color: 'var(--loss)', borderRadius: '8px', fontSize: '13px' }}>
            ⚠️ {liveError}
          </div>
        )}

        {/* Signals List / Groups */}
        <div className="pub-signals-container">
          {!isLoaded ? (
            <div className="pub-empty">
              <span className="pub-empty__title">Sinyaller Yükleniyor...</span>
              <span>Canlı veritabanı ve piyasa barları taranıyor.</span>
            </div>
          ) : displayedSignals.length === 0 ? (
            <div className="pub-empty">
              <span className="pub-empty__title">Sinyal Bulunamadı</span>
              <span>Seçilen filtre ve sembol kriterlerine uygun aktif bir sinyal yok.</span>
            </div>
          ) : (
            groupedSignals.map((group) => (
              <div key={group.label} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                <div className="pub-group-title">{group.label}</div>
                <div className="pub-signals-grid">
                  {group.items.map(({ sig, eff }) => {
                    const isLong = sig.direction === 'LONG' || sig.dir === 'LONG';
                    const badge = getStatusBadge(sig);
                    const cat = getStatusCategory(sig);
                    const live = liveStatuses[sig.id];
                    const r = calculateSignalR(sig, cat);

                    return (
                      <div
                        key={sig.id}
                        className={`pub-sigcard ${isLong ? 'pub-sigcard--long' : 'pub-sigcard--short'}`}
                        onClick={() => setActiveSignal(sig)}
                        role="button"
                        tabIndex={0}
                        title="İnteraktif grafiği açmak için tıklayın"
                      >
                        <div className="pub-sigcard__header">
                          <div className="pub-sigcard__sym-box">
                            <span className="pub-sigcard__sym">{sig.symbol}</span>
                            <span className={`pub-sigcard__dir ${isLong ? 'pub-sigcard__dir--long' : 'pub-sigcard__dir--short'}`}>
                              {isLong ? 'LONG' : 'SHORT'}
                            </span>
                          </div>
                          <span className={`pub-sigcard__st-badge ${badge.cls}`}>
                            ● {badge.label}
                          </span>
                        </div>

                        <div className="pub-sigcard__prices">
                          <div className="pub-sigcard__price-cell">
                            <span className="pub-sigcard__price-label">Giriş</span>
                            <span className="pub-sigcard__price-val">{formatPrice(sig.entry)}</span>
                          </div>
                          <div className="pub-sigcard__price-cell">
                            <span className="pub-sigcard__price-label">TP</span>
                            <span className="pub-sigcard__price-val pos">
                              {isTrailing ? 'Trailing' : formatPrice(sig.tp)}
                            </span>
                          </div>
                          <div className="pub-sigcard__price-cell">
                            <span className="pub-sigcard__price-label">SL</span>
                            <span className="pub-sigcard__price-val neg">{formatPrice(sig.sl)}</span>
                          </div>
                        </div>

                        {live?.lastPrice != null && (
                          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--muted)' }}>
                            <span>Anlık Fiyat: <b className="mono" style={{ color: 'var(--text)' }}>{formatPrice(live.lastPrice)}</b></span>
                            {r != null && (
                              <span className={`pub-sigcard__r-tag ${r >= 0 ? 'pos' : 'neg'}`}>
                                {r >= 0 ? '+' : ''}{r.toFixed(2)}R
                              </span>
                            )}
                          </div>
                        )}

                        <div className="pub-sigcard__footer">
                          <span>{timeAgo(eff)}</span>
                          <span style={{ fontSize: '11px', color: 'var(--accent)' }}>Grafiği İncele →</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            ))
          )}
        </div>

        {/* Public Research & Risk Disclaimer */}
        <div className="pub-disclaimer">
          <div className="pub-disclaimer__title">
            ⚠️ Şeffaflık ve Risk Bildirimi
          </div>
          <div className="pub-disclaimer__text">
            Bu platform, geliştirilmiş olan algoritmik stratejilerin (Donchian Kırılımları, Keltner Kanalları, VWAP Mean Reversion vb.)
            canlı piyasadaki sinyal davranışlarını ve gerçek zamanlı sonuçlarını şeffaf bir şekilde sergilemek üzere kamuya açılmıştır.
            Tüm analizler ve çıktılar sadece araştırma, backtest ve açık kaynak geliştirme amaçlıdır. Finansal tavsiye niteliği taşımaz.
            Kaldıraçlı ve vadeli piyasalar yüksek risk içerir.
          </div>
        </div>

        {/* Footer */}
        <footer className="pub-footer">
          <div>PUSU Algorithmic Trading Intelligence — Open Source Research</div>
          <div>
            Kaynak Kod: <a href="https://github.com/huseyin-yigit-ulker/ict-trade" target="_blank" rel="noreferrer">GitHub (Public)</a>
          </div>
        </footer>
      </main>

      {/* Candlestick Interactive Chart Modal */}
      {activeSignal && <ChartModal />}
    </div>
  );
}
