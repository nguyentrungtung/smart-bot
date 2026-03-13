import os
import sys
import subprocess
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from datetime import datetime, timedelta
import jwt

def generate_keys(keys_dir=".keys"):
    """Generate RSA keypair for JWT signing (RS256)."""
    if not os.path.exists(keys_dir):
        os.makedirs(keys_dir)
        print(f"Created directory: {keys_dir}")

    private_path = os.path.join(keys_dir, "private_key.pem")
    public_path = os.path.join(keys_dir, "public_key.pem")

    if os.path.exists(private_path) and os.path.exists(public_path):
        print("Keys already exist. Skipping generation.")
        return

    print("Generating RSA keypair...")
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )

    # Save Private Key
    with open(private_path, "wb") as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))

    # Save Public Key
    with open(public_path, "wb") as f:
        f.write(private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ))

    print(f"Keys generated successfully in {keys_dir}")

def generate_token(user_id="admin_user", keys_dir=".keys"):
    """Generate a test JWT token for local development/testing."""
    private_path = os.path.join(keys_dir, "private_key.pem")
    if not os.path.exists(private_path):
        print("Error: Private key not found. Run key generation first.")
        return

    with open(private_path, "rb") as f:
        private_key = serialization.load_pem_private_key(f.read(), password=None)

    payload = {
        "sub": user_id,
        "name": "Smart-Bot Admin",
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(days=7)
    }

    token = jwt.encode(payload, private_key, algorithm="RS256")
    print(f"\n--- TEST JWT TOKEN (Valid for 7 days) ---")
    print(token)
    print("------------------------------------------\n")
    return token

if __name__ == "__main__":
    # If running inside core_backend, adjust keys_dir
    default_dir = ".keys" if os.path.exists("app") else "../.keys"
    generate_keys(default_dir)
    generate_token(keys_dir=default_dir)
