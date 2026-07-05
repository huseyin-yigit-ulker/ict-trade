"""Generate the VM's RSA-OAEP keypair for per-user Binance API key submission.

  .venv/bin/python scripts/gen_exec_keypair.py [--path ~/.exec_keys/exec_rsa.pem]

Writes the PRIVATE key PEM (chmod 600) OUTSIDE the repo, then prints:
  * the .env line (EXEC_PRIV_KEY_PATH=...)
  * the SPKI-b64 PUBLIC key for the Render env (VITE_EXEC_PUBKEY_B64=...)

Refuses to overwrite an existing PEM (rotating the keypair would orphan every
ciphertext in ict_trade.user_api_keys — users would have to re-submit keys).
"""
from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--path", default="~/.exec_keys/exec_rsa.pem")
    args = ap.parse_args()

    path = Path(args.path).expanduser()
    if path.exists():
        raise SystemExit(f"{path} already exists — refusing to overwrite (would orphan stored ciphertexts).")
    path.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(path.parent, 0o700)

    priv = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    pem = priv.private_bytes(encoding=serialization.Encoding.PEM,
                             format=serialization.PrivateFormat.PKCS8,
                             encryption_algorithm=serialization.NoEncryption())
    path.write_bytes(pem)
    os.chmod(path, 0o600)

    spki = priv.public_key().public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo)

    print(f"private key written: {path}")
    print("\nadd to .env (VM):")
    print(f"EXEC_PRIV_KEY_PATH={path}")
    print("\nadd to Render env (frontend build):")
    print(f"VITE_EXEC_PUBKEY_B64={base64.b64encode(spki).decode()}")


if __name__ == "__main__":
    main()
