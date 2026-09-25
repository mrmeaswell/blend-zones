#!/usr/bin/env python3
"""Creates the RSA keypair Canvas needs for LTI 1.3.

Writes config/keys/private.pem and config/keys/public.pem (private key
mode 0600). Safe to re-run: refuses to overwrite an existing keypair
unless --force is passed, because replacing the key invalidates the
Developer Key registration in Canvas.
"""

import argparse
import os
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

KEY_DIR = Path(__file__).resolve().parent.parent / "config" / "keys"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="overwrite existing keys")
    args = parser.parse_args()

    KEY_DIR.mkdir(parents=True, exist_ok=True)
    private_path = KEY_DIR / "private.pem"
    public_path = KEY_DIR / "public.pem"

    if private_path.exists() and not args.force:
        print(f"Keypair already exists at {KEY_DIR}. Use --force to replace it.")
        print("Warning: replacing the key breaks the existing Canvas Developer Key.")
        return

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    private_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    os.chmod(private_path, 0o600)

    public_path.write_bytes(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    print(f"Wrote {private_path} (0600)")
    print(f"Wrote {public_path}")


if __name__ == "__main__":
    main()
