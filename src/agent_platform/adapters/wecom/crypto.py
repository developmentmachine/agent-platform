"""企业微信回调消息加解密 (W5)。

参考 ``企业微信开发文档 / 回调消息加解密方案``：
- AES-256-CBC + PKCS7 padding；
- key = base64decode(EncodingAESKey + "=")，长度 32 字节；
- IV = key[:16]；
- 明文协议 = ``random(16) | msg_len(4 BE) | msg | corp_id``；
- ``msg_signature = sha1(sorted([token, timestamp, nonce, encrypt]))``。

与企业微信 AiBot / 应用 / 客户联系 IM 等所有回调通道复用同一套协议。
"""
from __future__ import annotations

import base64
import hashlib
import os
import socket
import struct
from dataclasses import dataclass
from typing import Tuple

from cryptography.hazmat.primitives import padding as sym_padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


class WecomCryptoError(Exception):
    """加解密 / 签名相关的统一异常基类。"""


class InvalidSignature(WecomCryptoError):
    """msg_signature 校验失败。"""


class InvalidCorpId(WecomCryptoError):
    """解密后 corp_id 与预期不匹配 — 可能伪造请求。"""


@dataclass(frozen=True)
class WecomCrypto:
    """企业微信回调加解密器（无状态，可全局复用）。"""

    token: str
    encoding_aes_key: str
    corp_id: str

    # ─── helpers ──────────────────────────────────────────────────────────

    def _aes_key(self) -> bytes:
        key = base64.b64decode(self.encoding_aes_key + "=")
        if len(key) != 32:
            raise WecomCryptoError(
                f"encoding_aes_key 解码后长度应为 32，实际 {len(key)}"
            )
        return key

    @staticmethod
    def _sha1_sorted(*items: str) -> str:
        joined = "".join(sorted(items))
        return hashlib.sha1(joined.encode("utf-8")).hexdigest()

    # ─── signature ────────────────────────────────────────────────────────

    def sign(self, timestamp: str, nonce: str, encrypted: str) -> str:
        return self._sha1_sorted(self.token, timestamp, nonce, encrypted)

    def verify_signature(
        self, msg_signature: str, timestamp: str, nonce: str, encrypted: str
    ) -> None:
        expect = self.sign(timestamp, nonce, encrypted)
        if expect != msg_signature:
            raise InvalidSignature(
                f"msg_signature mismatch: got={msg_signature} expected={expect}"
            )

    # ─── encrypt / decrypt ────────────────────────────────────────────────

    def decrypt(self, encrypted: str) -> Tuple[str, str]:
        """解密 base64 密文，返回 ``(plain_msg, decoded_corp_id)``。"""
        key = self._aes_key()
        iv = key[:16]
        raw = base64.b64decode(encrypted)
        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        decryptor = cipher.decryptor()
        padded = decryptor.update(raw) + decryptor.finalize()

        unpadder = sym_padding.PKCS7(algorithms.AES.block_size).unpadder()
        try:
            plain = unpadder.update(padded) + unpadder.finalize()
        except ValueError as e:
            raise WecomCryptoError(f"padding error: {e}") from e

        if len(plain) < 20:
            raise WecomCryptoError("decrypted body too short")

        msg_len = struct.unpack(">I", plain[16:20])[0]
        msg = plain[20 : 20 + msg_len]
        decoded_corp_id = plain[20 + msg_len :].decode("utf-8")

        if decoded_corp_id != self.corp_id:
            raise InvalidCorpId(
                f"corp_id mismatch: decoded={decoded_corp_id!r} expected={self.corp_id!r}"
            )
        return msg.decode("utf-8"), decoded_corp_id

    def encrypt(self, plain_msg: str, *, random_16: bytes | None = None) -> str:
        """加密明文，返回 base64 密文。"""
        key = self._aes_key()
        iv = key[:16]
        rand = random_16 or os.urandom(16)
        if len(rand) != 16:
            raise WecomCryptoError("random must be 16 bytes")
        msg_bytes = plain_msg.encode("utf-8")
        msg_len_be = struct.pack(">I", socket.htonl(socket.ntohl(len(msg_bytes))))
        body = rand + msg_len_be + msg_bytes + self.corp_id.encode("utf-8")

        padder = sym_padding.PKCS7(algorithms.AES.block_size).padder()
        padded = padder.update(body) + padder.finalize()

        cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
        encryptor = cipher.encryptor()
        encrypted = encryptor.update(padded) + encryptor.finalize()
        return base64.b64encode(encrypted).decode("utf-8")


__all__ = [
    "InvalidCorpId",
    "InvalidSignature",
    "WecomCrypto",
    "WecomCryptoError",
]
