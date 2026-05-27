"""
实例加密模块 - RSA 密钥对管理
每个实例生成 2048 位 RSA 密钥对，用于好友关系安全验证
"""
import os
from pathlib import Path
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
import base64


class InstanceCrypto:
    """实例加密管理器，每个实例拥有一对 RSA 密钥"""

    def __init__(self, base_workplace: str):
        self.base_path = Path(base_workplace) / ".remote"
        self.private_key_path = self.base_path / "private_key.pem"
        self.public_key_path = self.base_path / "public_key.pem"
        self.friend_keys_dir = self.base_path / "friend_keys"

        self._private_key = None
        self._public_key = None

        self._ensure_keypair()

    def _ensure_keypair(self):
        """确保密钥对存在，不存在则生成"""
        if self.private_key_path.exists() and self.public_key_path.exists():
            self._load_keys()
        else:
            self._generate_keypair()

    def _generate_keypair(self):
        """生成 2048 位 RSA 密钥对"""
        self.base_path.mkdir(parents=True, exist_ok=True)
        key = RSA.generate(2048)
        self._private_key = key
        self._public_key = key.publickey()

        self.private_key_path.write_bytes(self._private_key.export_key())
        self.public_key_path.write_bytes(self._public_key.export_key())
        os.chmod(self.private_key_path, 0o600)
        print(f"[Crypto] 已生成 RSA 密钥对: {self.public_key_path}")

    def _load_keys(self):
        """加载已有密钥对"""
        self._private_key = RSA.import_key(self.private_key_path.read_bytes())
        self._public_key = RSA.import_key(self.public_key_path.read_bytes())

    def get_public_key_pem(self) -> str:
        """获取公钥 PEM 格式字符串"""
        return self._public_key.export_key().decode("utf-8")

    def get_friend_public_key(self, instance_id: str) -> str:
        """获取好友的公钥"""
        key_path = self.friend_keys_dir / f"{instance_id}.pem"
        if key_path.exists():
            return key_path.read_text()
        return None

    def save_friend_public_key(self, instance_id: str, public_key_pem: str):
        """保存好友的公钥"""
        self.friend_keys_dir.mkdir(parents=True, exist_ok=True)
        key_path = self.friend_keys_dir / f"{instance_id}.pem"
        key_path.write_text(public_key_pem)
        print(f"[Crypto] 已保存 {instance_id} 的公钥")

    def remove_friend_key(self, instance_id: str):
        """删除好友的公钥"""
        key_path = self.friend_keys_dir / f"{instance_id}.pem"
        if key_path.exists():
            key_path.unlink()
            print(f"[Crypto] 已删除 {instance_id} 的公钥")

    def encrypt_for_friend(self, instance_id: str, data: bytes) -> bytes:
        """使用好友公钥加密数据"""
        pub_pem = self.get_friend_public_key(instance_id)
        if not pub_pem:
            raise ValueError(f"没有找到 {instance_id} 的公钥")
        pub_key = RSA.import_key(pub_pem)
        cipher = PKCS1_OAEP.new(pub_key)
        return cipher.encrypt(data)

    def decrypt(self, encrypted_data: bytes) -> bytes:
        """使用自己的私钥解密数据"""
        cipher = PKCS1_OAEP.new(self._private_key)
        return cipher.decrypt(encrypted_data)
