import { useMemo, useState } from 'react';
import { useLang } from '../../context/LanguageContext';
import { useLiveExec, fmtUsd, fmtR } from '../../utils/useLiveExec';
import PositionCard, { ClosedCard } from '../../components/user/PositionCard';
import LivePositionModal from '../../components/trading/LivePositionModal';

// İşlemler — kullanıcının kendi işlem geçmişi (açık + kapalı, iki ağ birleşik).
// Dolu satır tıklanınca LivePositionModal (paylaşılabilir PUSU kartı) açılır;
// kapalı işlemde grafik bilinçli yok (da42fb1: "kart yeterli").

// Dikkat: 'Açık'/'Kapalı' anahtarları EN haritasında tema bağlamına (Light/Off)
// çevrildiğinden burada işlem-bağlamlı anahtarlar kullanılır.
const FILTERS = ['all', 'open', 'closed'];
const FILTER_LABEL = { all: 'Tümü', open: 'Açık Pozisyonlar', closed: 'Kapananlar' };

export default function TradesPage() {
  const { t } = useLang();
  const { loading, open, closed, snapFor, calcFor } = useLiveExec();
  const [filter, setFilter] = useState('all');
  const [net, setNet] = useState('all');
  const [sel, setSel] = useState(null);

  const nets = useMemo(() => {
    const s = new Set([...open, ...closed].map((p) => p.network).filter(Boolean));
    return [...s];
  }, [open, closed]);

  const byNet = (list) => (net === 'all' ? list : list.filter((p) => p.network === net));
  const showOpen = filter !== 'closed' ? byNet(open) : [];
  const showClosed = filter !== 'open' ? byNet(closed) : [];

  // Kapalı işlemlerin özet toplamı (iptaller hariç) — hızlı performans okuması.
  const settled = showClosed.filter((p) => p.state === 'CLOSED');
  const sumUsd = settled.reduce((a, p) => a + (Number(p.realized_usd) || 0), 0);
  const sumR = settled.reduce((a, p) => a + (Number(p.realized_r) || 0), 0);
  const wins = settled.filter((p) => Number(p.realized_r) >= 0).length;

  const tapOpen = (p) => (p.isGold ? p.state === 'OPEN' && p.entry_fill_time : true);
  const tapClosed = (p) => p.state === 'CLOSED' && p.entry_fill_time;
  const isEmpty = !loading && showOpen.length === 0 && showClosed.length === 0;

  return (
    <div className="ush-trades">
      <div className="ush-filterrow">
        {FILTERS.map((f) => (
          <button
            key={f}
            type="button"
            className={`ush-filter${filter === f ? ' is-active' : ''}`}
            onClick={() => setFilter(f)}
          >
            {t(FILTER_LABEL[f])}
          </button>
        ))}
        {nets.length > 1 && (
          <div className="ush-netseg">
            {['all', ...nets].map((n) => (
              <button
                key={n}
                type="button"
                className={`ush-filter ush-filter--net${net === n ? ' is-active' : ''}`}
                onClick={() => setNet(n)}
              >
                {n === 'all' ? t('Tümü') : n === 'mainnet' ? 'Main' : 'Paper'}
              </button>
            ))}
          </div>
        )}
      </div>

      {settled.length > 1 && filter !== 'open' && (
        <div className="ush-card ush-tradesum">
          <div><span>{t('Kapalı işlem')}</span><b className="mono">{settled.length}</b></div>
          <div><span>{t('Kazanan')}</span><b className="mono">{wins}/{settled.length}</b></div>
          <div><span>{t('Toplam K/Z')}</span><b className={`mono ${sumUsd >= 0 ? 'pos' : 'neg'}`}>{fmtUsd(sumUsd)}</b></div>
          <div><span>R</span><b className={`mono ${sumR >= 0 ? 'pos' : 'neg'}`}>{fmtR(sumR)}</b></div>
        </div>
      )}

      {loading && isEmpty ? (
        <div className="ush-empty">{t('Yükleniyor…')}</div>
      ) : isEmpty ? (
        <div className="ush-empty">{t('Henüz işlem yok.')}</div>
      ) : (
        <>
          {showOpen.length > 0 && (
            <section className="ush-section">
              <div className="ush-section__head"><h2>{t('Açık Pozisyonlar')}</h2><span className="ush-count">{showOpen.length}</span></div>
              <div className="ush-cardlist">
                {showOpen.map((p) => (
                  <PositionCard
                    key={`${p.isGold ? 'g' : 'o'}${p.id}`}
                    pos={p}
                    snap={snapFor(p)}
                    calc={calcFor(p)}
                    onClick={tapOpen(p) ? () => setSel(p) : undefined}
                  />
                ))}
              </div>
            </section>
          )}
          {showClosed.length > 0 && (
            <section className="ush-section">
              <div className="ush-section__head"><h2>{t('Kapananlar')}</h2><span className="ush-count">{showClosed.length}</span></div>
              <div className="ush-cardlist">
                {showClosed.map((p) => (
                  <ClosedCard
                    key={`${p.isGold ? 'g' : 'o'}${p.id}`}
                    pos={p}
                    onClick={tapClosed(p) ? () => setSel(p) : undefined}
                  />
                ))}
              </div>
            </section>
          )}
        </>
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
