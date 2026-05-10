# Medium Yazıları — ICT Trade Bot Serisi

Bu klasör, projeyi adım adım anlatan Medium yazılarının kaynak dosyalarını içerir. Her yazı `NN-konu.md` formatında; eşlik eden grafikler `images/` altında SVG olarak.

## Mevcut yazılar

| # | Dosya | Konu | Durum |
|---|---|---|---|
| 01 | [01-ict-strategies-foundation.md](01-ict-strategies-foundation.md) | ICT temel kavramları (FVG, OB, sweep, BOS/CHoCH, killzone, OTE) | ✅ Hazır |

## Yol haritası (sonraki yazılar)

| # | Konu | Notlar |
|---|---|---|
| 02 | 5 stratejinin anatomisi (A-E) | Her birini iki paragrafta + setup şartları + entry/SL/TP mantığı |
| 03 | Detector'ları Python'da yazmak | `detect_swings`, `detect_structure`, `detect_order_blocks`, `detect_fvgs` adım adım |
| 04 | Look-ahead bias avı | "Backtest'te ne kadar gizli bias var?" + truncated-data parity testi |
| 05 | 5 yıllık backtest sonuçları | 2022→2026, sembol/yıl/strateji breakdown, dürüst yorum |
| 06 | Production deployment | Airflow + Telegram + Supabase + dashboard nasıl bağlanıyor |

## Görseller (`images/`)

Tüm grafikler **SVG** formatında — vektörel, sıkıştırılmamış, sürüm kontrolünde okunabilir. Medium yayınlarken:

1. **Tarayıcıda SVG'yi aç** (örn. `images/04-fvg.svg`)
2. **Ekran görüntüsü al** (Cmd+Shift+4 / Win+Shift+S) veya
3. **SVG dosyasını PNG'ye dönüştür** (online converter ya da `rsvg-convert`)
4. Medium yazısına PNG olarak yükle

> Medium SVG dosyalarını doğrudan kabul etmiyor; PNG/JPG'ye dönüştürmek gerek.

| Dosya | Konu |
|---|---|
| [01-bos-choch.svg](images/01-bos-choch.svg) | BOS vs CHoCH karşılaştırma |
| [02-sweep.svg](images/02-sweep.svg) | Liquidity sweep mekaniği |
| [03-orderblock.svg](images/03-orderblock.svg) | Order Block tanımı + impulse |
| [04-fvg.svg](images/04-fvg.svg) | Fair Value Gap 3-bar pattern |
| [05-killzones.svg](images/05-killzones.svg) | NY saatleri + killzone bantları |
| [06-pd-ote.svg](images/06-pd-ote.svg) | Premium/Discount + OTE bölgesi |

Tema: Binance dark palette (matching dashboard).

## Yayın akışı (Medium)

1. Yazıyı [Medium](https://medium.com/) editöründe yeni story olarak aç
2. Markdown'ı kopyala-yapıştır — Medium çoğu syntax'ı tanır
3. Görselleri SVG → PNG dönüştürüp yerlerine ekle
4. Header image olarak ilk diagram'ı kullan (etkileyici)
5. Tag'leri ekle: `Trading`, `Crypto`, `Algorithmic Trading`, `ICT`, `Smart Money Concepts`, `Python`
6. Yayınla

## Lokal preview

VSCode'un built-in markdown preview'ı yeterli. Görseller relative path olduğu için doğrudan render olur.

```bash
cd medium/
code 01-ict-strategies-foundation.md
# Cmd+Shift+V → Markdown preview
```

## Ton ve dil tercihleri

- **Türkçe**, samimi (sen-ben), günlük dil
- **Jargon**'u açıklamadan kullanma
- Kod blokları varsa **kısa ve odaklı** (sayfa kaynak değil, fikir aktarıyor)
- Başlıklar **soru** veya **iddia** içersin (okur scroll'larken yakalansın)
- Her ana bölümde **bir görsel** (kavramı pekiştirmek için)
