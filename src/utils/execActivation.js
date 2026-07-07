import { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { getJSON } from './supa';

// Kullanıcının canlı-işlem AKTİVASYONU (2026-07-07, kullanıcı isteği): bir ağın (mainnet/testnet)
// işlem yüzeyi ancak kullanıcı o ağda (1) GEÇERLİ API anahtarı ve (2) ENABLED bir akış satırı
// (sembol seçili) kurduysa UI'da görünür — "diğer türlü boş olsun".
//
// Sorgular user_id=eq.<uid> ile daralır: user_api_keys_public ve user_stream_settings
// RLS'i admin'e TÜM satırları açar (is_admin OR own) — filtre olmadan admin'in aktivasyonu
// başka kullanıcıların satırlarından "true" çıkardı.
//
// Modül-seviyesi cache: Sidebar + MobileTabBar + sayfalar aynı oturumda tek fetch paylaşır;
// İşlem Merkezi bir ayar kaydettiğinde yaydığı SETTINGS_EVT cache'i düşürür (canlı tazelenir).

const SETTINGS_EVT = 'pusu:stream-settings-changed';   // trading/streams.js emitSettingsChanged ile aynı ad

let cache = null;
let cacheUid = null;
let inflight = null;

if (typeof window !== 'undefined') {
  window.addEventListener(SETTINGS_EVT, () => { cache = null; inflight = null; });
}

export async function fetchExecActivation(uid) {
  if (cache && cacheUid === uid) return cache;
  if (inflight && cacheUid === uid) return inflight;
  cacheUid = uid;
  const q = uid ? `&user_id=eq.${uid}` : '';
  inflight = Promise.all([
    getJSON(`user_api_keys_public?select=network,status${q}`).catch(() => []),
    getJSON(`user_stream_settings?select=network,enabled,symbols${q}`).catch(() => []),
  ]).then(([keys, sets]) => {
    const validKey = (net) => (keys || []).some((k) => k.network === net && k.status === 'valid');
    const enabled = (net) => (sets || []).some((s) => s.network === net && s.enabled && (s.symbols || []).length > 0);
    cache = {
      mainnet: validKey('mainnet') && enabled('mainnet'),
      testnet: validKey('testnet') && enabled('testnet'),
    };
    return cache;
  });
  return inflight;
}

/** { loading, mainnet, testnet } — kullanıcının kendi ağ-bazlı aktivasyonu. */
export function useExecActivation() {
  const { user } = useAuth();
  const uid = user?.id || null;
  const [act, setAct] = useState(cache && cacheUid === uid ? cache : null);

  useEffect(() => {
    let alive = true;
    const run = () => {
      if (!uid) { setAct({ mainnet: false, testnet: false }); return; }
      fetchExecActivation(uid).then((a) => { if (alive) setAct(a); });
    };
    run();
    window.addEventListener(SETTINGS_EVT, run);
    return () => { alive = false; window.removeEventListener(SETTINGS_EVT, run); };
  }, [uid]);

  return { loading: act == null, mainnet: !!act?.mainnet, testnet: !!act?.testnet };
}
