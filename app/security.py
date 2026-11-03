# -*- coding: utf-8 -*-
"""PIN 口令散列与登录令牌。只用标准库，避免额外的密码学依赖。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time

from .config import SECRET, TOKEN_TTL_DAYS

_ITER = 60000


def hash_pin(pin: str) -> str:
    salt = secrets.token_hex(8)
    dk = hashlib.pbkdf2_hmac("sha256", str(pin).encode("utf-8"), salt.encode(), _ITER)
    return f"pbkdf2${_ITER}${salt}${dk.hex()}"


def verify_pin(pin: str, stored: str) -> bool:
    try:
        algo, iters, salt, hex_dk = stored.split("$")
        if algo != "pbkdf2":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", str(pin).encode("utf-8"), salt.encode(), int(iters)
        )
        return hmac.compare_digest(dk.hex(), hex_dk)
    except Exception:
        return False


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def make_token(user_id: int, family_id: int, role: str) -> str:
    payload = {
        "uid": user_id,
        "fid": family_id,
        "role": role,
        "exp": int(time.time()) + TOKEN_TTL_DAYS * 86400,
    }
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64e(hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def parse_token(token: str) -> dict | None:
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    expect = _b64e(hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expect):
        return None
    try:
        payload = json.loads(_b64d(body))
    except Exception:
        return None
    if payload.get("exp", 0) < int(time.time()):
        return None
    return payload


def sign_answer(answer_key: dict) -> str:
    """小游戏答题签名：服务端出题、服务端判卷，前端无法伪造分数。"""
    body = _b64e(json.dumps(answer_key, separators=(",", ":")).encode())
    sig = _b64e(hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_answer(token: str) -> dict | None:
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    expect = _b64e(hmac.new(SECRET.encode(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, expect):
        return None
    try:
        return json.loads(_b64d(body))
    except Exception:
        return None
