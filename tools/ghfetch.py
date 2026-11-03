# -*- coding: utf-8 -*-
"""
多源抓取器：国内直连 GitHub 经常被重置，这里把同一份内容挂到多个镜像上轮流试。

用法：
    python tools/ghfetch.py raw <user/repo> <branch> <path>      取单个文件到 stdout
    python tools/ghfetch.py list <user/repo> <path>              列目录（JSON）

设计上刻意做成独立脚本，不依赖项目里的任何模块，
这样它可以单独用来做一次性的教材搬运，不把网络的不确定性带进 app 运行时。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) kids-reward/1.0"
TIMEOUT = 30
RETRIES = 3

# 同一份文件的镜像模板，按实测的可靠性排序（大文件尤其看重前两条）
REPO_RAW_MIRRORS = [
    "https://ghfast.top/https://raw.githubusercontent.com/{repo}/{branch}/{path}",
    "https://cdn.jsdelivr.net/gh/{repo}@{branch}/{path}",
    "https://gh-proxy.com/https://raw.githubusercontent.com/{repo}/{branch}/{path}",
    "https://raw.githubusercontent.com/{repo}/{branch}/{path}",
    "https://ghproxy.net/https://raw.githubusercontent.com/{repo}/{branch}/{path}",
    "https://raw.gitmirror.com/{repo}/{branch}/{path}",
]


def _opener():
    # 绕过系统代理：Windows 注册表里的代理设置会让 urllib 走上不通的代理
    return urllib.request.build_opener(urllib.request.ProxyHandler({}))


OPENER = _opener()
OPENER.addheaders = [("User-Agent", UA), ("Accept", "*/*")]


def raw_urls(repo: str, branch: str, path: str) -> list[str]:
    """同一文件的多条取用路径，按优先级排。

    顺序是试出来的：ghfast 反代对大文件最稳；jsdelivr 走 CDN 最快，
    但超过 20MB 会直接 403，所以排在第二（小文件先命中它，大文件自动落到后面）；
    raw.githubusercontent 在国内时通时不通，留作兜底。
    """
    q = "/".join(urllib.parse.quote(seg) for seg in path.split("/"))
    return [tpl.format(repo=repo, branch=branch, path=q) for tpl in REPO_RAW_MIRRORS]


def api_urls(repo: str, path: str) -> list[str]:
    q = urllib.parse.quote(path)
    return [
        f"https://api.github.com/repos/{repo}/contents/{q}",
        f"https://ghfast.top/https://api.github.com/repos/{repo}/contents/{q}",
        f"https://gh-proxy.com/https://api.github.com/repos/{repo}/contents/{q}",
    ]


def fetch(urls: list[str], *, binary: bool = False) -> bytes:
    """依次尝试每一条路径，全失败才抛错。"""
    errs: list[str] = []
    for attempt in range(RETRIES):
        for u in urls:
            try:
                with OPENER.open(u, timeout=TIMEOUT) as r:
                    data = r.read()
                if not data:
                    raise ValueError("空响应")
                # 反代有时会把错误页以 200 返回
                if not binary and data.lstrip()[:1] in (b"<",) and b"{\"" not in data[:200]:
                    raise ValueError("拿到的是网页不是文件")
                return data
            except Exception as e:  # noqa: BLE001
                errs.append(f"{type(e).__name__}:{u.split('/')[2]}")
        if attempt < RETRIES - 1:
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError("所有镜像都失败：" + ", ".join(errs[-6:]))


def list_dir(repo: str, path: str) -> list[dict]:
    data = fetch(api_urls(repo, path))
    rows = json.loads(data)
    if isinstance(rows, dict):
        raise RuntimeError(str(rows.get("message"))[:120])
    return rows


def main() -> None:
    if len(sys.argv) < 4:
        print(__doc__)
        return
    cmd = sys.argv[1]
    if cmd == "raw":
        repo, branch, path = sys.argv[2], sys.argv[3], sys.argv[4]
        sys.stdout.buffer.write(fetch(raw_urls(repo, branch, path), binary=True))
    elif cmd == "list":
        repo, path = sys.argv[2], sys.argv[3]
        for x in list_dir(repo, path):
            print(f"{x['type']}\t{x.get('size', 0)}\t{x['name']}")


if __name__ == "__main__":
    main()
