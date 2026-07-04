#!/usr/bin/env python3
"""Generate a VAPID key pair for PUSU Web Push.

Prints two values — paste them where noted. Run ONCE; keep the private key secret
(never commit it). Regenerating invalidates every existing subscription.

    python scripts/gen_vapid.py

  VITE_VAPID_PUBLIC_KEY  -> frontend build env (Render / .env, VITE_ prefix so the
                            browser can read it — it is a PUBLIC key, safe to expose)
  VAPID_PRIVATE_KEY      -> the VM .env ONLY (used by sync/push_notify.py to sign)
  VAPID_SUBJECT          -> a contact URI, e.g. mailto:you@example.com (set in VM .env)

Uses `cryptography` (already installed). The public key is the uncompressed EC
P-256 point (the browser's applicationServerKey); the private key is the base64url
raw scalar accepted by pywebpush's `vapid_private_key`.
"""
import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def main() -> None:
    priv = ec.generate_private_key(ec.SECP256R1())
    priv_raw = priv.private_numbers().private_value.to_bytes(32, "big")
    pub_point = priv.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    print("# --- PUSU VAPID keys (generated once; keep the private key secret) ---")
    print()
    print("# frontend build env (Render env var / .env):")
    print(f"VITE_VAPID_PUBLIC_KEY={b64u(pub_point)}")
    print()
    print("# VM .env ONLY (never commit / never expose to the browser):")
    print(f"VAPID_PRIVATE_KEY={b64u(priv_raw)}")
    print("VAPID_SUBJECT=mailto:you@example.com")


if __name__ == "__main__":
    main()
