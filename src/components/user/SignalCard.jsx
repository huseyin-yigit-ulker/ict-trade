import { useLang } from '../../context/LanguageContext';

// Sinyal kartı — kullanıcı modu. Motor içi detay YOK (confluence/quality/ham
// sig.strategy basılmaz — akış kimliği YALNIZ kod adı çipiyle). Tıklanınca
// üst katman setActiveSignal ile global ChartModal'ı açar.

// Dashboard.jsx LIVE_STATUS_DISPLAY'in kopyası (oraya dokunmamak için — 14 satır).
const LIVE_STATUS_DISPLAY = {
  'TP Oldu':                           { label: 'TP', cls: 'st-tp' },
  'SL Oldu':                           { label: 'SL', cls: 'st-sl' },
  'BE Oldu':                           { label: 'BE', cls: 'st-tp' },
  'TP/SL Aynı Mum':                    { label: 'TP+SL', cls: 'st-mixed' },
  'İşlem Aktif (Entry Geldi)':         { label: 'AKTİF', cls: 'st-active' },
  'İşlem Aktif (Kısmi ½TP Alındı)':    { label: '½TP·BE', cls: 'st-active' },
  'İşlem Aktif (+1R Alındı · Runner)': { label: 'AKTİF·+1R', cls: 'st-active' },
  'İptal (Entry Gelmeden TP/SL)':      { label: 'İPTAL', cls: 'st-cancel' },
  'İptal (Süre Doldu)':                { label: 'İPTAL', cls: 'st-cancel' },
  'İptal (Ters Yön)':                  { label: 'İPTAL', cls: 'st-cancel' },
  'Sinyal Bekliyor':                   { label: 'BEKLİYOR', cls: 'st-wait' },
};
const statusDisplay = (s) => LIVE_STATUS_DISPLAY[s] || LIVE_STATUS_DISPLAY['Sinyal Bekliyor'];

// Küçük-cap tokenlarda anlamlı basamaklar ondalıkta — dinamik hassasiyet (Dashboard kopyası).
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

const timeAgo = (date, t) => {
  if (!(date instanceof Date)) return '—';
  const diffMs = Date.now() - date.getTime();
  if (diffMs < 0) return t('şimdi');
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return t('az önce');
  if (mins < 60) return t('{n} dk önce', { n: mins });
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return t('{h} sa {m} dk', { h: hrs, m: mins % 60 });
  const days = Math.floor(hrs / 24);
  return t('{d} gün {h} sa', { d: days, h: hrs % 24 });
};

/**
 * sig = TradeContext processed signal; live = liveStatuses[sig.id];
 * streamName = kod adı (codenameFor); effTime = efektif sinyal anı (bar CLOSE).
 */
const SignalCard = ({ sig, live, streamName, effTime, trailing, onClick }) => {
  const { t } = useLang();
  const lng = sig.dir === 'LONG';
  const sd = statusDisplay(live?.status);
  const active = (live?.status || '').startsWith('İşlem Aktif');

  return (
    <button type="button" className="ush-sigcard" onClick={onClick} title={t('Grafiği aç')}>
      <div className="ush-sigcard__top">
        <span className="ush-sigcard__sym mono">{sig.symbol}</span>
        <span className={`ush-chip ${lng ? 'ush-chip--long' : 'ush-chip--short'}`}>{lng ? 'LONG' : 'SHORT'}</span>
        <span className={`ush-badge ${sd.cls}`}>● {t(sd.label)}</span>
      </div>
      <div className="ush-sigcard__sub">
        <span className="ush-chip ush-chip--stream">{streamName}</span>
        <span className="ush-sigcard__ago">{timeAgo(effTime, t)}</span>
      </div>
      <div className="ush-sigcard__grid">
        <div><span>{t('Giriş')}</span><b className="mono">{formatPrice(sig.entry)}</b></div>
        {trailing ? (
          <div><span>{t('Son Fiyat')}</span><b className="mono">{live?.lastPrice != null ? formatPrice(live.lastPrice) : '—'}</b></div>
        ) : (
          <div><span>TP</span><b className="mono pos">{formatPrice(sig.tp)}</b></div>
        )}
        <div><span>SL</span><b className="mono neg">{formatPrice(sig.sl)}</b></div>
      </div>
      {active && !trailing && live?.lastPrice != null && (
        <div className="ush-sigcard__meta">
          {t('Son Fiyat')}: <b className="mono">{formatPrice(live.lastPrice)}</b>
        </div>
      )}
    </button>
  );
};

export default SignalCard;
