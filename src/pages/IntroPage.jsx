import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLang } from '../context/LanguageContext';
import { infoFor } from '../utils/strategyInfo';
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

  const [stats, setStats] = useState(getCachedStats());
  const [loading, setLoading] = useState(!getCachedStats());
  const [failed, setFailed] = useState(false);

  const [cat, setCat] = useState('all');         // all | full | half | adaptive | session
  const [sort, setSort] = useState('r');          // r | win | exp | pf
  const [query, setQuery] = useState('');
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
    return Math.max(1, ...STREAMS.map((s) => Math.abs(Number(stats[s.version]?.total_r) || 0)));
  }, [stats]);

  const leaders = useMemo(() => {
    if (!stats) return null;
    const withStats = STREAMS.map((s) => ({ s, m: stats[s.version] })).filter((x) => x.m);
    if (!withStats.length) return null;
    const pick = (sel) => withStats.reduce((a, b) => (sel(b.m) > sel(a.m) ? b : a));
    const totalSignals = withStats.reduce((sum, x) => sum + (Number(x.m.total_trades) || 0), 0);
    return {
      topR: pick((m) => Number(m.total_r) || 0),
      topExp: pick((m) => Number(m.avg_r) || 0),
      topWin: pick((m) => Number(m.win_rate) || 0),
      totalSignals,
    };
  }, [stats]);

  const matchCat = (s) =>
    cat === 'all' ||
    (cat === 'chop' && s.chop) ||
    (cat === 'full' && s.exit === 'full') ||
    (cat === 'half' && s.exit === 'half') ||
    (cat === 'adaptive' && s.family === 'adaptive') ||
    (cat === 'session' && s.family === 'session');

  const metricOf = (s) => {
    const m = statOf(s);
    if (!m) return -Infinity;
    if (sort === 'win') return Number(m.win_rate) || 0;
    if (sort === 'exp') return Number(m.avg_r) || 0;
    if (sort === 'pf') return Number(m.profit_factor) || 0;
    return Number(m.total_r) || 0;
  };

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    return STREAMS
      .filter(matchCat)
      .filter((s) => {
        if (!q) return true;
        const c = infoFor(s.key, lang);
        const blob = `${s.key} ${c?.title || ''} ${c?.tagline || ''} ${c?.summary || ''}`.toLowerCase();
        return blob.includes(q);
      })
      .sort((a, b) => metricOf(b) - metricOf(a));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cat, sort, query, stats, lang]);

  const CATS = [
    { key: 'all', label: t('Tümü') },
    { key: 'full', label: t('Tam TP') },
    { key: 'half', label: '½TP' },
    { key: 'adaptive', label: t('Adaptif') },
    { key: 'session', label: t('Seans') },
    { key: 'chop', label: 'Chop' },
  ];
  const SORTS = [
    { key: 'r', label: t('Toplam R') },
    { key: 'win', label: t('İsabet') },
    { key: 'exp', label: t('Beklenti') },
    { key: 'pf', label: 'PF' },
  ];
  const FAMILY_LABEL = { core: t('ICT Çekirdek'), adaptive: t('Adaptif'), session: t('Seans') };
  const EXIT_LABEL = { full: t('Tam TP'), half: '½TP', mixed: t('Sembol-bazlı çıkış') };

  const LeaderTile = ({ label, entry, fmt }) => {
    if (!entry) return null;
    const info = infoFor(entry.s.key, lang);
    if (!info) return null;
    return (
      <button className="intro-leader" onClick={() => navigate(`/${entry.s.key}/backtest`)} style={{ '--acc': info.accent }}>
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
            <div className="intro-sub">Liquidity Ambush Intelligence</div>
            <p className="intro-manifesto">{t('{n} işlem akımı, tek bir likidite avı felsefesi — kurumsal süpürmeleri yakala, disiplinli çıkışla yönet.', { n: STREAMS.length })}</p>

            <div className="intro-leaders">
              <div className="intro-overview-tile">
                <span className="intro-leader__label">{t('Akım')}</span>
                <span className="intro-leader__value">{STREAMS.length}</span>
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

        {/* ---- Controls ---- */}
        <div className="intro-controls">
          <div className="intro-chips" role="group" aria-label="filter">
            {CATS.map((c) => (
              <button key={c.key} className={`intro-chip ${cat === c.key ? 'active' : ''}`} onClick={() => setCat(c.key)}>
                {c.label}
              </button>
            ))}
          </div>
          <div className="intro-controls__right">
            <div className="intro-sort" role="group" aria-label="sort">
              <span className="intro-sort__label">{t('Sırala')}</span>
              {SORTS.map((s) => (
                <button key={s.key} className={`intro-sort__btn ${sort === s.key ? 'active' : ''}`} onClick={() => setSort(s.key)}>
                  {s.label}
                </button>
              ))}
            </div>
            <input
              className="intro-search" type="text" placeholder={t('Akım ara...')}
              value={query} onChange={(e) => setQuery(e.target.value)}
            />
          </div>
        </div>

        {failed && <div className="intro-note">⚠ {t('Sonuç verisi alınamadı — akım açıklamaları yine de aşağıda.')}</div>}

        {/* ---- Stream cards ---- */}
        <div className="intro-cards">
          {visible.length === 0 && <div className="intro-empty">{t('Sonuç yok')}</div>}
          {visible.map((s) => {
            const info = infoFor(s.key, lang);
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

                <div className="intro-card__chips">
                  <span className="intro-tag">{FAMILY_LABEL[s.family]}</span>
                  <span className="intro-tag intro-tag--exit">{EXIT_LABEL[s.exit]}</span>
                </div>

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

                {/* What it does */}
                <p className="intro-card__summary">{head.summary}</p>

                {open && (
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
                  <button className="intro-go intro-go--live" onClick={() => navigate(`/${s.key}/live`)}>
                    <span className="intro-go__dot" /> {t('Live')}
                  </button>
                  <button className="intro-go" onClick={() => navigate(`/${s.key}/backtest`)}>
                    {t('Backtest')}
                  </button>
                  <button className="intro-go intro-go--ghost" onClick={() => setOpenKey(open ? null : s.key)}>
                    {open ? t('Gizle') : t('Detay')}
                  </button>
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
