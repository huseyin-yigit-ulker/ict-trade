import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLang } from '../context/LanguageContext';
import { useAuth } from '../context/AuthContext';
import { useStreamDisplay } from '../utils/useStreamDisplay';
import { slugFor, isResearchStream } from '../utils/streamMask';
import { STREAMS, fetchAllSummaries, getCachedStats, fmtR, fmtExp, fmtPct, fmtPf } from '../utils/streamStats';
import PusuLogo from '../components/PusuLogo';

// Intro / hub screen ("giriş ekranı"): every strategy stream on one PUSU-styled
// surface — what each does (from strategyInfo) + its REAL 2026 backtest result
// (live-pulled from the same backtest_summary_metrics RPC the dashboard uses).
// Cards deep-link into each stream's working Live / Backtest dashboard, where the
// full symbol / status / date filters live. The hub itself filters + sorts streams.

const IntroPage = () => {
  const { lang, t } = useLang();
  const navigate = useNavigate();
  const sd = useStreamDisplay();
  const { isAdmin, features } = useAuth();

  // Ürün sınırı: araştırma varyantları opt-in — yetkisiz kullanıcı (admin değil ve
  // backtest yüzeyi kapalı) yalnız 2 CANLI akımı görür (OPUS + MIDAS; NOVA 2026-07-07'de
  // araştırmaya indi). Hub'daki tüm sayaç/sıralama/kartlar bu havuzdan türer.
  const pool = useMemo(
    () => STREAMS.filter((s) => isAdmin || features?.backtest === true || !isResearchStream(s.key)),
    [isAdmin, features],
  );

  // Anonymized-by-default head: codename + generic tagline; the admin's lazy
  // adminStreamInfo overlay swaps in the real title/tagline/summary/sections.
  const headFor = (key) => {
    const info = sd.info(key, lang);
    if (info) return info;
    return {
      title: sd.name(key),
      tagline: t('Otonom işlem akışı · detaylar gizli'),
      summary: '',
      sections: null,
      caveat: null,
      icon: '◆',
      accent: '#F0B90B',
    };
  };

  const [stats, setStats] = useState(getCachedStats());
  const [loading, setLoading] = useState(!getCachedStats());
  const [failed, setFailed] = useState(false);

  const [openKey, setOpenKey] = useState(null);   // which card's detail is expanded

  useEffect(() => {
    if (getCachedStats()) return;
    let alive = true;
    fetchAllSummaries()
      .then((data) => { if (alive) setStats(data); })
      .catch(() => { if (alive) setFailed(true); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, []);

  const statOf = (s) => (stats ? stats[s.version] : null);

  // Stable comparison scale: largest |R| across ALL streams (not the filter), so
  // the per-card R bars stay comparable as you change the category/sort.
  const maxAbsR = useMemo(() => {
    if (!stats) return 1;
    return Math.max(1, ...pool.map((s) => Math.abs(Number(stats[s.version]?.total_r) || 0)));
  }, [stats, pool]);

  const leaders = useMemo(() => {
    if (!stats) return null;
    const withStats = pool.map((s) => ({ s, m: stats[s.version] })).filter((x) => x.m);
    if (!withStats.length) return null;
    const pick = (sel) => withStats.reduce((a, b) => (sel(b.m) > sel(a.m) ? b : a));
    const totalSignals = withStats.reduce((sum, x) => sum + (Number(x.m.total_trades) || 0), 0);
    return {
      topR: pick((m) => Number(m.total_r) || 0),
      topExp: pick((m) => Number(m.avg_r) || 0),
      topWin: pick((m) => Number(m.win_rate) || 0),
      totalSignals,
    };
  }, [stats, pool]);

  // 2026-07-09: filtre (Tümü/Range/Seans) + sıralama (SIRALA) + arama kontrolleri
  // kaldırıldı — kartlar sabit Toplam R (azalan) sırasında listelenir.
  const rOf = (s) => { const m = statOf(s); const r = m ? Number(m.total_r) : NaN; return Number.isFinite(r) ? r : -Infinity; };
  const visible = useMemo(() => pool.slice().sort((a, b) => rOf(b) - rOf(a)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [stats, pool]);

  const FAMILY_LABEL = { core: t('ICT Çekirdek'), adaptive: t('Adaptif'), session: t('Seans'), range: 'Range', trend: 'Trend' };
  const EXIT_LABEL = { full: t('Tam TP'), half: '½TP', mixed: t('Sembol-bazlı çıkış'), scaleout: 'Scale-out' };

  const LeaderTile = ({ label, entry, fmt }) => {
    if (!entry) return null;
    const info = headFor(entry.s.key);
    return (
      <button className="intro-leader" onClick={() => navigate(`/${slugFor(entry.s.key)}/backtest`)} style={{ '--acc': info.accent }}>
        <span className="intro-leader__label">{label}</span>
        <span className="intro-leader__value win">{fmt(entry.m)}</span>
        <span className="intro-leader__who"><span aria-hidden="true">{info.icon}</span> {info.title}</span>
      </button>
    );
  };

  return (
    <div className="intro-wrap">
      <div className="intro-inner">
        {/* ---- Hero (full-screen splash) ---- */}
        <header className="intro-hero">
          <div className="intro-ambient" aria-hidden="true">
            <div className="intro-glow" />
            <div className="intro-grid-bg" />
            <div className="intro-radar" />
          </div>
          <div className="intro-hero__content">
            <div className="intro-reticle"><PusuLogo size={72} animated /></div>
            <h1 className="intro-title">PUSU</h1>

            <div className="intro-leaders">
              <div className="intro-overview-tile">
                <span className="intro-leader__label">{t('Akım')}</span>
                <span className="intro-leader__value">{pool.length}</span>
                <span className="intro-leader__who">
                  {leaders ? `${leaders.totalSignals.toLocaleString(lang === 'en' ? 'en-US' : 'tr-TR')} ${t('sinyal')}` : '—'}
                </span>
              </div>
              {leaders && (
                <>
                  <LeaderTile label={t('En Yüksek R')} entry={leaders.topR} fmt={(m) => fmtR(Number(m.total_r))} />
                  <LeaderTile label={t('En İyi Beklenti')} entry={leaders.topExp} fmt={(m) => fmtExp(Number(m.avg_r))} />
                  <LeaderTile label={t('En Yüksek İsabet')} entry={leaders.topWin} fmt={(m) => fmtPct(Number(m.win_rate))} />
                </>
              )}
            </div>
            <div className="intro-disclaimer">{t('Tüm sayılar 2026 backtest — örneklem içi. Forward beklenti daha düşüktür.')}</div>
            <div className="intro-scrollcue" aria-hidden="true">⌄</div>
          </div>
        </header>

        {failed && <div className="intro-note">⚠ {t('Sonuç verisi alınamadı — akım açıklamaları yine de aşağıda.')}</div>}

        {/* ---- Stream cards ---- */}
        <div className="intro-cards">
          {visible.length === 0 && <div className="intro-empty">{t('Sonuç yok')}</div>}
          {visible.map((s) => {
            const info = headFor(s.key);
            const head = info;
            const m = statOf(s);
            const open = openKey === s.key;
            const totalR = m ? Number(m.total_r) : null;
            const barPct = m ? Math.min(100, (Math.abs(totalR) / maxAbsR) * 100) : 0;
            const pos = (totalR ?? 0) >= 0;
            return (
              <article key={s.key} className={`intro-card ${open ? 'is-open' : ''}`} style={{ '--acc': info.accent }}>
                <button className="intro-card__head" onClick={() => setOpenKey(open ? null : s.key)} aria-expanded={open}>
                  <span className="intro-card__icon" aria-hidden="true">{info.icon}</span>
                  <span className="intro-card__heads">
                    <span className="intro-card__name">{head.title}</span>
                    <span className="intro-card__tag">{head.tagline}</span>
                  </span>
                  <span className="intro-card__chev" aria-hidden="true">{open ? '▾' : '▸'}</span>
                </button>

                {sd.isAdmin && (
                  <div className="intro-card__chips">
                    <span className="intro-tag">{FAMILY_LABEL[s.family]}</span>
                    <span className="intro-tag intro-tag--exit">{EXIT_LABEL[s.exit]}</span>
                  </div>
                )}

                {/* Headline result */}
                {loading ? (
                  <div className="intro-stat-skel" aria-hidden="true" />
                ) : m ? (
                  <>
                    <div className="intro-stats">
                      <div className="intro-stat intro-stat--lead">
                        <span className="intro-stat__label">{t('Toplam R')}</span>
                        <span className={`intro-stat__val ${pos ? 'win' : 'loss'}`}>{fmtR(totalR)}</span>
                      </div>
                      <div className="intro-stat">
                        <span className="intro-stat__label">{t('İsabet')}</span>
                        <span className="intro-stat__val">{fmtPct(Number(m.win_rate))}</span>
                      </div>
                      <div className="intro-stat">
                        <span className="intro-stat__label">{t('Beklenti')}</span>
                        <span className={`intro-stat__val ${Number(m.avg_r) >= 0 ? 'win' : 'loss'}`}>{fmtExp(Number(m.avg_r))}</span>
                      </div>
                      <div className="intro-stat">
                        <span className="intro-stat__label">PF</span>
                        <span className="intro-stat__val">{fmtPf(m.profit_factor)}</span>
                      </div>
                    </div>
                    <div className="intro-rbar" title={`${fmtR(totalR)}`}>
                      <span className={`intro-rbar__fill ${pos ? 'win' : 'loss'}`} style={{ width: `${barPct}%` }} />
                    </div>
                    <div className="intro-stat-sub">
                      {Number(m.closed_trades).toLocaleString(lang === 'en' ? 'en-US' : 'tr-TR')} {t('kapanan')}
                      <span className="intro-dot">·</span>
                      {Number(m.total_trades).toLocaleString(lang === 'en' ? 'en-US' : 'tr-TR')} {t('sinyal')}
                    </div>
                  </>
                ) : (
                  <div className="intro-stat-sub">{t('Sonuç verisi yok')}</div>
                )}

                {/* What it does — admin only; outsiders get no mechanics */}
                {head.summary && <p className="intro-card__summary">{head.summary}</p>}

                {open && sd.isAdmin && (
                  <div className="intro-card__detail">
                    {Array.isArray(head.sections) && head.sections.map((sec, i) => (
                      <div key={i} className="intro-sec">
                        <div className="intro-sec__h">{sec.h}</div>
                        <div className="intro-sec__t">{sec.t}</div>
                      </div>
                    ))}
                    {head.caveat && <div className="intro-caveat">⚠ {head.caveat}</div>}
                  </div>
                )}

                <div className="intro-card__foot">
                  {/* Araştırma varyantları backtest-only (sidebar'la tutarlı) — Live yalnız canlı akışlarda. */}
                  {!isResearchStream(s.key) && (
                    <button className="intro-go intro-go--live" onClick={() => navigate(`/${slugFor(s.key)}/live`)}>
                      <span className="intro-go__dot" /> {t('Live')}
                    </button>
                  )}
                  <button className="intro-go" onClick={() => navigate(`/${slugFor(s.key)}/backtest`)}>
                    {t('Backtest')}
                  </button>
                  {sd.isAdmin && (
                    <button className="intro-go intro-go--ghost" onClick={() => setOpenKey(open ? null : s.key)}>
                      {open ? t('Gizle') : t('Detay')}
                    </button>
                  )}
                </div>
              </article>
            );
          })}
        </div>

        <div className="intro-foot">© 2026 PUSU · {t('Likidite Avı')}</div>
      </div>
    </div>
  );
};

export default IntroPage;
