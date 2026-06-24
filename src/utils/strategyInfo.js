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
        { h: 'Seans / zaman', t: 'ABD hisse-perp’leri YALNIZCA pre-market + regular seansında (04:00–16:00 ET, hafta içi, NYSE tatilleri hariç) sinyal üretir — dışında dayanak işlem görmez, gürültüdür. Metaller ~24/5, kripto 7/24 (gate yok). Canlı durum: topbar’daki 🕑 Seanslar penceresi.' },
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
        { h: 'Session / time', t: 'US stock-perps fire ONLY during pre-market + regular (04:00–16:00 ET, weekdays, ex-NYSE-holidays) — outside that the underlying doesn’t trade, so it is noise. Metals ~24/5, crypto 24/7 (no gate). Live status: the 🕑 Sessions window in the topbar.' },
      ],
      caveat: 'The 4h confirm cuts trade count but raises quality. Parameters chosen on 2026; OOS validation pending. Live R will be below backtest.',
    },
  },
  dch30_4h6: {
    icon: '⛰️', accent: '#F0B90B',
    tr: {
      title: 'DONCHIAN 30m+4h · 6R', tagline: 'Hibrit, geniş hedef: 1:6 R/R',
      summary: 'dch30_4h hibridiyle birebir AYNI giriş (30m kırılım + 4h yön onayı) ve AYNI −1R stop; tek fark hedef 6R. MFE analizi gösterdi ki kazananlar medyan ~+8R’ye gidiyor, kaybedenler doğruca stop’a (medyan +0R) — yani hedefi genişletmek kayıp tarafını değiştirmiyor, sadece kazananları daha çok yakalıyor.',
      sections: [
        { h: 'Neden 6R', t: 'RR-sweep’te R/işlem hedefle birlikte HER ÜÇ yılda da artıyor (2024/2025/2026); 6R, 4R’nin ~2 katı R/işlem veriyor. Tüm denenen filtreler içinde OOS’ta tutan TEK kaldıraç.' },
        { h: 'Asimetri', t: 'Kaybedenlerin sadece ~%38’i +1R’ye değiyor (medyan +0R) → doğruca stop. 4R TP’lerinin ~%51’i +4R DAHA gidiyor. Geniş hedef bu yapısal asimetriyi paraya çeviriyor.' },
        { h: 'Çıkış & risk', t: 'Stop = ATR(14)×2; hedef = sabit R/R = 6. Tam-TP. Çözülme hızlı: TP medyan ~1.4 gün, SL medyan ~6 saat.' },
        { h: 'Bedeli', t: 'WR %23 → ~%15. Equity eğrisi daha lumpy, drawdown’lar daha derin ama nadir. Nadir büyük kazanana daha bağımlı.' },
        { h: 'Seans / zaman', t: 'ABD hisse-perp’leri yalnızca pre-market + regular (04:00–16:00 ET, hafta içi, NYSE tatilleri hariç) sinyal üretir; metaller ~24/5, kripto 7/24. Canlı durum: topbar’daki 🕑 Seanslar.' },
      ],
      caveat: '6R, getiriyi artırır ama varyansı da. Daha düz eğri istersen 4R (dch30_4h) tercih et. Canlı R backtest’in altında olur.',
    },
    en: {
      title: 'DONCHIAN 30m+4h · 6R', tagline: 'Hybrid, wider target: 1:6 R/R',
      summary: 'Identical entry to the dch30_4h hybrid (30m breakout + 4h confirm) and the SAME −1R stop; only the target differs (6R). The MFE study found winners run to ~+8R median while losers go straight to stop (median +0R) — so widening the target does not change the loss side, it only captures more of the winners.',
      sections: [
        { h: 'Why 6R', t: 'In the RR-sweep, R/trade rises with the target in ALL THREE years (2024/2025/2026); 6R ~doubles R/trade vs 4R. The only lever that held up out-of-sample among everything tested.' },
        { h: 'Asymmetry', t: 'Only ~38% of losers reach +1R (median +0R) → straight to stop. ~51% of 4R TPs run +4R BEYOND. The wider target monetises this structural asymmetry.' },
        { h: 'Exit & risk', t: 'Stop = ATR(14)×2; target = fixed R/R = 6. Full-TP. Resolves fast: TP median ~1.4d, SL median ~6h.' },
        { h: 'The cost', t: 'WR 23% → ~15%. Lumpier equity curve, deeper but rarer drawdowns, more dependent on rare big winners.' },
        { h: 'Session / time', t: 'US stock-perps fire only during pre-market + regular (04:00–16:00 ET, weekdays, ex-NYSE-holidays); metals ~24/5, crypto 24/7. Live status: the 🕑 Sessions window in the topbar.' },
      ],
      caveat: '6R lifts returns but also variance. For a smoother curve prefer 4R (dch30_4h). Live R will be below backtest.',
    },
  },
  d30_4h_so: {
    icon: '⛰️', accent: '#2ECC71',
    tr: {
      title: 'DONCHIAN 30m+4h · WR', tagline: 'Yüksek isabet: kademeli çıkış + breakeven runner',
      summary: 'dch30_4h ile birebir AYNI giriş (30m kırılım + 4h yön onayı) ve AYNI −1R stop; fark çıkış modeli. Aynı edge’in DÜŞÜK-R / YÜKSEK-WR ucu: trend kitabı (6R) ~%26 WR / büyük kazananlarken bu ~%78 WR’lik düzgün bir eğri verir. Win rate’i ilk hedef belirler; runner sadece R ekler.',
      sections: [
        { h: 'Kademeli çıkış', t: 'Pozisyonun %60’ı +1R’de kapanır (WR’yi bu belirler). Kalan %40 RUNNER: stop breakeven’a çekilir; runner şunlardan İLK olanında kapanır — +4R cap (= sinyalin kendi TP’si), breakeven (fiyat girişe dönerse 0R), veya 3-günlük zaman-çıkışı (mark-to-market).' },
        { h: 'Runner cap (4R / 3g)', t: '2024-2026 sweep: kapaksız/20g +2776R; runner’ı +4R’de ve 3 günde sınırlamak +2438R (−%12) ama süreyi ≤3 güne, işlem başına R’yi ≤2.2R’ye indirir. WR değişmez (ilk hedef belirler). Alternatifler: cap6/3g +2594R (daha fazla R), cap3/3g +2388R (daha sıkı). Kullanıcı tercihi: 4R/3g denge.' },
        { h: 'Frontier', t: 'WR↔R aynı madalyonun iki yüzü: hedef düştükçe WR artar, R azalır. Sadece hedefi 0.5R’ye düşürmek fee yüzünden negatife döner (%69 WR, −99R). Scale-out, ~%54 WR’yi koruyarak runner ile R’yi geri kazanır.' },
        { h: 'Sonuçlar (OOS)', t: '3 yıl da pozitif (yön-teyitli + 4R/3g cap, tam 1m veriyle çözüldü): 2024 +749.6R (WR %76), 2025 +1068.5R (%79), 2026 +618.2R (%80) — toplam +2436.3R / 4641 işlem. 19 kripto + XAU; her runner penceresi pencere-sonunu aşan 1m veriyle (kenar marklarsız) çözülür.' },
        { h: 'Çıkış & risk', t: 'Stop = ATR(14)×2 (−1R). İlk hedef +1R’de %60; runner: +4R cap / breakeven / 3g zaman-çıkışı. %0.1 round-trip ücret. Dar hedefte fee orantısal olarak ağır — düşük-R’yi kabul et ama NEGATİF-R’yi değil.' },
      ],
      caveat: 'Backtest-only başladı (canlı sinyaller dch30_4h emit’inden gelir, scale-out olarak çözülür). Crypto+XAU evreni (hisse-perp/XAG dahil değil). Slippage modellenmiyor → canlı R backtest’in altında.',
    },
    en: {
      title: 'DONCHIAN 30m+4h · WR', tagline: 'High win-rate: scale-out + breakeven runner',
      summary: 'Identical entry to dch30_4h (30m breakout + 4h confirm) and the SAME −1R stop; only the exit differs. The LOW-R / HIGH-WR end of the same edge: the trend book (6R) is ~26% WR / big winners, this is a ~78% WR smooth curve. The first target sets the win rate; the runner only adds R.',
      sections: [
        { h: 'Scale-out', t: '60% of the position closes at +1R (this sets the WR). The remaining 40% is the RUNNER: its stop moves to breakeven, then it exits at the FIRST of — a +4R cap (== the signal’s own TP), breakeven (0R, price back to entry), or a 3-day time-exit (mark-to-market).' },
        { h: 'Runner cap (4R / 3d)', t: '2024-2026 sweep: uncapped/20d was +2776R; capping the runner at +4R and 3 days gives +2438R (−12%) but bounds duration to ≤3d and per-trade R to ≤2.2R. WR is unchanged (set by the first target). Alternatives: cap6/3d +2594R (more R), cap3/3d +2388R (tighter). User choice: 4R/3d balance.' },
        { h: 'The frontier', t: 'WR↔R are two sides of one coin: lower the target → higher WR, lower R. Merely cutting the target to 0.5R turns negative after fees (69% WR, −99R). Scale-out keeps ~54% WR while the runner recovers the R.' },
        { h: 'Results (OOS)', t: 'Positive all three years (directional-confirmed + 4R/3d cap, resolved on full 1m data): 2024 +749.6R (76% WR), 2025 +1068.5R (79%), 2026 +618.2R (80%) — total +2436.3R / 4641 trades. 19 crypto + XAU; every runner window is resolved on 1m data that extends past the window end (no data-edge marks).' },
        { h: 'Exit & risk', t: 'Stop = ATR(14)×2 (−1R). First target 60% at +1R; runner: +4R cap / breakeven / 3-day time exit. 0.1% round-trip fee. Fees bite proportionally hard at tight targets — accept low-R, not NEGATIVE-R.' },
      ],
      caveat: 'Shipped backtest-first (live signals come from the dch30_4h emit, resolved as scale-out). Crypto+XAU universe (no stock-perps/XAG). Slippage not modelled → live R below backtest.',
    },
  },
  d1h_so: {
    icon: '⛰️', accent: '#2ECC71',
    tr: {
      title: 'DONCHIAN 1h · WR', tagline: '1h kırılım + kademeli çıkış (4R/6R/8R) + breakeven runner',
      summary: 'Donchian 1h base sürümüyle (donchian ·0.5R) BİREBİR AYNI giriş — saf 1h Donchian(55) kırılımı, kendi-TF ER≥0.35 kapısı, 4h onayı YOK — ama full-TP yerine yüksek-WR kademeli çıkış modeliyle çözülür. 30m+4h scale-out ailesinin (d30so) 1h kardeşi: aynı mekanik, farklı zaman dilimi. Win-rate’i ilk hedef belirler; runner sadece R ekler.',
      sections: [
        { h: 'Giriş (1h, 4h onayı yok)', t: '1h kapanış 55-bar ekstremini kırar (LONG/SHORT), ER(24)≥0.35 güçlü-trend kapısı. 30m+4h ailesinden farkı: orada 4h yön onayı vardı; burada 1h kendi ER kapısını kullanır (donchian base ile aynı entry). Gerçekçi giriş: +0.5R onay seviyesinden doldurulur (risk = 1.5×ham).' },
        { h: 'Kademeli çıkış', t: 'Pozisyonun %60’ı +1R’de kapanır (WR’yi bu belirler, ~%53). Kalan %40 RUNNER: stop breakeven’a çekilir; runner şunlardan İLK olanında kapanır — +cap R (4/6/8), breakeven (girişe dönüş, 0R), veya 3-günlük zaman-çıkışı (mark-to-market).' },
        { h: 'Cap seçenekleri (4R / 6R / 8R)', t: 'Tek fark runner cap’i — üç sürüm AYNI 1h sinyali + AYNI +0.5R fill’i paylaşır, sadece runner tavanı değişir. Cap büyüdükçe toplam R artar, WR sabit kalır (%53). İsimler kasıtlı olarak açık: d1h_so4c / d1h_so6c / d1h_so8c — 30m+4h ailesinin d30so* etiketleriyle asla karışmaz.' },
        { h: 'Sonuçlar (OOS, +0.5R gerçekçi giriş, 3 yıl)', t: '19 kripto + XAU, tam 1m veriyle çözüldü, WR ~%53. 4R: 2024 −9.2R · 2025 +90.5R · 2026 +43.4R (top +124.4R). 6R: +12.7 / +106.4 / +29.9 (top +149.0R). 8R: +19.5 / +101.4 / +34.3 (top +155.1R). 6R ve 8R üç yılda da pozitif; 4R yalnız 2024’te hafif negatif (30m ailesindeki desenle aynı). Backtest-only.' },
        { h: 'Çıkış & risk', t: 'Stop = ATR(14)×2 (−1R, ham). İlk hedef +1R’de %60; runner: +cap R / breakeven / 3g zaman-çıkışı. %0.1 round-trip ücret. Aynı edge’in düşük-R/yüksek-WR ucu — 1h full-TP (donchian) ise düşük-WR/büyük-kazanan ucu.' },
      ],
      caveat: 'Backtest-only (canlı scanner yok; istenirse 1h donchian canlı sinyallerinden scale-out olarak çözülebilir). 30m+4h scale-out’a göre daha az ama daha uzun-soluklu sinyal (1h bar). Crypto+XAU evreni. Slippage modellenmiyor → canlı R backtest’in altında olur.',
    },
    en: {
      title: 'DONCHIAN 1h · WR', tagline: '1h breakout + scale-out (4R/6R/8R) + breakeven runner',
      summary: 'Identical entry to the Donchian 1h base (donchian ·0.5R) — plain 1h Donchian(55) breakout, own-TF ER≥0.35 gate, NO 4h confirm — but resolved under the high-WR scale-out exit instead of full-TP. The 1h sibling of the 30m+4h scale-out family (d30so): same mechanic, different timeframe. The first target sets the win rate; the runner only adds R.',
      sections: [
        { h: 'Entry (1h, no 4h confirm)', t: '1h close breaks the 55-bar extreme (LONG/SHORT), ER(24)≥0.35 strong-trend gate. Unlike the 30m+4h family (which adds a 4h-direction confirm), the 1h stream uses its own ER gate (same entry as the donchian base). Realistic entry: filled from the +0.5R confirmation level (risk = 1.5×raw).' },
        { h: 'Scale-out', t: '60% of the position closes at +1R (sets the WR, ~53%). The remaining 40% is the RUNNER: stop moves to breakeven, then it exits at the FIRST of — a +cap R (4/6/8) take-profit, breakeven (0R, back to entry), or a 3-day time-exit (mark-to-market).' },
        { h: 'Cap options (4R / 6R / 8R)', t: 'The only difference is the runner cap — the three versions share the SAME 1h signals + SAME +0.5R fill; only the runner ceiling changes. A higher cap lifts total R while WR stays fixed (53%). Names are deliberately explicit: d1h_so4c / d1h_so6c / d1h_so8c — never colliding with the 30m+4h family’s d30so* tags.' },
        { h: 'Results (OOS, +0.5R realistic entry, 3 years)', t: '19 crypto + XAU, resolved on full 1m data, WR ~53%. 4R: 2024 −9.2R · 2025 +90.5R · 2026 +43.4R (total +124.4R). 6R: +12.7 / +106.4 / +29.9 (total +149.0R). 8R: +19.5 / +101.4 / +34.3 (total +155.1R). 6R and 8R are positive all three years; only 4R dips slightly in 2024 (same pattern as the 30m family). Backtest-only.' },
        { h: 'Exit & risk', t: 'Stop = ATR(14)×2 (−1R, raw). First target 60% at +1R; runner: +cap R / breakeven / 3-day time exit. 0.1% round-trip fee. The low-R/high-WR end of the same edge — the 1h full-TP (donchian) is its low-WR/big-winner end.' },
      ],
      caveat: 'Backtest-only (no live scanner; could be resolved as scale-out off the 1h donchian live signals if wanted). Fewer but longer-horizon signals than the 30m+4h scale-out (1h bars). Crypto+XAU universe. Slippage not modelled → live R below backtest.',
    },
  },
};

export const infoFor = (strategy, lang) => {
  // Realistic-entry twins ('c' suffix) + scale-out runner-cap variants (d30so6...) derive from the
  // base card + a 0.5R-entry note, so they render everywhere without duplicating full cards.
  const realistic = strategy.endsWith('c') && !STRATEGY_INFO[strategy];
  let key = realistic ? strategy.slice(0, -1) : strategy;
  if (/^d30so\d+$/.test(key)) key = 'd30_4h_so';     // 6R/… scale-out cap variant -> base scale-out card
  if (/^d1h_so\d+$/.test(key)) key = 'd1h_so';       // 1h scale-out 4/6/8R cap variant -> 1h scale-out card
  const e = STRATEGY_INFO[key];
  if (!e) return null;
  const base = { icon: e.icon, accent: e.accent, ...(e[lang] || e.tr) };
  if (realistic) {
    base.title = `${base.title} ·0.5R`;
    base.tagline = lang === 'en'
      ? 'Realistic entry from the +0.5R confirmation zone (RR collapses 4→2.33 — the honest edge)'
      : 'Gerçekçi giriş: +0.5R onay bölgesinden (RR 4→2.33 düşer — dürüst edge)';
  }
  return base;
};
