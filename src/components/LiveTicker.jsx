import { useEffect, useState } from 'react';
import { useLang } from '../context/LanguageContext';

// Liquid Binance USDⓈ-M perps — overlaps the bot's traded set.
const SYMBOLS = [
  'BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT', 'XRPUSDT',
  'DOGEUSDT', 'ADAUSDT', 'SUIUSDT', 'NEARUSDT', 'ARBUSDT',
  '1000PEPEUSDT', 'WIFUSDT', 'FETUSDT', 'ONDOUSDT', 'ORDIUSDT',
];

const FAPI = 'https://fapi.binance.com/fapi/v1/ticker/24hr'; // Binance FUTURES
const POLL_MS = 5000;

const formatPrice = (p) => {
  if (!isFinite(p)) return '—';
  if (p >= 1000) return p.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (p >= 1) return p.toFixed(3);
  if (p >= 0.01) return p.toFixed(4);
  return p.toPrecision(4);
};

const baseOf = (sym) => sym.replace(/USDT$/, '');

const LiveTicker = () => {
  const { t } = useLang();
  const [prices, setPrices] = useState({});

  useEffect(() => {
    let stopped = false;
    let timer = null;

    const fetchOne = async (sym) => {
      try {
        const res = await fetch(`${FAPI}?symbol=${sym}`);
        if (!res.ok) return null;
        const d = await res.json();
        const price = parseFloat(d.lastPrice);
        const pct = parseFloat(d.priceChangePercent);
        if (!isFinite(price)) return null;
        return [sym, { price, pct }];
      } catch {
        return null;
      }
    };

    const poll = async () => {
      const results = await Promise.all(SYMBOLS.map(fetchOne));
      if (stopped) return;
      const next = {};
      for (const r of results) if (r) next[r[0]] = r[1];
      // Merge so a transient single-symbol failure keeps its last good value.
      setPrices((prev) => ({ ...prev, ...next }));
    };

    poll();
    timer = setInterval(poll, POLL_MS);

    return () => { stopped = true; if (timer) clearInterval(timer); };
  }, []);

  // Keep the bot's symbol order; only render the ones we have a price for.
  const items = SYMBOLS.map((s) => ({ symbol: s, ...prices[s] })).filter((i) => i.price != null);

  if (items.length === 0) {
    return (
      <div className="live-ticker">
        <div className="live-ticker__status">
          <span className="live-ticker__dot" /> {t('Canlı fiyatlar bağlanıyor…')}
        </div>
      </div>
    );
  }

  // Duplicate the row so the marquee can loop seamlessly.
  const renderRow = (keyPrefix) =>
    items.map((it) => {
      const up = (it.pct ?? 0) >= 0;
      return (
        <span className="lt-item" key={`${keyPrefix}-${it.symbol}`}>
          <span className="lt-sym">{baseOf(it.symbol)}</span>
          <span className="lt-price">{formatPrice(it.price)}</span>
          <span className={`lt-chg ${up ? 'up' : 'down'}`}>
            {up ? '▲' : '▼'} {Math.abs(it.pct ?? 0).toFixed(2)}%
          </span>
        </span>
      );
    });

  return (
    <div className="live-ticker" title="Binance Futures canlı fiyatlar (24s değişim)">
      <div className="live-ticker__label">
        <span className="live-ticker__dot live" /> {t('CANLI · FUTURES')}
      </div>
      <div className="live-ticker__viewport">
        <div className="live-ticker__track">
          {renderRow('a')}
          {renderRow('b')}
        </div>
      </div>
    </div>
  );
};

export default LiveTicker;
