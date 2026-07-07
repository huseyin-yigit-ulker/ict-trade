import { useCallback, useEffect, useState } from 'react';
import { useLang } from '../../context/LanguageContext';
import { getJSON, rpc } from '../../utils/supa';
import { encryptForVm, keycryptReady } from '../../utils/keycrypt';

// Binance API keys — one card per network. The browser RSA-encrypts key+secret
// (utils/keycrypt) BEFORE they leave the page; the DB only ever sees ciphertext
// (rotate_api_key RPC) and the read side is the sanitized user_api_keys_public view.

const VM_IP = import.meta.env.VITE_VM_EGRESS_IP;

const NETWORKS = [
  { network: 'mainnet', title: 'Mainnet', real: true },
  { network: 'testnet', title: 'Testnet (Paper)', real: false },
];

const NetworkKeyCard = ({ net, row, onSubmitted }) => {
  const { t, locale } = useLang();
  const [open, setOpen] = useState(false);
  const [apiKey, setApiKey] = useState('');
  const [secret, setSecret] = useState('');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState(null); // {kind:'ok'|'err', text}

  const submit = async (e) => {
    e.preventDefault();
    const key = apiKey.trim();
    const sec = secret.trim();
    if (busy || !key || !sec) return;
    setBusy(true);
    setNote(null);
    try {
      const keyEnc = await encryptForVm(key);
      const secEnc = await encryptForVm(sec);
      await rpc('rotate_api_key', {
        p_network: net.network,
        p_key_enc: keyEnc,
        p_secret_enc: secEnc,
        p_last4: key.slice(-4),
      });
      setApiKey('');
      setSecret('');
      setNote({ kind: 'ok', text: t('Anahtar alındı — doğrulama başladı (≤1 dk).') });
      onSubmitted();
    } catch (e2) {
      setNote({ kind: 'err', text: e2.message });
    } finally {
      setBusy(false);
    }
  };

  const statusChip = row && (
    row.status === 'valid' ? <span className="chip chip--ok">{t('Geçerli')}</span>
      : row.status === 'invalid' ? <span className="chip chip--err">{t('Geçersiz')}</span>
      : <span className="chip chip--warn">{t('Doğrulanıyor…')}</span>
  );

  return (
    <section className="overview-card settings-card">
      <div className="summary-title">
        {t('API Anahtarı')} · {net.title}
        {net.real && <span className="badge-real" style={{ marginLeft: 8 }}>{t('GERÇEK PARA')}</span>}
      </div>

      <div className="settings-row">
        <span>{t('Durum')}</span>
        {row ? statusChip : <b>{t('Anahtar yok')}</b>}
      </div>
      {row && (
        <div className="settings-row"><span>{t('Anahtar')}</span><b>•••• {row.key_last4 || '????'}</b></div>
      )}
      {row?.status === 'valid' && (
        <>
          <div className="settings-row">
            <span>{t('Bakiye')}</span>
            <b className="win">{row.balance_usdt != null ? `${Number(row.balance_usdt).toFixed(2)} USDT` : '—'}</b>
          </div>
          <div className="settings-row">
            <span>{t('Doğrulandı')}</span>
            <b>{row.verified_at ? new Date(row.verified_at).toLocaleString(locale) : '—'}</b>
          </div>
        </>
      )}
      {row?.status === 'invalid' && row.invalid_reason && (
        <div className="form-note form-note--err">{row.invalid_reason}</div>
      )}
      {row?.withdrawals_enabled === true && (
        <div className="key-banner key-banner--err">
          {t('Bu anahtarın ÇEKİM yetkisi var — reddedildi. Çekim yetkisiz yeni anahtar oluşturun.')}
        </div>
      )}
      {row?.position_mode_ok === false && (
        <div className="key-banner key-banner--warn">
          {t('Binance hesabınız hedge modda; one-way moda geçin.')}
        </div>
      )}

      <button className="header-btn" type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        {open ? '▾' : '▸'} {t('Anahtar Ekle/Yenile')}
      </button>
      {open && (
        keycryptReady() ? (
          <form className="key-form" onSubmit={submit}>
            <label className="tfield">
              <span>API Key</span>
              <input
                type="password" autoComplete="off" autoCapitalize="none" autoCorrect="off"
                spellCheck={false} maxLength={128} value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
              />
            </label>
            <label className="tfield">
              <span>API Secret</span>
              <input
                type="password" autoComplete="off" autoCapitalize="none" autoCorrect="off"
                spellCheck={false} maxLength={128} value={secret}
                onChange={(e) => setSecret(e.target.value)}
              />
            </label>
            <button className="apply-btn" type="submit" disabled={busy || !apiKey.trim() || !secret.trim()}>
              {busy ? '…' : t('Gönder')}
            </button>
          </form>
        ) : (
          <div className="form-note form-note--warn">
            {t('Şifreleme anahtarı yapılandırılmamış — anahtar gönderilemez (VITE_EXEC_PUBKEY_B64).')}
          </div>
        )
      )}
      {note && <div className={`form-note form-note--${note.kind}`}>{note.text}</div>}

      <ul className="key-notes">
        <li>{t('Anahtar yalnız şifreli saklanır (RSA) — sunucu düz metni hiç görmez.')}</li>
        <li>{t('Sadece Futures trade yetkisi verin.')}</li>
        <li>{t('Çekim (withdraw) yetkisi vermeyin.')}</li>
        <li>{t('IP kısıtı önerilir')}{VM_IP ? ` (VM IP: ${VM_IP})` : ''}</li>
        <li>
          <a href="https://www.binance.com/en/my/settings/api-management" target="_blank" rel="noreferrer">
            {t('Binance API yönetim sayfası')} ↗
          </a>
          {' · '}{t('adım adım kılavuz “Kurulum Rehberi” kartında.')}
        </li>
      </ul>
    </section>
  );
};

export default function ApiKeysCard() {
  const [keys, setKeys] = useState({});   // network -> latest non-rotated row
  const [err, setErr] = useState('');

  const load = useCallback(async () => {
    try {
      const rows = await getJSON('user_api_keys_public?select=*&order=created_at.desc');
      const latest = {};
      for (const r of rows || []) {
        if (r.status === 'rotated') continue;
        if (!latest[r.network]) latest[r.network] = r;   // rows are newest-first
      }
      setKeys(latest);
      setErr('');
    } catch (e) {
      setErr(e.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Poll every 5s while a verification is in flight; stop as soon as it settles.
  const pending = Object.values(keys).some((k) => k?.status === 'pending_verify');
  useEffect(() => {
    if (!pending) return undefined;
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, [pending, load]);

  return (
    <>
      {err && (
        <section className="overview-card settings-card">
          <div className="form-note form-note--err">{err}</div>
        </section>
      )}
      {NETWORKS.map((n) => (
        <NetworkKeyCard key={n.network} net={n} row={keys[n.network]} onSubmitted={load} />
      ))}
    </>
  );
}
