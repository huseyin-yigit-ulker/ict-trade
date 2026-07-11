import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useLang } from '../../context/LanguageContext';
import { useLiveExec, fmtUsd, fmtUsdSigned, ago } from '../../utils/useLiveExec';
import PositionCard, { ClosedCard } from '../../components/user/PositionCard';
import OnboardingCard from '../../components/user/OnboardingCard';
import LivePositionModal from '../../components/trading/LivePositionModal';

// Portföy — kullanıcı modunun ana sayfası. Binance app ana ekranı gibi:
// büyük bakiye + göz-gizle, açık K/Z, açık pozisyon kartları, son işlem teaser'ı.
// Veri RLS ile kullanıcıya kilitli; iki ağ (mainnet+paper) tek görünümde.

const HIDE_KEY = 'pusu.hideBalance';

const EyeIcon = ({ off }) => (
  <svg viewBox="0 0 20 20" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
    <path d="M2.5 10s2.8-4.5 7.5-4.5S17.5 10 17.5 10 14.7 14.5 10 14.5 2.5 10 2.5 10Z" />
    <circle cx="10" cy="10" r="2.2" />
    {off && <line x1="4" y1="16" x2="16" y2="4" />}
  </svg>
);

export default function PortfolioPage() {
  const { t } = useLang();
  const {
    loading, open, closed, snapFor, calcFor, accounts,
    totalWallet, totalUpnl, updatedAt, refresh,
  } = useLiveExec();
  const [hide, setHide] = useState(() => {
    try { return localStorage.getItem(HIDE_KEY) === '1'; } catch { return false; }
  });
  const [sel, setSel] = useState(null);
  const toggleHide = () => setHide((h) => {
    try { localStorage.setItem(HIDE_KEY, h ? '0' : '1'); } catch { /* ignore */ }
    return !h;
  });

  const mask = (v) => (hide ? '******' : v);
  const upnlUp = Number(totalUpnl) >= 0;
  const teaser = closed.slice(0, 3);
  // Yalnız gerçekten dolmuş satırlar tıklanır (iptallerde dolum/kart yok) — admin pano kuralı.
  const tapOpen = (p) => (p.isGold ? p.state === 'OPEN' && p.entry_fill_time : true);
  const tapClosed = (p) => p.state === 'CLOSED' && p.entry_fill_time;

  return (
    <div className="ush-portfolio">
      {/* Bakiye kartı */}
      <section className="ush-card ush-balance">
        <div className="ush-balance__label">
          <span>{t('Toplam Bakiye')}</span>
          <button type="button" className="ush-eye" onClick={toggleHide}
                  aria-label={t('Bakiyeyi gizle/göster')}>
            <EyeIcon off={hide} />
          </button>
          {updatedAt && (
            <button type="button" className="ush-mini-refresh" onClick={refresh} title={t('Yenile')}>⟳</button>
          )}
        </div>
        <div className="ush-balance__value mono">
          {loading && totalWallet == null ? '· · ·' : mask(fmtUsd(totalWallet))}
        </div>
        <div className="ush-balance__sub">
          <span className={totalUpnl == null ? 'dim' : upnlUp ? 'pos' : 'neg'}>
            {t('Açık K/Z')}: {totalUpnl == null ? '—' : mask(fmtUsdSigned(totalUpnl))}
          </span>
          {accounts.length > 1 && accounts.map((a) => (
            <span key={a.network} className="ush-chip ush-chip--net">
              {a.network === 'mainnet' ? 'Main' : 'Paper'} {mask(fmtUsd(a.wallet_balance))}
            </span>
          ))}
        </div>
      </section>

      {/* Kurulum Adımları — yeni kullanıcının canlı ilerleme kartı; kurulum
          tamamlanınca (4/4) kendini gizler. */}
      <OnboardingCard />

      {/* Açık pozisyonlar */}
      <section className="ush-section">
        <div className="ush-section__head">
          <h2>{t('Açık Pozisyonlar')}</h2>
          {open.length > 0 && <span className="ush-count">{open.length}</span>}
        </div>
        {loading && open.length === 0 ? (
          <div className="ush-empty">{t('Yükleniyor…')}</div>
        ) : open.length === 0 ? (
          <div className="ush-empty">{t('Açık pozisyon yok — sinyal bekleniyor.')}</div>
        ) : (
          <div className="ush-cardlist">
            {open.map((p) => (
              <PositionCard
                key={`${p.isGold ? 'g' : 'o'}${p.id}`}
                pos={p}
                snap={snapFor(p)}
                calc={calcFor(p)}
                onClick={tapOpen(p) ? () => setSel(p) : undefined}
              />
            ))}
          </div>
        )}
      </section>

      {/* Son işlemler teaser'ı */}
      {teaser.length > 0 && (
        <section className="ush-section">
          <div className="ush-section__head">
            <h2>{t('Son İşlemler')}</h2>
            <Link to="/islemler" className="ush-more">{t('Tümü')} →</Link>
          </div>
          <div className="ush-cardlist">
            {teaser.map((p) => (
              <ClosedCard
                key={`${p.isGold ? 'g' : 'o'}${p.id}`}
                pos={p}
                onClick={tapClosed(p) ? () => setSel(p) : undefined}
              />
            ))}
          </div>
        </section>
      )}

      {updatedAt && (
        <div className="ush-updated">{t('Güncellendi')}: {ago(updatedAt.toISOString(), t)}</div>
      )}

      {sel && (
        <LivePositionModal
          key={`${sel.isGold ? 'g' : 'o'}${sel.id}`}
          pos={sel}
          snap={snapFor(sel)}
          calc={calcFor(sel)}
          onClose={() => setSel(null)}
        />
      )}
    </div>
  );
}
