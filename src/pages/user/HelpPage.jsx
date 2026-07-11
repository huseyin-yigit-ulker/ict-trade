import { Link } from 'react-router-dom';
import { useLang } from '../../context/LanguageContext';

// Yardım / SSS — kullanıcı modunun statik mini rehberi. Anonimleştirme sınırına
// uyar: strateji mekaniği YOK; yalnız akış (kod adı), risk, anahtar, bildirim,
// durdurma gibi kullanıcıyı ilgilendiren işletim bilgisi.

const QA = [
  {
    q: 'PUSU nasıl çalışır?',
    a: 'Üç adım: (1) Sinyaller merkezî motor tarafından üretilir — siz grafik izlemezsiniz. (2) Emirler sizin Binance hesabınızda, sizin API anahtarınızla çalışır; paranız hiçbir zaman PUSU’ya geçmez. (3) Riski siz belirlersiniz: işlem başına tutar, eşzamanlı işlem sayısı ve günlük zarar tavanı sizin kontrolünüzdedir.',
  },
  {
    q: 'Param güvende mi?',
    a: 'API anahtarınız tarayıcınızda RSA ile şifrelenir ve yalnız şifreli saklanır; sunucu düz metni görmez. Anahtara ÇEKİM (withdraw) yetkisi vermezsiniz — sistem çekim yetkili anahtarı zaten reddeder. Paranız kendi Binance hesabınızda kalır; PUSU yalnız işlem açıp kapatır.',
  },
  {
    q: 'Riskimi nasıl kontrol ederim?',
    a: 'Bot sekmesindeki İnce Ayar bölümünden: işlem başına risk (USD), aynı anda en fazla kaç işlem, toplam risk ve günlük zarar tavanı. Hazır şablonlar bu değerleri tek dokunuşta güvenli kombinasyonlara kurar. Sunucu tarafı ayrıca toplam riski doğrulanmış bakiyenizin %25’iyle sınırlar.',
  },
  {
    q: 'Botu nasıl durdururum?',
    a: 'İki seviye vardır. DURDUR: yeni işlem açılmaz, açık pozisyonlar kurallarına göre yönetilerek kapatılır (önerilen yol). ACİL KAPAMA (KILL): tüm pozisyonlar derhal piyasa fiyatından kapatılır — yalnız acil durumda kullanın. İkisi de Bot sekmesindeki akış kartındadır.',
  },
  {
    q: 'Ücret ve komisyonlar nedir?',
    a: 'İşlemler kendi Binance hesabınızda gerçekleştiği için Binance’in standart vadeli işlem komisyonu ve funding (fonlama) maliyeti geçerlidir. Canlı sonuçlar; komisyon, kayma ve kısmi dolum nedeniyle geçmiş test sonuçlarının altında kalabilir.',
  },
  {
    q: 'Önce gerçek para bağlamadan denemek istiyorum.',
    a: 'Mümkün: Binance Futures Testnet’ten (testnet.binancefuture.com) ücretsiz bir test anahtarı alın ve Bot sekmesinde ağ olarak Paper’ı seçerek ekleyin. Paper işlemler sahte bakiye ile çalışır — birikiminiz riske girmez; arayüzde Paper etiketiyle görünür.',
  },
  {
    q: 'Bildirimler telefonuma gelmiyor.',
    a: 'Profil → Bildirimler’den izni verdiğinizden emin olun. iPhone’da önce siteyi Ana Ekrana Ekle ile kurmanız gerekir (Safari kısıtı); Android/Chrome’da doğrudan çalışır. İşlem açılış/kapanışları ve ilk haftanızda günlük özet otomatik gelir.',
  },
  {
    q: 'Sinyaller nereden geliyor?',
    a: 'Kod adlı otonom akışlardan (ör. ATLAS, MENKAR). Her akış uzun geçmiş verilerle doğrulanmış kurallarla merkezde çalışır; strateji detayları gizlidir. Sinyaller herkese aynı anda üretilir, emirler ise yalnız kendi hesabınızda ve kendi risk ayarlarınızla uygulanır.',
  },
];

export default function HelpPage() {
  const { t } = useLang();
  return (
    <div className="ush-help">
      <h1 className="ush-pagetitle">{t('Yardım & SSS')}</h1>
      <div className="ush-faq">
        {QA.map(({ q, a }) => (
          <details key={q} className="ush-faq__item">
            <summary>{t(q)}</summary>
            <p>{t(a)}</p>
          </details>
        ))}
      </div>
      <div className="ush-card ush-cta">
        <p>{t('Cevabını bulamadınız mı? Yöneticinize ulaşın veya bot kurulumuna dönün.')}</p>
        <Link to="/bot" className="ush-btn ush-btn--primary">{t('Bot sekmesine git')} →</Link>
      </div>
    </div>
  );
}
