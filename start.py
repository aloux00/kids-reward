# -*- coding: utf-8 -*-
"""
一键启动向导

    python start.py            显示菜单
    python start.py --lan      直接以"手机/平板可访问"模式启动
    python start.py --local    直接以"仅本机"模式启动

双击 启动.bat 也可以，效果等同于不带参数运行本脚本。
"""
from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent
PORT = 8777
DATA_DIR = ROOT / "data"
BACKUP_DIR = ROOT / "backups"


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def port_in_use(port: int = PORT) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.6)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


def wait_ready(timeout: int = 25) -> bool:
    for _ in range(timeout * 2):
        if port_in_use():
            return True
        time.sleep(0.5)
    return False


def run_cmd(args: list[str]) -> int:
    return subprocess.call([sys.executable] + args, cwd=str(ROOT))


def banner() -> None:
    print()
    print("=" * 56)
    print("   星星成长记 · 启动向导")
    print("=" * 56)
    print(f"   工作目录：{ROOT}")
    print(f"   端口：    {PORT}")
    print("=" * 56)


def menu() -> str:
    print()
    print("  1) 本机试用          只有这台电脑能打开")
    print("  2) 手机 / 平板       同一 WiFi 下，手机和平板都能打开")
    print("  3) 重置演示数据      恢复到初始演示状态（会清空现有记录）")
    print("  4) 备份数据          把数据库和规则文件打包保存")
    print("  5) 运行体检          主流程 + 扩展模块 + 教材，共 216 项自检")
    print("  0) 退出")
    print()
    return input("  请输入序号后回车：").strip()


def launch(host: str, open_browser: bool) -> None:
    if port_in_use():
        print(f"\n  端口 {PORT} 已被占用，说明服务很可能已经在运行了。")
        print(f"  直接打开 http://127.0.0.1:{PORT} 即可；")
        print("  如果想重启，先关掉原来的黑窗口。")
        return
    print("\n  正在启动，请稍候…")
    proc = subprocess.Popen(
        [sys.executable, "run.py"] + (["--lan"] if host == "0.0.0.0" else []),
        cwd=str(ROOT))
    if wait_ready():
        if host == "0.0.0.0":
            print(f"\n  ✓ 已启动。请在手机 / 平板浏览器打开：")
            print(f"      http://{lan_ip()}:{PORT}")
            print(f"    电脑本机：http://127.0.0.1:{PORT}")
        else:
            url = f"http://127.0.0.1:{PORT}"
            print(f"\n  ✓ 已启动：{url}")
            if open_browser:
                time.sleep(0.4)
                webbrowser.open(url)
        print("\n  账号：家长 dad / 1234，妈妈 mom / 1234；孩子点头像，口令 1234")
        print("  这个黑窗口不要关，关掉就是停止服务。 Ctrl+C 可以停止。\n")
    else:
        print("  启动超时，请检查上方有无报错信息。")
    try:
        proc.wait()
    except KeyboardInterrupt:
        print("\n  已停止。")


def reset_demo() -> None:
    if port_in_use():
        print("\n  服务正在运行，请先关闭它再重置数据（关掉那个黑窗口）。\n")
        return
    ans = input("\n  这会清空全部现有记录，确认请输入 yes：").strip().lower()
    if ans != "yes":
        print("  已取消。")
        return
    run_cmd(["seed.py", "--reset"])
    print("\n  演示数据已恢复。\n")


def backup() -> None:
    """SQLite 是 WAL 模式，直接复制 .db 会丢掉尚未合并的事务，
    必须用 VACUUM INTO 生成一致性快照。"""
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / stamp
    dest.mkdir(parents=True, exist_ok=True)
    print()

    books = [p for p in (DATA_DIR / "textbooks").glob("*.pdf") if p.is_file()]
    TEXTBOOK_COUNT = len(books)
    TEXTBOOK_MB = round(sum(p.stat().st_size for p in books) / 1048576)

    db = DATA_DIR / "kids.db"
    n = 0
    if db.exists():
        try:
            import sqlite3
            con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
            con.execute("VACUUM INTO ?", (str(dest / "kids.db"),))
            con.close()
            print(f"  ✓ 数据库快照 → backups/{stamp}/kids.db")
            n += 1
        except Exception as e:
            print(f"  ✗ 数据库备份失败：{e}")

    photos = sorted((ROOT / "uploads").glob("*"))
    photos = [p for p in photos if p.is_file()]
    if photos:
        udir = dest / "uploads"
        udir.mkdir(exist_ok=True)
        for p in photos:
            shutil.copy2(p, udir / p.name)
        print(f"  ✓ 佐证照片 {len(photos)} 张 → backups/{stamp}/uploads/")
        n += 1

    cfg = ROOT / "rules.yaml"
    if cfg.exists():
        shutil.copy2(cfg, dest / "rules.yaml")
        print(f"  ✓ 当前规则 → backups/{stamp}/rules.yaml")
        n += 1

    # 教材的索引和页数只有几百 KB，必须跟着备份走；
    # PDF 本体动辄几百 MB，而且随时能重新下载，就不进备份包了。
    for name in ("textbook-catalog.json", "textbook-pages.json"):
        f = DATA_DIR / name
        if f.exists():
            shutil.copy2(f, dest / name)
            print(f"  ✓ 教材{('索引' if 'catalog' in name else '页数')} → backups/{stamp}/{name}")
            n += 1

    if TEXTBOOK_COUNT:
        print(f"  · 教材 PDF {TEXTBOOK_COUNT} 本（约 {TEXTBOOK_MB} MB）未打包，"
              f"换机器时重跑 tools/fetch_textbooks.py 即可")

    print(f"\n  备份完成：backups/{stamp}/  共 {n} 项。\n"
          if n else "\n  没有找到可备份的数据。\n")


def health() -> None:
    if not port_in_use():
        print("\n  服务未运行。请先选 1 或 2 启动服务，再运行体检。\n")
        return
    print()
    # 每套自检前都把演示数据拨回干净状态：
    # 每日上限、每日游戏局数这类约束是按天统计的，同一天连跑两次会互相干扰。
    scripts = ["smoke_test.py", "smoke_test_extra.py", "smoke_test_extra2.py"]
    # 教材那套要读真实 PDF，一本都没下载时先别跑，免得满屏红字吓人
    book_dir = ROOT / "data" / "textbooks"
    if book_dir.exists() and any(book_dir.glob("*.pdf")):
        scripts.append("smoke_test_extra3.py")
    else:
        print("  （教材库还是空的，先跑 tools/fetch_textbooks.py 下载，再回来体检教材功能）")
    for script in scripts:
        run_cmd(["seed.py", "--reset"])
        run_cmd([script])
    print()


def main() -> None:
    banner()
    args = sys.argv[1:]
    if "--lan" in args:
        launch("0.0.0.0", False)
        return
    if "--local" in args:
        launch("127.0.0.1", True)
        return

    while True:
        c = menu()
        if c == "1":
            launch("127.0.0.1", True); return
        if c == "2":
            launch("0.0.0.0", False); return
        if c == "3":
            reset_demo()
        elif c == "4":
            backup()
        elif c == "5":
            health()
        elif c == "0":
            print("  再见。\n"); return
        else:
            print("  没有这个选项，请重新输入。")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n  已退出。")
