<div align="center">

# 🎯 PUSU — Liquidity Ambush & Quant Signals
### *Açık Kaynak Algoritmik Alım-Satım, Strateji Araştırma ve Canlı Sinyal Laboratuvarı*
### *Open-Source Algorithmic Trading, Empirical Research & Live Signal Monitor*

[![Live Signals](https://img.shields.io/badge/Live%20Signals-Public%20Dashboard%20(No%20Login)-0ECB81?style=for-the-badge&logo=google-chrome&logoColor=white)](#-canlı-halka-açık-sinyal-ekranı--public-signals-dashboard)
[![Render Ready](https://img.shields.io/badge/Deploy%20on-Render-46E3B7?style=for-the-badge&logo=render&logoColor=black)](#-render--vercel-üzerinde-canlı-yayınlama-deployment)
[![Vercel Ready](https://img.shields.io/badge/Deploy%20on-Vercel-000000?style=for-the-badge&logo=vercel&logoColor=white)](#-render--vercel-üzerinde-canlı-yayınlama-deployment)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-18%20%2B%20Vite-61DAFB?style=for-the-badge&logo=react&logoColor=black)](https://react.dev/)
[![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](LICENSE)

<p align="center">
  <b>Giriş veya kimlik doğrulaması gerektirmeyen, tüm algoritmik stratejilerin (OPUS, TALOS-ICHI, MIDAS, Donchian) canlı sinyallerini ve gerçekleşen sonuçlarını şeffaf bir şekilde sergileyen halka açık platform.</b><br>
  <i>A public-facing quant trading dashboard showcasing real-time signals, multi-market strategies, and empirical performance metrics with zero login barrier.</i>
</p>

[🌐 Canlı Sinyal Ekranı](#-canlı-halka-açık-sinyal-ekranı--public-signals-dashboard) •
[🚀 Render & Vercel Deployment](#-render--vercel-üzerinde-canlı-yayınlama-deployment) •
[📊 Stratejiler](#-strateji-kitaplığı--strategy-suite) •
[🔬 Araştırma Raporları](#-araştırma-raporları--research-reports) •
[🔒 Güvenlik & Secret Temizliği](#-güvenlik-ve-ortam-değişkenleri-temizliği) •
[💻 Yerel Kurulum](#-yerel-kurulum-quickstart)

</div>

---

## 📢 Açık Kaynak Bildirisi & Şeffaflık (Open Source Release)

Bu depo artık **tamamen halka açık (public)** hale getirilmiştir. Piyasada gizlenecek bir sihirli formül veya %100 kusursuz bir algoritma yoktur; backtest üzerinde parlayan modellerin canlı piyasada borsa komisyonları (taker fees), likidite kaymaları (slippage) ve rejim değişiklikleriyle nasıl yüzleştiği bu repoda tüm çıplaklığıyla paylaşılmaktadır.

Bu projede:
* **Canlı Sinyal Takip Ekranı (`PublicSignalsPage`)**: Dışarıdan herkesin doğrudan erişebileceği, üyelik/giriş (login) gerektirmeyen şeffaf bir canlı sinyal paneli eklendi.
* **İkinci Bağımsız Dağıtım (Render & Vercel Ready)**: Özel API anahtarlarına ihtiyaç duymayan, yalnızca sinyalleri ve interaktif mum grafiklerini gösteren ikinci bir Render / Vercel web uygulaması olarak tek tıkla deploy edilebilir.
* **Geçmiş Commit & Secret Temizliği**: Tüm git geçmişi `git-filter-repo` ile taranarak eski commit'lerdeki her türlü hassas environment key, bot token ve veritabanı şifresi tamamen temizlenmiş, repo genel kullanıma hazır hale getirilmiştir.

---

## 🌐 Canlı Halka Açık Sinyal Ekranı / Public Signals Dashboard

Artık sistemde oturum açma zorunluluğu olmadan canlı sinyalleri izleyebileceğiniz ikinci bir genel arayüz bulunmaktadır:

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  PUSU CANLI SİNYAL AKIŞI (PUBLIC LIVE SIGNALS)                                    │
│  ● Canlı Borsa Taraması · 0 Login Engeli · İnteraktif TradingView Mum Grafikleri │
│                                                                                  │
│  [ OPUS (Kripto) ]  [ TALOS-ICHI (Altın) ]  [ MIDAS (VWAP) ]  [ DONCHIAN (1h) ]  │
│                                                                                  │
│  • Kazanma Oranı: %54.4       • Net R Getirisi: +388.6R      • Aktif İşlemler: 3 │
│  • Giriş, Zarar Durdur (SL) ve Kâr Al (TP) Seviyeleri Anlık Olarak Görünür       │
│  • Kartlara Tıklandığında Özel Mum Grafiği Açılır                                │
└──────────────────────────────────────────────────────────────────────────────────┘
```

> 🔗 **Canlı Demo / Yayındaki Uygulama Linki:**  
> `https://pusu-signals.onrender.com` *(veya Vercel üzerindeki kendi dağıtımınız)*  
> *(Projeyi Render veya Vercel'e bağladığınızda bu linki kendi alan adınızla güncelleyebilirsiniz).*

---

## 🚀 Render & Vercel Üzerinde Canlı Yayınlama (Deployment)

Projeyi dışarıdan herkesin görebileceği ikinci bir render veya vercel uygulaması olarak yayınlamak için gerekli konfigürasyonlar repoya hazır olarak dahil edilmiştir.

### 1. Render Static Site Olarak Dağıtım (Önerilen)
Repo kök dizininde hazır bir `render.yaml` yer almaktadır. Render Dashboard üzerinden:
1. [Render.com](https://render.com) adresine gidin ve **New + -> Static Site** seçeneğini seçin.
2. Bu GitHub reposunu (`ict-trade`) bağlayın.
3. Ayarları şu şekilde girin:
   - **Build Command:** `npm run build`
   - **Publish Directory:** `dist`
4. **Environment Variables** kısmına istemci değişkenlerini tanımlayın:
   - `VITE_SUPABASE_URL`: Supabase proje REST URL'iniz
   - `VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY`: Supabase anon/public key'iniz
5. **Create Static Site** butonuna tıklayın. Siteniz 1-2 dakika içinde canlıya alınır ve login gerektirmeyen genel sinyal paneli doğrudan açılır!

### 2. Vercel Üzerinde Dağıtım
Repo kök dizininde tek sayfa uygulama (SPA) yönlendirmelerini içeren `vercel.json` hazır bulunmaktadır:
1. [Vercel.com](https://vercel.com) adresine gidin ve **Add New -> Project** diyerek repoyu import edin.
2. Framework Preset olarak **Vite** otomatik algılanır.
3. Environment variables olarak `VITE_SUPABASE_URL` ve `VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY` değerlerini girin.
4. **Deploy** butonuna basın. Vercel sitenizi hemen yayınlar!

---

## 📊 Strateji Kitaplığı / Strategy Suite

Platform bünyesinde 5 ana kantitatif model ailesi yer alır:

| Strateji Adı | Kod Adı | Piyasa / Parite | Zaman Dilimi | Temel Mekanizma & Yürütme Modeli |
|---|---|---|---|---|
| 🟢 **OPUS** | `ATLAS` (`d30so8f3h7`) | Kripto Çoklu Varlık *(BTC, ETH, SOL...)* | 30m bar + 4h filtre | Donchian(55) kırılımı + 4h Kaufman ER filtreli trend takibi. 8R kademeli kâr al (scale-out) ve breakeven koruması. |
| 🟡 **TALOS-ICHI** | `MENKAR` (`talos_ichi`) | Altın *(XAUUSDT)* | 1m bar / Seans | Keltner kanalları + Ichimoku Kumo bulutu momentum takibi. 1.5×ATR başlangıç stopu ve 3.5×ATR dinamik trailing stop. |
| 🔵 **MIDAS** | `SIRIUS` (`midas`) | Altın *(XAUUSDT)* | 1m bar / Seans | Londra & NY seanslarında Hacim Ağırlıklı Ortalama Fiyat (VWAP) sapmaları ve ortalamaya dönüş (mean-reversion). |
| 🟣 **TALOS** | `ANTARES` (`talos`) | Altın *(XAUUSDT)* | 1m bar / Seans | Keltner kanalı bazlı klasik altın trend takip modeli. Oynaklık patlamalarında yönlü işlem. |
| 🟠 **DONCHIAN 1h** | `VEGA` (`donchianc`) | Kripto Çiftleri | 1h | 1 saatlik periyotta Donchian kanal kırılımları. 0.5R teyit mekanizmasıyla sahte kırılım (false breakout) filtresi. |

---

## 🔒 Güvenlik ve Ortam Değişkenleri Temizliği

Bu depo kamuya açılmadan önce titiz bir güvenlik denetiminden geçirilmiştir:
1. **Git Geçmişinden Secret'ların Silinmesi**: `git-filter-repo` aracıyla geçmişteki tüm commit ağaçları taranmış; eski `.env` dosyaları, Telegram bot token'ları ve eski veritabanı bağlantı parolaları commit geçmişinden geri döndürülemez biçimde temizlenmiştir.
2. **Sıfır Hardcoded Secret**: Kod tabanındaki hiçbir dosyada canlı API anahtarı, gizli anahtar veya şifre yer almaz.
3. **Örnek Şablon (`.env.example`)**: Gerekli tüm ortam değişkenleri dummy (sahte) yer tutucularla `.env.example` içinde belgelenmiştir.
4. **İstemci Güvenliği**: React/Vite tarafında sadece herkese açık olan `VITE_SUPABASE_URL` ve `VITE_SUPABASE_PUBLISHABLE_DEFAULT_KEY` değişkenleri kullanılır; Binance API gizli anahtarları kesinlikle istemci koduna dahil edilmez.

---

## 🔬 Araştırma Raporları / Research Reports

Repoda her stratejinin doğuşunu, backtest sonuçlarını ve canlı piyasa zorluklarını anlatan kapsamlı teknik raporlar mevcuttur:

* 📄 [STRATEJI-RAPORU.md](STRATEJI-RAPORU.md) — 20+ modelin 2024-2026 backtest ve out-of-sample (OOS) karşılaştırması.
* 📄 [ORDERFLOW-RAPORU.md](ORDERFLOW-RAPORU.md) — Kırılım mumlarında agresör delta dengesizliği ($z = +2.62$) analizi.
* 📄 [MIDAS.md](MIDAS.md) — Altın VWAP motoru, komisyon gerçekleri ve durum makinesi mimarisi.
* 📄 [ML-XAU-RAPORU.md](ML-XAU-RAPORU.md) — Triple Barrier yöntemi ve LightGBM meta-labeling deneyi (ve neden canlıya alınmadığı).
* 📄 [FX-GOLD-VWAP-RAPORU.md](FX-GOLD-VWAP-RAPORU.md) — XAUUSDT mikro-yapısı ve Monte Carlo boş hipotez testleri.
* 📄 [RUNBOOK.md](RUNBOOK.md) — Sistem operasyonları, Oracle Cloud sunucu kurulumu ve acil durum prosedürleri.

---

## 💻 Yerel Kurulum (Quickstart)

Projeyi kendi bilgisayarınızda çalıştırmak için:

### 1. Gereksinimler
* Node.js 18+ ve npm
* Python 3.10+

### 2. Arayüzü Başlatma
```bash
# Repoyu klonlayın
git clone https://github.com/huseyin-yigit-ulker/ict-trade.git
cd ict-trade

# Bağımlılıkları yükleyin
npm install

# Ortam değişkenlerini hazırlayın
cp .env.example .env

# Geliştirme sunucusunu başlatın
npm run dev
```
Uygulama tarayıcınızda `http://localhost:5173` adresinde açılır ve doğrudan canlı sinyal takip ekranını gösterir!

### 3. Python Motorunu Çalıştırma (İsteğe Bağlı)
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Bitcoin üzerinde OPUS stratejisi backtesti
python backtest/run_backtest.py --symbol BTCUSDT --interval 30m --days 90
```

---

## ⚠️ Yasal Uyarı & Risk Bildirimi (Disclaimer)

> **ÖNEMLİ BİLGİLENDİRME**: Bu repository, algoritmik modellerin mantığını, veri analiz yöntemlerini ve canlı sinyalleri incelemek amacıyla oluşturulmuş bir araştırma ve eğitim projesidir. Kripto varlıklar, emtialar ve vadeli işlem türevleri yüksek sermaye riski içerir. Geçmiş test sonuçları veya geçmiş kârlar gelecekteki getirilerin garantisi değildir. Buradaki hiçbir materyal yatırım veya finansal tavsiye niteliğinde değildir.

---

<div align="center">
  <sub>Açık kaynak araştırma projesi · Geliştirici: <b>Hüseyin Yiğit Ülker</b> · 2026</sub>
</div>
