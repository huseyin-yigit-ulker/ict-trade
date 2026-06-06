import { useEffect } from 'react';
import { useTradeContext } from '../context/TradeContext';
import { useLang } from '../context/LanguageContext';

// Volume Radar = the engine's DYNAMIC (mode='dynamic') volume-anomaly picks:
// symbols outside the static 17 whose previous 1h bar volume spiked, then scanned
// by the same ICT strategies. Experimental / unvetted — framed as such.

const fmtPrice = (v) => {
  if (typeof v !== 'number' || !Number.isFinite(v)) return '--';
  const a = Math.abs(v);
  if (a === 0) return '0';
  if (a >= 100) return v.toFixed(2);
  if (a >= 1) return v.toFixed(4);
  if (a >= 0.01) return v.toFixed(5);
  return v.toPrecision(4);
};
const rrOf = (s) => {
  if (!s?.entry || !s?.sl || !s?.tp) return null;
  const risk = Math.abs(s.entry - s.sl);
  const reward = Math.abs(s.tp - s.entry);
  return risk ? reward / risk : null;
};
const STRAT = {
  A_liquidity_sweep_reversal: 'Liquidity Sweep',
  B_power_of_three: 'Power of Three',
  C_fvg_ob_confluence: 'FVG + OB',
  D_silver_bullet: 'Silver Bullet',
  E_eqh_eql_run: 'EQH / EQL',
  composite: 'Composite',
};

const VolumeRadarPage = () => {
  const { dynamicSignals, loadDynamic, setActiveSignal, setChartView } = useTradeContext();
  const { t, locale } = useLang();

  useEffect(() => { loadDynamic(); }, [loadDynamic]);

  return (
    <div className="radar-page">
      <div className="radar-head">
        <div className="radar-kicker">🔥 PUSU</div>
        <h2>{t('Hacim Radarı')}</h2>
        <p className="radar-sub">
          {t('Önceki periyotta anormal hacim artışı gösteren, sabit liste dışı semboller — aynı ICT motoruyla tarandı. Deneysel; backtest ile doğrulanmamış.')}
        </p>
      </div>

      {dynamicSignals.length === 0 ? (
        <div className="radar-empty">{t('Henüz dinamik sinyal yok.')}</div>
      ) : (
        <div className="trade-grid">
          {dynamicSignals.map((sig) => {
            const rr = rrOf(sig);
            const time = (sig.dateObj instanceof Date)
              ? sig.dateObj.toLocaleString(locale, { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
              : '--';
            return (
              <div
                key={sig.id}
                className="trade-card trade-card--radar"
                onClick={() => { setChartView('journal'); setActiveSignal(sig); }}
              >
                <div className="trade-head">
                  <span className="symbol-box">{sig.symbol}</span>
                  <span className={`dir-badge ${sig.dir.toLowerCase()}`}>
                    <span className="dir-arrow" aria-hidden="true">{sig.dir === 'LONG' ? '↗' : '↘'}</span>
                    {sig.dir}
                  </span>
                  <span className="radar-flag" title={t('Hacim anomalisi')}>🔥</span>
                  {rr != null && <span className="rr-pill">1:{rr.toFixed(2)}</span>}
                </div>
                <div className="trade-body">
                  <div className="trade-metric">
                    <span className="metric-label">{t('Tarih')}</span>
                    <span className="metric-value">{time}</span>
                  </div>
                  <div className="trade-metric">
                    <span className="metric-label">{t('Strateji')}</span>
                    <span className="metric-value">
                      {STRAT[sig.strategy] || sig.strategy || '--'}
                      {sig.confluenceScore != null ? ` · ${sig.confluenceScore}` : ''}
                    </span>
                  </div>
                  <div className="trade-metric">
                    <span className="metric-label">{t('Entry')}</span>
                    <span className="metric-value">{fmtPrice(sig.entry)}</span>
                  </div>
                  <div className="trade-metric">
                    <span className="metric-label">{t('Hedef')} / {t('Risk')}</span>
                    <span className="metric-value">
                      <span className="win">{fmtPrice(sig.tp)}</span> / <span className="loss">{fmtPrice(sig.sl)}</span>
                    </span>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default VolumeRadarPage;
