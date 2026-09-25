"""
Generates the RSA keypair the LTI tool needs to sign/verify with Canvas.
Run once before starting the app: python generate_keys.py

Produces keys/private.pem and keys/public.pem, which lti_config.json
already points at.
"""

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import os

os.makedirs("keys", exist_ok=True)

private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

with open("keys/private.pem", "wb") as f:
    f.write(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )

with open("keys/public.pem", "wb") as f:
    f.write(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

print("Wrote keys/private.pem and keys/public.pem")
