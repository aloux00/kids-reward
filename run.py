# -*- coding: utf-8 -*-
"""
启动脚本
    python run.py              本机访问 http://127.0.0.1:8777
    python run.py --lan        手机 / 平板在同一 WiFi 下访问（监听 0.0.0.0）
    python run.py --proxy      在反向代理后面跑（Cloudflare Tunnel / nginx / Caddy）
                               不设这个，所有访客的 IP 都会显示成 127.0.0.1
    python run.py --lan --proxy
"""
from __future__ import annotations

import argparse
import socket

import uvicorn


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--lan", action="store_true", help="允许局域网内的手机/平板访问")
    ap.add_argument("--proxy", action="store_true",
                    help="前面有反向代理时用：信任 X-Forwarded-*，取到真实访客 IP")
    ap.add_argument("--port", type=int, default=8777)
    ap.add_argument("--reload", action="store_true",
                    help="改代码自动重载，只在开发时用（容器里由 KIDS_RELOAD=1 开启）")
    args = ap.parse_args()

    host = "0.0.0.0" if args.lan else "127.0.0.1"
    print("=" * 52)
    print("  儿童成长激励系统已启动")
    print(f"  本机访问：   http://127.0.0.1:{args.port}")
    if args.lan:
        print(f"  手机/平板：  http://{lan_ip()}:{args.port}   （需同一 WiFi）")
    print("  家长演示号： dad / 1234      孩子演示号： 头像 + 1234")
    if args.reload:
        print("  自动重载：   已开启（改 app/ 下的代码会立即生效）")
    print("=" * 52)
    uvicorn.run(
        "app.main:app",
        host=host,
        port=args.port,
        log_level="info",
        # --reload 必须同时给 reload_dirs：不给的话 uvicorn 会监视整个工作目录，
        # 而 data/ 里躺着几百 MB 教材，一启动就卡死。
        reload=args.reload,
        reload_dirs=["app"] if args.reload else None,
        # 反向代理后必须显式声明信任转发头，否则 uvicorn 一律忽略它们
        proxy_headers=args.proxy,
        forwarded_allow_ips="*" if args.proxy else None,
    )
