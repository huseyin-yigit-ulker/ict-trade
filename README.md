# PUSU — Liquidity Ambush Intelligence

> 📘 **Full system runbook** (requirements, all streams, fresh-clone setup, cron, ops, changelog):
> **[RUNBOOK.md](RUNBOOK.md)**. Gold stream: [MIDAS.md](MIDAS.md).

React + Vite tabanlı ICT (Inner Circle Trader) sinyal paneli: canlı sinyaller,
backtest drill-down (Yıl → Ay → Gün), TradingView grafik entegrasyonu ve
Supabase veri katmanı.

```bash
npm install
npm run dev       # geliştirme
npm run build     # üretim (dist/)
npm run lint
```

## Güvenlik

Bu uygulama **statik bir frontend**tir — login ekranı yalnızca yumuşak bir
istemci tarafı kapıdır, gerçek güvenlik **Supabase RLS** politikalarındadır.
Bilinmesi gerekenler:

- **Giriş bilgileri** `.env` ile override edilir; bundle'a asla düz metin girmez:
  ```bash
  node scripts/gen-login-hash.mjs   # VITE_LOGIN_USER_SHA256 + VITE_LOGIN_PBKDF2 üretir
  ```
  Override yoksa repo'daki **varsayılan bilgiler** geçerlidir ve login ekranı
  bunun için görünür bir uyarı gösterir. Dağıtımda mutlaka değiştirin.
- **`.env` asla commit edilmez** (gitignore'da). İçinde Telegram bot token'ı ve
  Postgres bağlantı dizesi gibi gerçek sırlar vardır — bunlar yalnızca
  pipeline/backtest scriptleri içindir, frontend'e **yalnızca** `VITE_*` ve
  `BACKTESTING_VITE_*` önekli değerler sızar (bkz. `vite.config.js > envPrefix`).
- **CSP**: üretim build'ine `vite.config.js` içindeki `cspInject` eklentisi bir
  Content-Security-Policy meta'sı enjekte eder (Supabase + Binance + TradingView
  + Google Fonts beyaz listesi). Yeni bir dış kaynak eklerseniz CSP'yi güncelleyin.
- **Başarısız girişler** kalıcı üstel backoff ile kilitlenir (5 deneme → 30sn,
  her tekrarda iki katı, en çok 15 dk).
- Supabase publishable anahtarı bundle içinde **görünür olması normaldir**;
  veri erişimini sınırlayan şey RLS'dir. Tablolara anonim yazma/silme izni
  verilmediğini periyodik olarak doğrulayın.
