# -*- coding: utf-8 -*-
"""
登录失败限流。

本地内网试用时这道防线可有可无，但一旦通过公网域名访问，4 位 PIN
（1 万种组合）在没有限制的情况下几秒钟就能被枚举出来，所以必须有。

实现刻意保持简单：进程内字典 + TTL，单实例够用。将来若要多实例部署，
换成 Redis 计数即可（接口不变）。
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict

_lock = threading.Lock()

# key -> [失败时间戳, ...]
_fails: dict[str, list[float]] = defaultdict(list)
# key -> 解锁时间戳
_locked_until: dict[str, float] = {}

MAX_FAILS = int(__import__("os").environ.get("KIDS_LOGIN_MAX_FAILS", "6"))
WINDOW_SEC = int(__import__("os").environ.get("KIDS_LOGIN_WINDOW", "600"))     # 10 分钟内
LOCK_SEC = int(__import__("os").environ.get("KIDS_LOGIN_LOCK", "300"))         # 锁 5 分钟
_CLEAN_INTERVAL = 300.0
_last_clean = time.time()


def _cleanup(now: float) -> None:
    """顺手清掉过期条目，避免长期运行后字典无限增长。"""
    global _last_clean
    if now - _last_clean < _CLEAN_INTERVAL:
        return
    _last_clean = now
    for k in list(_fails):
        if _fails[k] and now - _fails[k][-1] > WINDOW_SEC:
            del _fails[k]
    for k in list(_locked_until):
        if _locked_until[k] < now:
            del _locked_until[k]


def wait_seconds(key: str) -> int:
    """返回还需要等待的秒数；0 表示允许登录。"""
    now = time.time()
    with _lock:
        _cleanup(now)
        until = _locked_until.get(key, 0.0)
        if until > now:
            return int(until - now) + 1
    return 0


def record_fail(key: str) -> int:
    """记录一次失败。返回还需要重试前等待的秒数（0 表示尚未锁定）。"""
    now = time.time()
    with _lock:
        _cleanup(now)
        arr = _fails[key]
        arr.append(now)
        # 只保留时间窗内的失败记录
        _fails[key] = [t for t in arr if now - t <= WINDOW_SEC]
        if len(_fails[key]) >= MAX_FAILS:
            _locked_until[key] = now + LOCK_SEC
            _fails[key] = []
            return LOCK_SEC
    return 0


def reset(key: str) -> None:
    """登录成功后清零单个维度。"""
    with _lock:
        _fails.pop(key, None)
        _locked_until.pop(key, None)


def reset_many(keys: list[str]) -> None:
    """登录成功后，把这次用到的所有维度一起清零。

    只清账号是不够的：一家人（或走 Cloudflare Tunnel 时）共用同一个出口 IP，
    而 IP 维度的计数从来不清，几次手滑输错就会把全家人一起锁在门外。
    反过来，撞库的人不会登录成功，所以这里放行并不会削弱防护。
    """
    with _lock:
        for k in keys:
            _fails.pop(k, None)
            _locked_until.pop(k, None)


def client_ip(request) -> str:
    """取客户端真实 IP。

    走 Cloudflare Tunnel / nginx 时必须带上 --proxy-headers，
    否则这里拿到的永远是 127.0.0.1，限流会把全家人当成一个人。
    """
    if request is None:
        return "unknown"
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    return (request.client.host if request.client else "unknown") or "unknown"


def guard(account_key: str, ip: str):
    """同时按账号和 IP 两个维度检查。

    返回 (被拦截的等待秒数 or None, [需要 record_fail 的 key 列表])。
    """
    keys = [f"acct:{account_key}", f"ip:{ip}"]
    for k in keys:
        w = wait_seconds(k)
        if w:
            return w, keys
    return None, keys
