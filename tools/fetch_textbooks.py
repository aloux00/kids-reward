# -*- coding: utf-8 -*-
"""
按索引批量下载教材到 data/textbooks/，落盘即完成，App 运行时不再碰 GitHub。

    python tools/fetch_textbooks.py --preset primary-ym     # 小学1-6年级 语文统编+数学人教
    python tools/fetch_textbooks.py --subject math --grade 一年级
    python tools/fetch_textbooks.py --path "小学/语文/统编版/义务教育教科书·语文一年级上册.pdf"
    python tools/fetch_textbooks.py --preset primary-ym --dry-run   # 只报体积不下载

下载内核直接用 app/services/textbook.py 里那一份 —— 断点续传、多镜像轮换、
.part 临时文件这些细节只该有一个实现，否则 App 里点的下载和这里跑的脚本
迟早会走出两套行为。
"""
from __future__ import annotations

import argparse
import concurrent.futures as futures
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.services import textbook as svc  # noqa: E402

DEST = ROOT / "data" / "textbooks"

_print_lock = threading.Lock()


def say(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


def pick(cat: dict, args) -> list[dict]:
    books = cat["books"]
    if args.path:
        books = [b for b in books if b["path"] == args.path]
    if args.preset == "primary-ym":
        # 小学 1-6 年级，统编版语文 + 人教版数学，上下册
        books = [
            b for b in books
            if b["stage"] == "小学"
            and ((b["subject"] == "语文" and b["version"] == "统编版")
                 or (b["subject"] == "数学" and b["version"] == "人教版"))
        ]
    if args.subject:
        books = [b for b in books if b["subject_code"] == args.subject or b["subject"] == args.subject]
    if args.grade:
        books = [b for b in books if b["grade"] == args.grade]
    if args.stage:
        books = [b for b in books if b["stage"] == args.stage]
    return books


def one(book: dict, repo: str, branch: str) -> tuple[str, bool, str]:
    path = book["path"]
    dest = DEST / svc.file_name_for(path)
    ok, info = svc.download_to_file(repo, branch, path, dest, int(book.get("size") or 0))
    return path, ok, info


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preset", default="")
    ap.add_argument("--subject", default="")
    ap.add_argument("--grade", default="")
    ap.add_argument("--stage", default="")
    ap.add_argument("--path", default="")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cat = svc.load_catalog()
    if not cat.get("books"):
        raise SystemExit("索引不存在，先跑 tools/build_textbook_catalog.py")
    repo = cat.get("repo") or "TapXWorld/ChinaTextbook"
    branch = cat.get("branch") or "master"

    books = pick(cat, args)
    if not books:
        raise SystemExit("没有匹配到教材，检查筛选条件")

    total = sum(int(b.get("size") or 0) for b in books)
    say(f"选中 {len(books)} 本，共 {total / 1048576:.0f} MB")
    if args.dry_run:
        for b in books:
            say(f"  {b.get('size', 0) / 1048576:6.1f} MB  {b['path']}")
        return

    DEST.mkdir(parents=True, exist_ok=True)

    ok, fail = 0, []
    t0 = time.time()
    with futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        tasks = [pool.submit(one, b, repo, branch) for b in books]
        for i, fut in enumerate(futures.as_completed(tasks), 1):
            path, good, info = fut.result()
            if good:
                ok += 1
                say(f"[{i}/{len(books)}] ✅ {info:>10}  {path.split('/')[-1]}")
            else:
                fail.append(path)
                say(f"[{i}/{len(books)}] ❌ {info:>10}  {path.split('/')[-1]}")

    cost = time.time() - t0
    say(f"\n完成 {ok}/{len(books)}，用时 {cost / 60:.1f} 分钟 → {DEST}")
    if fail:
        say("失败清单（重跑同一条命令会自动续传）：")
        for p in fail:
            say("  " + p)
        sys.exit(1)


if __name__ == "__main__":
    main()
