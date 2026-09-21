# coding=utf-8
"""凭证加密工具"""

import base64
import json
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


def _get_fernet() -> Fernet:
    settings = get_settings()
    raw = settings.CREDENTIAL_ENCRYPTION_KEY
    # Fernet 要求 32 字节 base64 key;开发期用户给的可能不是规范 base64,这里兜底
    try:
        return Fernet(raw.encode() if isinstance(raw, str) else raw)
    except (ValueError, Exception):
        # 兜底:用 hash 出一个稳定 key(仅开发期)
        import hashlib

        digest = hashlib.sha256(raw.encode()).digest()
        return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_credential(credential: dict[str, Any]) -> dict[str, Any]:
    """加密 credential dict,返回可入库的 dict {"enc": "<base64密文>"}"""
    if not credential:
        return {"enc": ""}
    f = _get_fernet()
    plaintext = json.dumps(credential, ensure_ascii=False).encode("utf-8")
    token = f.encrypt(plaintext)
    return {"enc": token.decode("ascii")}


def decrypt_credential(stored: dict[str, Any]) -> dict[str, Any]:
    """解密入库的 dict,返回明文 dict"""
    if not stored or not stored.get("enc"):
        return {}
    f = _get_fernet()
    try:
        plaintext = f.decrypt(stored["enc"].encode("ascii"))
        return json.loads(plaintext)
    except (InvalidToken, json.JSONDecodeError):
        return {}
