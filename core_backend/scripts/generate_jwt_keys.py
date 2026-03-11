import os
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization

def generate_keypair():
    # Tạo RSA private key (2048-bit)
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )

    # Trích xuất public key tương ứng
    public_key = private_key.public_key()

    # Chuyển đổi thành định dạng PEM (bytes)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    # Xác định thư mục lưu trữ nội bộ
    keys_dir = os.path.join(os.path.dirname(__file__), "..", ".keys")
    os.makedirs(keys_dir, exist_ok=True)

    private_path = os.path.join(keys_dir, "private_key.pem")
    public_path = os.path.join(keys_dir, "public_key.pem")

    # Lưu file
    with open(private_path, "wb") as f:
        f.write(private_pem)
    
    with open(public_path, "wb") as f:
        f.write(public_pem)

    print("✅ Đã tạo cặp khóa RSA thành công!")
    print(f"🔒 Private Key lưu tại: {private_path}")
    print(f"🔑 Public Key lưu tại: {public_path}")

if __name__ == "__main__":
    generate_keypair()
