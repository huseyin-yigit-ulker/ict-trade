import { useLang } from '../../context/LanguageContext';
import {
  STATE_BADGE, GOLD_BADGE, EXIT_LABEL, GOLD_EXIT,
  fmtPx, fmtUsd, fmtUsdSigned, fmtR, ago, countdown,
} from '../../utils/useLiveExec';

// Binance emir kartı görünümü — kullanıcı modunun tek pozisyon birimi.
// R-ekonomisi maskesi: cap/runner detayları admin-only olduğundan burada hedef
// her zaman nötr "Hedef" olarak yazılır (LivePositionsPage:104-106 kuralı).

const DirChip = ({ dir }) => {
  const lng = (dir || '').toUpperCase() === 'LONG';
  return <span className={`ush-chip ${lng ? 'ush-chip--long' : 'ush-chip--short'}`}>{lng ? 'LONG' : 'SHORT'}</span>;
};

const NetChip = ({ network, t }) => (
  network === 'testnet' ? <span className="ush-chip ush-chip--net">{t('Paper')}</span> : null
);

/** Açık pozisyon kartı. pos = {...row, isGold}; calc = liveCalc/goldCalc çıktısı. */
const PositionCard = ({ pos, snap, calc, onClick }) => {
  const { t } = useLang();
  const badge = (pos.isGold ? GOLD_BADGE : STATE_BADGE)[pos.state] || { label: pos.state, cls: 'st-wait' };
  const pre = pos.isGold
    ? pos.state !== 'OPEN'
    : pos.state === 'PENDING_ENTRY' || pos.state === 'ENTRY_WORKING';
  const cd = countdown(pre ? pos.entry_deadline : pos.time_stop_at, t);
  const pnlUsd = pos.isGold ? calc?.upnl : calc?.totalUsd;
  const pnlR = pos.isGold ? calc?.liveR : calc?.totalR;
  const up = Number(pnlUsd) >= 0;
  const tappable = !!onClick;

  return (
    <button
      type="button"
      className={`ush-poscard${tappable ? ' is-tap' : ''}`}
      onClick={onClick}
      disabled={!tappable}
      title={tappable ? t('Kartı gör ve paylaş') : undefined}
    >
      <div className="ush-poscard__top">
        <span className="ush-poscard__sym mono">{pos.symbol}</span>
        <DirChip dir={pos.direction} />
        <NetChip network={pos.network} t={t} />
        <span className={`ush-badge ${badge.cls}`}>{t(badge.label)}</span>
      </div>

      <div className="ush-poscard__pnl">
        <b className={`mono ${pnlUsd == null ? 'dim' : up ? 'pos' : 'neg'}`}>{fmtUsdSigned(pnlUsd)}</b>
        <span className={`mono ${pnlR == null ? 'dim' : Number(pnlR) >= 0 ? 'pos' : 'neg'}`}>{fmtR(pnlR)}</span>
        {!pos.isGold && calc?.isRunner && (
          <span className="ush-poscard__lock">🔒 {fmtUsdSigned(calc.bookedUsd)} {t('alındı')}</span>
        )}
        {pos.isGold && calc?.lockedR != null && (
          <span className="ush-poscard__lock">🔒 {fmtR(calc.lockedR)} {t('kilitli')}</span>
        )}
      </div>

      <div className="ush-poscard__grid">
        <div><span>{t('Giriş')}</span><b className="mono">{fmtPx(pos.eff_entry || pos.signal_entry)}</b></div>
        <div><span>{t('Mark')}</span><b className="mono">{fmtPx(snap?.mark_price)}</b></div>
        <div><span>SL</span><b className="mono">{fmtPx(pos.isGold ? (pos.cur_sl || pos.signal_sl) : pos.signal_sl)}</b></div>
        <div>
          <span>{pos.isGold ? t('Miktar') : t('Hedef')}</span>
          <b className="mono">{pos.isGold ? (pos.qty ?? '—') : fmtPx(pos.signal_cap)}</b>
        </div>
      </div>

      {cd && <div className="ush-poscard__meta">⏳ {pre ? t('Giriş penceresi') : t('Zaman limiti')}: {cd}</div>}
    </button>
  );
};

/** Kapalı işlem kartı (kompakt satır) — Portföy teaser'ı + İşlemler listesi paylaşır. */
export const ClosedCard = ({ pos, onClick }) => {
  const { t } = useLang();
  const cancelled = pos.state === 'CANCELLED';
  const win = Number(pos.realized_r) >= 0;
  const label = cancelled
    ? t('İPTAL')
    : (pos.isGold ? GOLD_EXIT : EXIT_LABEL)[pos.exit_reason] || pos.exit_reason || t('KAPANDI');
  const tappable = !!onClick;
  return (
    <button
      type="button"
      className={`ush-closedcard${tappable ? ' is-tap' : ''}`}
      onClick={onClick}
      disabled={!tappable}
      title={tappable ? t('Kartı gör ve paylaş') : undefined}
    >
      <div className="ush-closedcard__l">
        <span className="ush-closedcard__sym mono">{pos.symbol}</span>
        <DirChip dir={pos.direction} />
        <NetChip network={pos.network} t={t} />
        <span className={`ush-badge ${cancelled ? 'st-cancel' : win ? 'st-done' : 'st-sl'}`}>{t(label)}</span>
      </div>
      <div className="ush-closedcard__r">
        {!cancelled && (
          <>
            <b className={`mono ${win ? 'pos' : 'neg'}`}>{pos.realized_usd == null ? '—' : fmtUsd(pos.realized_usd)}</b>
            <span className={`mono ${win ? 'pos' : 'neg'}`}>{pos.realized_r == null ? '—' : fmtR(pos.realized_r)}</span>
          </>
        )}
        <span className="ush-closedcard__ago">{ago(pos.exit_time || pos.updated_at, t)}</span>
      </div>
    </button>
  );
};

export default PositionCard;
