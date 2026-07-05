// Client-side RSA-OAEP-SHA256 encryption of Binance API keys BEFORE they ever leave
// the browser: the DB only stores ciphertext, only the VM's private PEM can read it
// (sync/users/crypto.py). Public key ships as base64(SPKI DER) via VITE_EXEC_PUBKEY_B64
// (printed by scripts/gen_exec_keypair.py, set in the Render build env).

const PUBKEY_B64 = import.meta.env.VITE_EXEC_PUBKEY_B64 || '';

let keyPromise = null;

function importKey() {
  if (!keyPromise) {
    const raw = atob(PUBKEY_B64);
    const der = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) der[i] = raw.charCodeAt(i);
    keyPromise = crypto.subtle.importKey(
      'spki', der.buffer, { name: 'RSA-OAEP', hash: 'SHA-256' }, false, ['encrypt'],
    );
  }
  return keyPromise;
}

export function keycryptReady() {
  return !!PUBKEY_B64 && !!globalThis.crypto?.subtle;
}

/** plaintext (≤ ~318 bytes for RSA-3072) -> base64 ciphertext for user_api_keys.*_enc */
export async function encryptForVm(plaintext) {
  if (!keycryptReady()) throw new Error('keycrypt unavailable (VITE_EXEC_PUBKEY_B64 missing?)');
  const key = await importKey();
  const buf = await crypto.subtle.encrypt({ name: 'RSA-OAEP' }, key, new TextEncoder().encode(plaintext));
  const bytes = new Uint8Array(buf);
  let s = '';
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
  return btoa(s);
}
