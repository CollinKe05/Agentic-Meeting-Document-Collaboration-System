# AES-256-CBC + PKCS7 + base64 加密/解密工具
# 支持三种加密协议, 随机选择, 自动检测解密
# 依赖: pip install pycryptodome
import base64
import os
import random
import hashlib
import json
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

BLOCK_SIZE = 16

DEFAULT_KEY = "default-strong-key-1234567890"


def _fix_key(key: str) -> bytes:
    if not isinstance(key, str):
        key = str(key)
    key_bytes = key.encode("utf-8")
    if len(key_bytes) < 32:
        repetitions = (32 // len(key_bytes)) + 1
        key_bytes = (key_bytes * repetitions)[:32]
    else:
        key_bytes = key_bytes[:32]
    return key_bytes


# ── 协议1: 基本 AES-256-CBC ──

def encrypt_text_protocol1(plain_text: str, key: str) -> str:
    key_bytes = _fix_key(key)
    iv = os.urandom(BLOCK_SIZE)
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
    padded = pad(plain_text.encode("utf-8"), BLOCK_SIZE)
    encrypted = cipher.encrypt(padded)
    encrypted_data = iv + encrypted
    return base64.b64encode(encrypted_data).decode("utf-8")


def decrypt_text_protocol1(enc_text: str, key: str) -> str:
    key_bytes = _fix_key(key)
    enc_data = base64.b64decode(enc_text)
    iv = enc_data[:BLOCK_SIZE]
    encrypted = enc_data[BLOCK_SIZE:]
    cipher = AES.new(key_bytes, AES.MODE_CBC, iv)
    padded = cipher.decrypt(encrypted)
    plain = unpad(padded, BLOCK_SIZE)
    return plain.decode("utf-8")


# ── 协议2: PBKDF2-HMAC-SHA256 密钥派生 ──

def encrypt_text_protocol2(plain_text: str, key: str) -> str:
    salt = os.urandom(16)
    key_hash = hashlib.pbkdf2_hmac("sha256", key.encode("utf-8"), salt, iterations=10000)
    iv = os.urandom(BLOCK_SIZE)
    cipher = AES.new(key_hash, AES.MODE_CBC, iv)
    padded = pad(plain_text.encode("utf-8"), BLOCK_SIZE)
    encrypted = cipher.encrypt(padded)
    metadata = {
        "protocol": 2,
        "salt": base64.b64encode(salt).decode("utf-8"),
        "iv": base64.b64encode(iv).decode("utf-8"),
    }
    result = {"metadata": metadata, "data": base64.b64encode(encrypted).decode("utf-8")}
    return base64.b64encode(json.dumps(result).encode("utf-8")).decode("utf-8")


def decrypt_text_protocol2(enc_text: str, key: str) -> str:
    data = json.loads(base64.b64decode(enc_text).decode("utf-8"))
    metadata = data["metadata"]
    encrypted = base64.b64decode(data["data"])
    salt = base64.b64decode(metadata["salt"])
    iv = base64.b64decode(metadata["iv"])
    key_hash = hashlib.pbkdf2_hmac("sha256", key.encode("utf-8"), salt, iterations=10000)
    cipher = AES.new(key_hash, AES.MODE_CBC, iv)
    padded = cipher.decrypt(encrypted)
    plain = unpad(padded, BLOCK_SIZE)
    return plain.decode("utf-8")


# ── 协议3: 双层 AES-256-CBC ──

def encrypt_text_protocol3(plain_text: str, key: str) -> str:
    salt = os.urandom(16)
    key_hash1 = hashlib.pbkdf2_hmac("sha256", key.encode("utf-8"), salt, iterations=5000)
    key_hash2 = hashlib.pbkdf2_hmac("sha256", key.encode("utf-8") + salt, salt, iterations=7500)
    iv1 = os.urandom(BLOCK_SIZE)
    cipher1 = AES.new(key_hash1, AES.MODE_CBC, iv1)
    padded1 = pad(plain_text.encode("utf-8"), BLOCK_SIZE)
    encrypted1 = cipher1.encrypt(padded1)
    iv2 = os.urandom(BLOCK_SIZE)
    cipher2 = AES.new(key_hash2, AES.MODE_CBC, iv2)
    padded2 = pad(encrypted1, BLOCK_SIZE)
    encrypted2 = cipher2.encrypt(padded2)
    metadata = {
        "protocol": 3,
        "salt": base64.b64encode(salt).decode("utf-8"),
        "iv1": base64.b64encode(iv1).decode("utf-8"),
        "iv2": base64.b64encode(iv2).decode("utf-8"),
    }
    result = {"metadata": metadata, "data": base64.b64encode(encrypted2).decode("utf-8")}
    return base64.b64encode(json.dumps(result).encode("utf-8")).decode("utf-8")


def decrypt_text_protocol3(enc_text: str, key: str) -> str:
    data = json.loads(base64.b64decode(enc_text).decode("utf-8"))
    metadata = data["metadata"]
    encrypted2 = base64.b64decode(data["data"])
    salt = base64.b64decode(metadata["salt"])
    iv1 = base64.b64decode(metadata["iv1"])
    iv2 = base64.b64decode(metadata["iv2"])
    key_hash1 = hashlib.pbkdf2_hmac("sha256", key.encode("utf-8"), salt, iterations=5000)
    key_hash2 = hashlib.pbkdf2_hmac("sha256", key.encode("utf-8") + salt, salt, iterations=7500)
    cipher2 = AES.new(key_hash2, AES.MODE_CBC, iv2)
    padded1 = unpad(cipher2.decrypt(encrypted2), BLOCK_SIZE)
    cipher1 = AES.new(key_hash1, AES.MODE_CBC, iv1)
    plain = unpad(cipher1.decrypt(padded1), BLOCK_SIZE)
    return plain.decode("utf-8")


# ── 自动选择协议 ──

def encrypt_text(plain_text: str, key: str = None) -> str:
    if key is None:
        key = os.environ.get("MARKDOWN_ENCRYPT_KEY", DEFAULT_KEY)
    protocol = random.randint(1, 3)
    if protocol == 1:
        encrypted = encrypt_text_protocol1(plain_text, key)
        return '{"metadata": {"protocol": 1}, "data": "' + encrypted + '"}'
    elif protocol == 2:
        return encrypt_text_protocol2(plain_text, key)
    else:
        return encrypt_text_protocol3(plain_text, key)


def decrypt_text(enc_text: str, key: str = None) -> str:
    if key is None:
        key = os.environ.get("MARKDOWN_ENCRYPT_KEY", DEFAULT_KEY)
    try:
        data = json.loads(enc_text)
        protocol = data.get("metadata", {}).get("protocol", 1)
        if protocol == 1:
            return decrypt_text_protocol1(data["data"], key)
        elif protocol == 2:
            return decrypt_text_protocol2(enc_text, key)
        elif protocol == 3:
            return decrypt_text_protocol3(enc_text, key)
        else:
            raise ValueError(f"未知的加密协议: {protocol}")
    except json.JSONDecodeError:
        return decrypt_text_protocol1(enc_text, key)


# ── 文件级辅助函数 ──

def is_encrypted(content: str) -> bool:
    """检测内容是否为加密密文"""
    stripped = content.strip()
    if not stripped:
        return False
    # 明文 Markdown 几乎都以 # 开头
    if stripped.startswith("#"):
        return False
    # 尝试 JSON 解析, 检查是否有加密协议标识
    try:
        data = json.loads(stripped)
        if "metadata" in data and "protocol" in data.get("metadata", {}):
            return True
    except json.JSONDecodeError:
        pass
    # 长度较长且不以 markdown 标记开头, 可能是旧版 base64 密文
    if len(stripped) > 100:
        return True
    return False


def read_markdown_file(file_path: str, key: str = None) -> str:
    """读取 Markdown 文件, 自动检测并解密"""
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()
    if is_encrypted(content):
        return decrypt_text(content.strip(), key)
    return content


def write_markdown_file(file_path: str, content: str, encrypt: bool = False, key: str = None) -> str:
    """写入 Markdown 文件, 可选加密"""
    if encrypt:
        content = encrypt_text(content, key)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    return file_path
