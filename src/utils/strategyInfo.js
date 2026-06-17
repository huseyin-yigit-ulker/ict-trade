// Per-strategy intro-card content, bilingual (tr / en). Rendered by StrategyIntro.jsx.
// Shape per language: { title, tagline, summary, sections:[{h,t}], caveat? }.
//
// 2026-06-16: pruned to a SINGLE stream — donchian. The MAIN/IMPULSE/KARMA/OPUS/RANGE/
// RANGE+ cards (and the Light / 1h-regime section twins) were removed with their streams;
// see sync/donchian/RETIRED_STREAMS_REPORT.md.

export const STRATEGY_INFO = {
  donchian: {
    icon: '⛰️', accent: '#F0B90B',
    tr: {
      title: 'DONCHIAN', tagline: 'Donchian-55 breakout — güçlü trend (momentum tamamlayıcı)',
      summary: 'Bir trend-takip stratejisi: fiyat son 55 barın ekstremini kırınca trende katılır ve YALNIZCA güçlü-trend rejiminde (Kaufman ER ≥ 0.35) ateşler. Mean-reversion sistemlerin yapısal tamamlayıcısı — getirileri düşük korelasyonlu, çünkü birbirini dışlayan rejimlerde para kazanır.',
      sections: [
        { h: 'Sinyal mantığı', t: 'Taze Donchian(55) kırılımı (1h kapanış): close son 55 barın en yükseğini aşarsa LONG, en düşüğünü kırarsa SHORT. Sustained breakout’ta bir kez ateşler (her barda değil). Sebepsel: kanal current barı dışlar (shift(1)), look-ahead yok.' },
        { h: 'Rejim kapısı', t: 'Kaufman Efficiency Ratio (24 bar) ≥ 0.35 — yalnızca GÜÇLÜ trend. ER-kovası kanıtı: kazancın tamamı ER>0.35’te, chop/light bantta zarar — yani güçlü-trend rejimini hasat eder.' },
        { h: 'Çıkış & risk', t: 'Stop = ATR(14)×2; hedef = sabit R/R = 4 (geniş hedef, trend-takip imzası). Tam-TP, kısmi yok. %0.1 round-trip ücret. Düşük WR (~%25) / büyük kazananlar — 4-5 ardışık kayıp normaldir.' },
        { h: 'Sonuçlar', t: '2026 (40 sembol, 1m): +288R, WR %23. OOS: 2025 +662R (3151 işlem), 2024 +102.5R (17 kripto, tam). Üç yılda da net pozitif — overfit değil.' },
        { h: 'Evren', t: '40 sembol (çekirdek: BTC/ETH/SOL/XAU/XAG). Trend edge’i crypto + metallerde güçlü; bazı hisse-perp’ler ve ORDI/ONDO tutarlı negatif (budama adayı).' },
      ],
      caveat: 'Parametreler (55 / ER0.35 / RR4) 2026’da seçildi; 2025+2024 OOS bu seçimi doğruladı. Slippage modellenmiyor → canlı R backtest’in biraz altında olur.',
    },
    en: {
      title: 'DONCHIAN', tagline: 'Donchian-55 breakout — strong trend (momentum complement)',
      summary: 'A trend-following strategy: it joins the trend when price breaks the 55-bar extreme and fires ONLY in the strong-trend regime (Kaufman ER ≥ 0.35). The structural complement to mean-reversion systems — returns are low-correlated because they earn in mutually exclusive regimes.',
      sections: [
        { h: 'Signal logic', t: 'Fresh Donchian(55) breakout (1h close): LONG if close exceeds the prior 55-bar high, SHORT if it breaks the low. Fires once per sustained breakout (not every bar). Causal: the channel excludes the current bar (shift(1)), no look-ahead.' },
        { h: 'Regime gate', t: 'Kaufman Efficiency Ratio (24 bars) ≥ 0.35 — STRONG trend only. ER-bucket proof: all profit is in ER>0.35 while it loses in the chop/light bands — it harvests the strong-trend regime.' },
        { h: 'Exit & risk', t: 'Stop = ATR(14)×2; target = fixed R/R = 4 (wide target, the trend-follower signature). Full-TP, no partial. 0.1% round-trip fee. Low WR (~25%) / large winners — 4-5 consecutive losers is normal.' },
        { h: 'Results', t: '2026 (40 symbols, 1m): +288R, WR 23%. OOS: 2025 +662R (3151 trades), 2024 +102.5R (17 crypto, full). Net positive all three years — not overfit.' },
        { h: 'Universe', t: '40 symbols (core: BTC/ETH/SOL/XAU/XAG). The trend edge is strong on crypto + metals; some stock-perps and ORDI/ONDO are consistently negative (prune candidates).' },
      ],
      caveat: 'Parameters (55 / ER0.35 / RR4) were chosen on 2026; the 2025+2024 OOS validated that choice. Slippage is not modelled → live R will be somewhat below backtest.',
    },
  },
  dch30_4h: {
    icon: '⛰️', accent: '#F0B90B',
    tr: {
      title: 'DONCHIAN 30m+4h', tagline: 'Hybrid: 30m kırılım + 4h trend yön onayı',
      summary: 'Çok-zaman-dilimli (MTF) hibrit: 30m Donchian(55) kırılımı yalnızca 4h trendi AYNI yönü onayladığında işleme alınır (4h kapanış, 4h 55-bar Donchian orta çizgisinin trade yönünde tarafında). 2026 MTF-doğrulama panelinin kazananı — saf 30m’den belirgin üstün.',
      sections: [
        { h: 'Sinyal mantığı', t: '30m kapanış 55-bar ekstremini kırar (LONG/SHORT). Sinyal sadece 4h trend yönü teyit ederse alınır: long için 4h kapanış 4h Donchian orta çizgisinin üstünde, short için altında. Sebepsel: sinyal ateşleme anında SADECE kapanmış 4h barları kullanılır.' },
        { h: 'Neden yön, ER değil', t: 'Base sinyal zaten kendi TF’inde ER-gated. 4h ER kapısı eklemek edge’i yok ediyor (tükenmiş trendleri seçiyor); 4h YÖN hizası ise dominant trendle hizalayıp R/işlemi 2 katına çıkarıyor.' },
        { h: 'Çıkış & risk', t: 'Stop = ATR(14)×2; hedef = sabit R/R = 4. Tam-TP. %0.1 round-trip ücret.' },
        { h: 'Sonuçlar', t: '2026 (40 sembol, 1m): +349R (4h_dir), saf 30m +240R’ye karşı; R/işlem +0.058→+0.120 (2×), ~%30 daha az işlem (daha az komisyon). 2025+2024 OOS doğrulaması devam ediyor.' },
        { h: 'Evren', t: '40 sembol. Trend edge’i crypto + metallerde güçlü; ABD hisse-perp’leri negatif (budama adayı).' },
      ],
      caveat: '4h onayı işlem sayısını azaltır ama kaliteyi artırır. Parametre 2026’da seçildi; OOS doğrulaması bekleniyor. Canlı R backtest’in altında olur.',
    },
    en: {
      title: 'DONCHIAN 30m+4h', tagline: 'Hybrid: 30m breakout + 4h trend-direction confirm',
      summary: 'A multi-timeframe (MTF) hybrid: a 30m Donchian(55) breakout is taken only when the 4h trend confirms the SAME direction (4h close on the trade’s side of its 55-bar Donchian midline). The winner of the 2026 MTF-validation panel — clearly superior to plain 30m.',
      sections: [
        { h: 'Signal logic', t: '30m close breaks the 55-bar extreme (LONG/SHORT). Taken only if the 4h trend confirms: for long, 4h close above its 4h Donchian midline; for short, below. Causal: only 4h bars CLOSED by the signal’s fire time are consulted.' },
        { h: 'Direction, not ER', t: 'The base signal is already ER-gated on its own TF. Adding a 4h-ER gate destroys the edge (it selects exhausted trends); 4h DIRECTION alignment instead keeps trades with the dominant trend and doubles R/trade.' },
        { h: 'Exit & risk', t: 'Stop = ATR(14)×2; target = fixed R/R = 4. Full-TP. 0.1% round-trip fee.' },
        { h: 'Results', t: '2026 (40 symbols, 1m): +349R (4h_dir) vs plain 30m +240R; R/trade +0.058→+0.120 (2×) on ~30% fewer trades (less fee drag). 2025+2024 OOS validation in progress.' },
        { h: 'Universe', t: '40 symbols. Trend edge is strong on crypto + metals; US stock-perps are negative (prune candidates).' },
      ],
      caveat: 'The 4h confirm cuts trade count but raises quality. Parameters chosen on 2026; OOS validation pending. Live R will be below backtest.',
    },
  },
};

export const infoFor = (strategy, lang) => {
  const e = STRATEGY_INFO[strategy];
  if (!e) return null;
  return { icon: e.icon, accent: e.accent, ...(e[lang] || e.tr) };
};
