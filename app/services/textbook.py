# -*- coding: utf-8 -*-
"""
教材服务：内置目录 + 本地文件 + 后台下载 + 阅读进度。

设计上的一条硬线：**运行时只读本地文件**。

森灵那套是把 GitHub 当文件源，每次打开都走 /proxy 现场拉，缓存没命中就转圈甚至报错。
这里改成「先落到 data/textbooks，再从本地读」——代价是第一次要等下载，
收益是之后孩子在任何时候点开都是瞬开，断网也不影响。

下载这件事本身仍然绕不开 GitHub，所以做了三件事兜底：
多镜像轮换、Range 断点续传、.part 临时文件（半个文件绝不冒充完整教材）。
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import CATALOG_PATH, PAGES_PATH, TEXTBOOK_DIR
from ..db import SessionLocal
from ..models import Family, Textbook, TextbookProgress, User

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) kids-reward/1.0"

# 同一份文件的镜像模板，按实测可靠性排序。
# 说明：tools/ghfetch.py 里还有一份用于抓目录 JSON 的精简列表，
# 那份偏重"小文件走 CDN"，这里偏重"几十 MB 的 PDF 要能续传"，用途不同所以没有合并。
MIRRORS = [
    "https://ghfast.top/https://raw.githubusercontent.com/{repo}/{branch}/{path}",
    "https://gh-proxy.com/https://raw.githubusercontent.com/{repo}/{branch}/{path}",
    "https://ghproxy.net/https://raw.githubusercontent.com/{repo}/{branch}/{path}",
    "https://raw.githubusercontent.com/{repo}/{branch}/{path}",
    "https://cdn.jsdelivr.net/gh/{repo}@{branch}/{path}",   # >20MB 会 403，留作小文件快路
    "https://raw.gitmirror.com/{repo}/{branch}/{path}",
]

CATALOG_CACHE: dict = {"mtime": 0.0, "data": None}

# 正在下载的进度：textbook_id -> {"bytes": int, "total": int}
_LIVE: dict[int, dict] = {}
_LIVE_LOCK = threading.Lock()


# ------------------------------------------------------------------ 目录
def load_catalog() -> dict:
    """读内置目录索引。文件没生成就返回空目录，不报错。"""
    if not CATALOG_PATH.exists():
        return {"repo": "", "branch": "master", "count": 0, "books": []}
    mt = CATALOG_PATH.stat().st_mtime
    if CATALOG_CACHE["data"] is None or mt != CATALOG_CACHE["mtime"]:
        CATALOG_CACHE["data"] = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
        CATALOG_CACHE["mtime"] = mt
    return CATALOG_CACHE["data"]


def catalog_stages() -> list[str]:
    return sorted({b["stage"] for b in load_catalog()["books"]})


def catalog_query(*, stage: str = "", subject: str = "", version: str = "",
                  grade: str = "", q: str = "", limit: int = 200) -> list[dict]:
    """按条件筛内置目录。全部在内存里做，一次几毫秒。"""
    books = load_catalog()["books"]
    if stage:
        books = [b for b in books if b["stage"] == stage]
    if subject:
        books = [b for b in books if b["subject_code"] == subject or b["subject"] == subject]
    if version:
        books = [b for b in books if b["version"] == version]
    if grade:
        books = [b for b in books if b["grade"] == grade]
    if q:
        kw = q.strip().lower()
        books = [b for b in books if kw in b["path"].lower() or kw in b["title"].lower()]
    return books[:limit]


def catalog_versions(stage: str = "", subject: str = "") -> list[str]:
    rows = catalog_query(stage=stage, subject=subject, limit=100000)
    return sorted({b["version"] for b in rows if b["version"]})


_PAGES_CACHE: dict = {"mtime": 0.0, "data": {}}


def load_pages() -> dict:
    """已知教材页数（目录路径 → 页数）。

    由 tools/probe_pages.mjs 在下载后用 pdf.js 实测生成。没有这个文件也不影响运行，
    只是家长布置作业时少一道"页数超了"的校验。
    """
    if not PAGES_PATH.exists():
        return {}
    mt = PAGES_PATH.stat().st_mtime
    if mt != _PAGES_CACHE["mtime"]:
        try:
            _PAGES_CACHE["data"] = json.loads(PAGES_PATH.read_text(encoding="utf-8"))
            _PAGES_CACHE["mtime"] = mt
        except Exception:
            return {}
    return _PAGES_CACHE["data"]


# ------------------------------------------------------------------ 文件
def file_name_for(catalog_path: str) -> str:
    """用路径哈希当文件名。

    中文全名当文件名，在 Windows / Linux 之间搬一次、再被 URL 编码一次，
    十有八九会出乱子。哈希稳定、短、无歧义；原始书名存在 DB 里给家长看。
    """
    return hashlib.sha1(catalog_path.encode("utf-8")).hexdigest()[:16] + ".pdf"


def local_path(file_name: str) -> Path | None:
    if not file_name:
        return None
    p = TEXTBOOK_DIR / file_name
    # 防止 file_name 里混进 ../ 之类的东西
    try:
        p.resolve().relative_to(TEXTBOOK_DIR.resolve())
    except ValueError:
        return None
    return p


def is_ready(tb: Textbook) -> bool:
    p = local_path(tb.file_name)
    return bool(p and p.exists() and p.stat().st_size > 1024)


# ------------------------------------------------------------------ 下载
def _urls(repo: str, branch: str, path: str) -> list[str]:
    q = "/".join(urllib.parse.quote(seg) for seg in path.split("/"))
    return [t.format(repo=repo, branch=branch, path=q) for t in MIRRORS]


def download_to_file(repo: str, branch: str, catalog_path: str, dest: Path,
                     expect_size: int = 0, *, retries: int = 4,
                     on_bytes=None) -> tuple[bool, str]:
    """把一本教材拉到 dest。返回 (是否成功, 说明)。

    带 Range 续传：449MB 下一半断了，重来一次谁都受不了。
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and expect_size and dest.stat().st_size == expect_size:
        return True, "已存在"

    part = dest.with_suffix(".part")
    urls = _urls(repo, branch, catalog_path)
    last_err = ""

    for attempt in range(retries):
        for url in urls:
            have = part.stat().st_size if part.exists() else 0
            if expect_size and have == expect_size:
                break
            headers = {"User-Agent": UA, "Accept": "*/*"}
            if have:
                headers["Range"] = f"bytes={have}-"
            try:
                req = urllib.request.Request(url, headers=headers)
                opener = urllib.request.build_opener(
                    urllib.request.ProxyHandler({}))  # 绕过 Windows 注册表里的代理
                with opener.open(req, timeout=45) as r:
                    mode = "ab" if (have and getattr(r, "status", 200) == 206) else "wb"
                    if mode == "wb":
                        have = 0
                    with open(part, mode) as f:
                        while True:
                            chunk = r.read(256 * 1024)
                            if not chunk:
                                break
                            f.write(chunk)
                            have += len(chunk)
                            if on_bytes:
                                on_bytes(have, expect_size)
                got = part.stat().st_size if part.exists() else 0
                if expect_size and got != expect_size:
                    last_err = f"大小不符 {got}/{expect_size}"
                    continue
                if got < 1024:
                    last_err = "文件太小，可能取到了错误页"
                    part.unlink(missing_ok=True)
                    continue
                os.replace(part, dest)
                return True, f"{got / 1048576:.1f} MB"
            except urllib.error.HTTPError as e:
                last_err = f"HTTP {e.code}"
                if e.code in (403, 404):
                    continue
            except Exception as e:  # noqa: BLE001
                last_err = f"{type(e).__name__}"
        time.sleep(1.2 * (attempt + 1))

    return False, last_err or "未知错误"


def _progress_cb(tb_id: int):
    def cb(done: int, total: int) -> None:
        with _LIVE_LOCK:
            _LIVE[tb_id] = {"bytes": done, "total": total}
    return cb


def live_progress(tb_id: int) -> dict:
    with _LIVE_LOCK:
        return dict(_LIVE.get(tb_id) or {})


def start_download(tb_id: int) -> None:
    """开一个后台线程去下载。接口立刻返回，前端轮询状态。"""
    t = threading.Thread(target=_run_download, args=(tb_id,), daemon=True)
    t.start()


def _run_download(tb_id: int) -> None:
    db: Session = SessionLocal()
    try:
        tb = db.get(Textbook, tb_id)
        if not tb:
            return
        tb.status = "download"
        tb.error_msg = ""
        db.commit()

        repo = load_catalog().get("repo") or "TapXWorld/ChinaTextbook"
        branch = load_catalog().get("branch") or "master"
        catalog_path = tb.catalog_path
        expect = tb.size_bytes or 0

        if not catalog_path:
            # 家长自己填的远程地址：直接按 URL 取，不需要镜像
            ok, info = _download_plain(tb.remote_url, TEXTBOOK_DIR / (tb.file_name or ""),
                                       on_bytes=_progress_cb(tb_id))
        else:
            name = tb.file_name or file_name_for(catalog_path)
            tb.file_name = name
            db.commit()
            ok, info = download_to_file(repo, branch, catalog_path,
                                        TEXTBOOK_DIR / name, expect,
                                        on_bytes=_progress_cb(tb_id))

        tb = db.get(Textbook, tb_id)
        if not tb:
            return
        p = local_path(tb.file_name)
        if ok and p and p.exists():
            tb.status = "ready"
            tb.size_bytes = p.stat().st_size
            tb.error_msg = ""
        else:
            tb.status = "failed"
            tb.error_msg = (info or "下载失败")[:180]
        db.commit()
    except Exception as e:  # noqa: BLE001
        try:
            tb = db.get(Textbook, tb_id)
            if tb:
                tb.status = "failed"
                tb.error_msg = f"{type(e).__name__}: {e}"[:180]
                db.commit()
        except Exception:
            pass
    finally:
        with _LIVE_LOCK:
            _LIVE.pop(tb_id, None)
        db.close()


def _download_plain(url: str, dest: Path, *, on_bytes=None) -> tuple[bool, str]:
    """家长填的任意地址，不用镜像，直连一次。"""
    if not url:
        return False, "地址为空"
    if not dest.name:
        return False, "文件名缺失"
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(req, timeout=60) as r, open(dest, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if on_bytes:
                    on_bytes(done, total)
        if dest.stat().st_size < 1024:
            dest.unlink(missing_ok=True)
            return False, "文件太小，可能不是 PDF"
        return True, f"{dest.stat().st_size / 1048576:.1f} MB"
    except Exception as e:  # noqa: BLE001
        return False, f"取不到这个地址（{type(e).__name__}）"


# ------------------------------------------------------------------ 书架
def sync_catalog_files(db: Session, family: Family) -> int:
    """把已经下载到本地的内置教材，自动挂进这个家庭的书架。

    为什么不在下载时直接建行：下载器是脱离 Web 进程跑的批处理，
    而书架是"谁家的"这种业务概念。这里用「文件在了就补行」的方式对齐，
    既让批处理保持简单，也让家长一打开就能看到刚下好的书。
    """
    cat = load_catalog()
    if not cat.get("books"):
        return 0
    rows = db.scalars(select(Textbook).where(Textbook.family_id == family.id)).all()
    have = {r.file_name for r in rows if r.file_name}
    existing_paths = {r.catalog_path for r in rows if r.catalog_path}

    # 先补历史：早先上架时还不知道页数，现在有了就填上
    pages = load_pages()
    if pages:
        for r in rows:
            if r.catalog_path and not r.page_count and pages.get(r.catalog_path):
                r.page_count = int(pages[r.catalog_path])

    added = 0
    for b in cat["books"]:
        name = file_name_for(b["path"])
        if name in have or b["path"] in existing_paths:
            continue
        p = TEXTBOOK_DIR / name
        if not (p.exists() and p.stat().st_size == b.get("size", 0)):
            continue
        db.add(Textbook(
            family_id=family.id,
            title=b["title"],
            subject=b.get("subject_code", "other"),
            stage=b.get("stage", ""),
            grade=b.get("grade", ""),
            term=b.get("term", ""),
            version=b.get("version", ""),
            source="catalog",
            file_name=name,
            catalog_path=b["path"],
            size_bytes=p.stat().st_size,
            page_count=int(pages.get(b["path"]) or 0),
            status="ready",
        ))
        added += 1
    if added:
        db.commit()
    return added


def page_of(db: Session, child_id: int, textbook_id: int) -> TextbookProgress | None:
    return db.scalar(
        select(TextbookProgress).where(
            TextbookProgress.textbook_id == textbook_id,
            TextbookProgress.child_id == child_id,
        )
    )


def save_progress(db: Session, child: User, tb: Textbook, *, last_page: int,
                  page_count: int = 0, seconds: int = 0) -> TextbookProgress:
    row = page_of(db, child.id, tb.id)
    if not row:
        row = TextbookProgress(family_id=child.family_id, textbook_id=tb.id,
                               child_id=child.id)
        db.add(row)
    row.last_page = max(1, int(last_page or 1))
    if page_count:
        row.page_count = int(page_count)
        if not tb.page_count:
            tb.page_count = int(page_count)
    if seconds:
        row.seconds = (row.seconds or 0) + max(0, int(seconds))
    db.flush()
    return row


# ------------------------------------------------------------------ DTO
SUBJECT_LABEL = {
    "chinese": "语文", "math": "数学", "english": "英语", "science": "科学",
    "morality": "道德与法治", "music": "音乐", "art": "美术", "pe": "体育与健康",
    "calligraphy": "书法", "physics": "物理", "chemistry": "化学", "biology": "生物",
    "history": "历史", "geography": "地理", "politics": "思想政治", "other": "其它",
}

STATUS_LABEL = {
    "ready": "可阅读", "download": "下载中", "failed": "下载失败", "link": "外部链接",
}


def dto(tb: Textbook, prog: TextbookProgress | None = None) -> dict:
    ready = is_ready(tb) or tb.status == "link"
    return {
        "id": tb.id,
        "title": tb.title,
        "subject": tb.subject,
        "subject_name": SUBJECT_LABEL.get(tb.subject, tb.subject or "其它"),
        "stage": tb.stage,
        "grade": tb.grade,
        "term": tb.term,
        "version": tb.version,
        "source": tb.source,
        "status": tb.status,
        "status_name": STATUS_LABEL.get(tb.status, tb.status),
        "error": tb.error_msg,
        "size_mb": round((tb.size_bytes or 0) / 1048576, 1),
        "page_count": tb.page_count or 0,
        "cover": tb.cover,
        "is_current": bool(tb.is_current),
        "note": tb.note,
        "ready": ready,
        "readable": is_ready(tb),
        "url": tb.remote_url if tb.status == "link" else "",
        "file_url": f"/api/textbook/{tb.id}/file" if is_ready(tb) else "",
        "last_page": prog.last_page if prog else 1,
        "seconds": prog.seconds if prog else 0,
        "progress": (round(prog.last_page / (tb.page_count or prog.page_count), 3)
                     if prog and (tb.page_count or prog.page_count) else 0),
        "updated_at": tb.updated_at.strftime("%Y-%m-%d %H:%M") if tb.updated_at else "",
    }
