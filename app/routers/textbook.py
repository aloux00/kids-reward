# -*- coding: utf-8 -*-
"""
教材路由：孩子端（书架 / 阅读进度 / 阅读作业）与家长端（教材库维护 / 布置作业）分开挂。

两条权限约定和项目其它部分保持一致：
- 孩子只能看到自己家的书；
- 家长端的每一个 kid_id 都必须在同一个 family 里，否则 404。
"""
from __future__ import annotations

import datetime as dt
import re
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import TEXTBOOK_DIR
from ..db import get_db
from ..deps import current_user, require_child, require_parent
from ..models import Family, ReadingAssignment, Textbook, TextbookProgress, User
from ..services import PointService, add_audit
from ..services import textbook as svc

# 上传限制：教材 PDF 普遍几十 MB，但要拦住"传个 2GB 视频"这种情况
MAX_PDF_MB = 400

child_router = APIRouter(prefix="/api/child", tags=["textbook"])
parent_router = APIRouter(prefix="/api/parent", tags=["textbook"])
common_router = APIRouter(prefix="/api", tags=["textbook"])


# ------------------------------------------------------------------ 公共工具
def _kid(kid_id: int, parent: User = Depends(require_parent),
         db: Session = Depends(get_db)) -> User:
    kid = db.get(User, kid_id)
    if not kid or kid.family_id != parent.family_id or kid.role != "child":
        raise HTTPException(404, "孩子不存在")
    return kid


def _own(db: Session, user: User, tb_id: int) -> Textbook:
    tb = db.get(Textbook, tb_id)
    if not tb or tb.family_id != user.family_id:
        raise HTTPException(404, "教材不存在")
    return tb


def _shelf(db: Session, family_id: int, *, subject: str = "", q: str = "") -> list[Textbook]:
    stmt = select(Textbook).where(Textbook.family_id == family_id)
    if subject:
        stmt = stmt.where(Textbook.subject == subject)
    rows = db.scalars(
        stmt.order_by(Textbook.is_current.desc(), Textbook.subject,
                      Textbook.grade, Textbook.sort_order, Textbook.id)
    ).all()
    if q:
        kw = q.strip().lower()
        rows = [r for r in rows if kw in r.title.lower() or kw in (r.version or "").lower()]
    return rows


# ------------------------------------------------------------------ 文件服务
@common_router.get("/textbook/{tb_id}/file")
def textbook_file(tb_id: int, request: Request, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    """
    把 PDF 发给浏览器。

    必须支持 Range：pdf.js 会先取头部再按需取片段，
    直接返回整个 40MB 文件在两页一翻的场景下体验很差，手机也吃不住。
    """
    tb = _own(db, user, tb_id)
    if tb.status == "link" and tb.remote_url:
        return Response(status_code=302, headers={"Location": tb.remote_url})

    p = svc.local_path(tb.file_name) if tb.file_name else None
    if not p or not p.exists():
        raise HTTPException(404, "这本书还没下载好")

    size = p.stat().st_size
    range_header = request.headers.get("range") or ""
    m = re.match(r"bytes=(\d*)-(\d*)", range_header)
    if not m:
        return FileResponse(p, media_type="application/pdf",
                            headers={"Accept-Ranges": "bytes",
                                     "Cache-Control": "private, max-age=600"})

    start = int(m.group(1) or 0)
    end = int(m.group(2)) if m.group(2) else size - 1
    end = min(end, size - 1)
    if start > end:
        return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})

    length = end - start + 1
    with open(p, "rb") as f:
        f.seek(start)
        chunk = f.read(length)
    return Response(
        content=chunk,
        status_code=206,
        media_type="application/pdf",
        headers={
            "Content-Range": f"bytes {start}-{end}/{size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
            "Cache-Control": "private, max-age=600",
        },
    )


@common_router.get("/textbook/subjects")
def subject_options():
    return [{"code": k, "name": v} for k, v in svc.SUBJECT_LABEL.items()]


# ------------------------------------------------------------------ 孩子端
@child_router.get("/textbooks")
def child_shelf(user: User = Depends(require_child), db: Session = Depends(get_db)):
    fam = db.get(Family, user.family_id)
    if fam:
        svc.sync_catalog_files(db, fam)
    rows = _shelf(db, user.family_id)
    out = []
    for tb in rows:
        prog = svc.page_of(db, user.id, tb.id)
        out.append(svc.dto(tb, prog))
    groups: dict[str, list] = {}
    for item in out:
        groups.setdefault(item["subject_name"], []).append(item)
    return {
        "books": out,
        "groups": [{"subject": k, "books": v} for k, v in groups.items()],
        "current": [b for b in out if b["is_current"]],
        "total": len(out),
    }


class ProgressIn(BaseModel):
    last_page: int = 1
    page_count: int = 0
    seconds: int = 0


@child_router.put("/textbook/{tb_id}/progress")
def save_progress(tb_id: int, body: ProgressIn, user: User = Depends(require_child),
                  db: Session = Depends(get_db)):
    tb = _own(db, user, tb_id)
    row = svc.save_progress(db, user, tb, last_page=body.last_page,
                            page_count=body.page_count, seconds=body.seconds)
    db.commit()
    return {"ok": True, "last_page": row.last_page, "page_count": row.page_count or tb.page_count}


@child_router.get("/readings")
def child_readings(user: User = Depends(require_child), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(ReadingAssignment)
        .where(ReadingAssignment.child_id == user.id,
               ReadingAssignment.status.in_(["pending", "done"]))
        .order_by(ReadingAssignment.status, ReadingAssignment.due_date, ReadingAssignment.id)
    ).all()
    return {"items": [_reading_dto(db, r) for r in rows]}


class DoneIn(BaseModel):
    evidence_text: str = ""


@child_router.post("/reading/{rid}/done")
def mark_done(rid: int, body: DoneIn, user: User = Depends(require_child),
              db: Session = Depends(get_db)):
    row = db.get(ReadingAssignment, rid)
    if not row or row.child_id != user.id:
        raise HTTPException(404, "作业不存在")
    if row.status != "pending":
        raise HTTPException(400, "这份阅读作业已经交过啦")
    row.status = "done"
    row.done_at = dt.datetime.now()
    row.evidence_text = (body.evidence_text or "").strip()[:200]
    db.commit()
    return {"ok": True, "status": row.status}


def _reading_dto(db: Session, r: ReadingAssignment) -> dict:
    tb = db.get(Textbook, r.textbook_id)
    return {
        "id": r.id,
        "textbook_id": r.textbook_id,
        "title": tb.title if tb else "（教材已删除）",
        "subject_name": svc.SUBJECT_LABEL.get(tb.subject if tb else "", "其它"),
        "grade": tb.grade if tb else "",
        "term": tb.term if tb else "",
        "page_from": r.page_from,
        "page_to": r.page_to,
        "pages": r.page_to - r.page_from + 1,
        "points": r.points,
        "status": r.status,
        "note": r.note,
        "evidence_text": r.evidence_text,
        "due_date": r.due_date,
        "biz_date": r.biz_date,
        "reject_reason": r.reject_reason,
        "awarded": r.awarded,
        "created_at": r.created_at.strftime("%m-%d %H:%M") if r.created_at else "",
        "readable": bool(tb and svc.is_ready(tb)),
    }


# ------------------------------------------------------------------ 家长端：书架
@parent_router.get("/textbooks")
def parent_shelf(subject: str = "", q: str = "",
                 parent: User = Depends(require_parent), db: Session = Depends(get_db)):
    fam = db.get(Family, parent.family_id)
    if fam:
        svc.sync_catalog_files(db, fam)
    rows = _shelf(db, parent.family_id, subject=subject, q=q)
    books = []
    for tb in rows:
        prog = svc.page_of(db, parent.id, tb.id)
        d = svc.dto(tb, prog)
        d.pop("last_page", None)
        d.pop("progress", None)
        d.pop("seconds", None)
        books.append(d)
    used = {b["subject"] for b in books}
    return {
        "books": books,
        "total": len(books),
        "missing_subjects": [k for k, v in svc.SUBJECT_LABEL.items()
                             if k in ("chinese", "math", "english") and k not in used],
    }


def _clean_name(name: str) -> str:
    return re.sub(r"[\\/:*?\"<>|]", "", (name or "").strip())[:60]


class UploadMeta(BaseModel):
    title: str = ""
    subject: str = "other"
    grade: str = ""
    term: str = ""
    version: str = ""


@parent_router.post("/textbooks/upload")
async def upload_textbook(file: UploadFile = File(...),
                          title: str = Form(""), subject: str = Form("other"),
                          grade: str = Form(""), term: str = Form(""),
                          version: str = Form(""),
                          parent: User = Depends(require_parent),
                          db: Session = Depends(get_db)):
    """家长从手机或电脑上传一本 PDF。

    书名/学科这些必须用 Form 声明：这是一次 multipart 上传，
    声明成普通参数的话 FastAPI 会去 query string 里找，前端写在表单里的值就全丢了。
    """
    if (file.content_type or "") not in ("application/pdf", "application/octet-stream"):
        if not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(400, "只支持 PDF 教材")

    name = f"up_{uuid.uuid4().hex[:12]}.pdf"
    dest = TEXTBOOK_DIR / name
    total = 0
    with open(dest, "wb") as f:
        while True:
            chunk = await file.read(1024 * 512)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_PDF_MB * 1024 * 1024:
                f.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(400, f"教材不能超过 {MAX_PDF_MB}MB")
            f.write(chunk)

    if total < 1024:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, "这个文件看起来不是 PDF")

    # 校验 PDF 魔数，避免把改名后的图片塞进来
    with open(dest, "rb") as f:
        if f.read(5)[:4] != b"%PDF":
            f.close()
            dest.unlink(missing_ok=True)
            raise HTTPException(400, "这个文件看起来不是 PDF")

    raw = _clean_name(title) or _clean_name((file.filename or "").rsplit(".", 1)[0]) or "未命名教材"
    tb = Textbook(
        family_id=parent.family_id,
        title=raw,
        subject=subject or "other",
        grade=grade, term=term, version=version or "家长上传",
        source="upload", file_name=name, size_bytes=total, status="ready",
        created_by=parent.id,
    )
    db.add(tb)
    db.commit()
    add_audit(db, parent.family_id, parent.id, "upload_textbook", "textbook", tb.id, raw)
    return {"ok": True, "book": svc.dto(tb)}


class LinkIn(BaseModel):
    url: str
    title: str = ""
    subject: str = "other"
    grade: str = ""
    term: str = ""
    version: str = "远程地址"
    download: bool = True          # False = 只存链接，点开时用新窗口打开


@parent_router.post("/textbooks/link")
def add_by_url(body: LinkIn, parent: User = Depends(require_parent),
               db: Session = Depends(get_db)):
    """远程地址：默认拉回本地（这才是"不依赖外网"的正确姿势），也可以只存链接。"""
    url = (body.url or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        raise HTTPException(400, "请填写以 http:// 或 https:// 开头的地址")

    title = _clean_name(body.title) or url.rsplit("/", 1)[-1][:60] or "未命名教材"
    name = f"url_{uuid.uuid4().hex[:12]}.pdf"
    tb = Textbook(
        family_id=parent.family_id,
        title=title,
        subject=body.subject or "other",
        grade=body.grade, term=body.term, version=body.version or "远程地址",
        source="url",
        file_name="" if not body.download else name,
        remote_url=url,
        status="download" if body.download else "link",
        created_by=parent.id,
    )
    db.add(tb)
    db.commit()
    if body.download:
        svc.start_download(tb.id)
    return {"ok": True, "book": svc.dto(tb)}


class BookPatch(BaseModel):
    title: str | None = None
    subject: str | None = None
    grade: str | None = None
    term: str | None = None
    version: str | None = None
    note: str | None = None
    is_current: bool | None = None


@parent_router.patch("/textbook/{tb_id}")
def patch_book(tb_id: int, body: BookPatch, parent: User = Depends(require_parent),
               db: Session = Depends(get_db)):
    tb = _own(db, parent, tb_id)
    if body.title is not None:
        tb.title = _clean_name(body.title) or tb.title
    for f in ("subject", "grade", "term", "version"):
        v = getattr(body, f)
        if v is not None:
            setattr(tb, f, v[:20])
    if body.note is not None:
        tb.note = body.note.strip()[:120]
    if body.is_current is not None:
        if body.is_current:
            # 同一学科只留一本"当前在用"，否则孩子端不知道该翻哪本
            for other in db.scalars(
                select(Textbook).where(Textbook.family_id == parent.family_id,
                                       Textbook.subject == tb.subject)
            ).all():
                other.is_current = False
        tb.is_current = body.is_current
    db.commit()
    return {"ok": True, "book": svc.dto(tb)}


@parent_router.delete("/textbook/{tb_id}")
def delete_book(tb_id: int, parent: User = Depends(require_parent),
                db: Session = Depends(get_db)):
    tb = _own(db, parent, tb_id)
    used = db.scalar(
        select(ReadingAssignment.id).where(ReadingAssignment.textbook_id == tb.id).limit(1))
    if used:
        raise HTTPException(400, "这本书上还挂着阅读作业，先删作业再删书")
    # 外键是打开的，进度行必须先走，否则删书会撞 foreign key 约束
    db.execute(delete(TextbookProgress).where(TextbookProgress.textbook_id == tb.id))
    if tb.file_name:
        p = svc.local_path(tb.file_name)
        if p and p.exists():
            p.unlink(missing_ok=True)
    add_audit(db, parent.family_id, parent.id, "delete_textbook", "textbook", tb.id, tb.title)
    db.delete(tb)
    db.commit()
    return {"ok": True}


@parent_router.post("/textbook/{tb_id}/retry")
def retry_download(tb_id: int, parent: User = Depends(require_parent),
                   db: Session = Depends(get_db)):
    tb = _own(db, parent, tb_id)
    if tb.status == "ready":
        return {"ok": True, "status": "ready"}
    if not tb.file_name and tb.source == "url":
        tb.file_name = f"url_{uuid.uuid4().hex[:12]}.pdf"
    if not tb.file_name and tb.catalog_path:
        tb.file_name = svc.file_name_for(tb.catalog_path)
    tb.status = "download"
    tb.error_msg = ""
    db.commit()
    svc.start_download(tb.id)
    return {"ok": True, "status": "download"}


@parent_router.get("/textbook/{tb_id}/status")
def download_status(tb_id: int, parent: User = Depends(require_parent),
                    db: Session = Depends(get_db)):
    tb = _own(db, parent, tb_id)
    live = svc.live_progress(tb.id)
    done = live.get("bytes", 0)
    total = live.get("total") or tb.size_bytes or 0
    return {
        "status": tb.status,
        "error": tb.error_msg,
        "bytes": done,
        "total": total,
        "percent": round(done / total * 100, 1) if total else 0,
    }


# ------------------------------------------------------------------ 家长端：内置目录
@parent_router.get("/textbooks/catalog")
def browse_catalog(stage: str = "", subject: str = "", version: str = "",
                   grade: str = "", q: str = "", limit: int = Query(120, le=400),
                   parent: User = Depends(require_parent), db: Session = Depends(get_db)):
    """浏览内置的 ChinaTextbook 索引（纯本地 JSON，不联网）。"""
    cat = svc.load_catalog()
    rows = svc.catalog_query(stage=stage, subject=subject, version=version,
                             grade=grade, q=q, limit=limit)
    mine = {r.catalog_path: r for r in db.scalars(
        select(Textbook).where(Textbook.family_id == parent.family_id,
                               Textbook.catalog_path != "")).all()}

    out = []
    for b in rows:
        have = mine.get(b["path"])
        out.append({
            "path": b["path"],
            "title": b["title"],
            "stage": b["stage"],
            "subject": b["subject"],
            "subject_code": b["subject_code"],
            "subject_name": svc.SUBJECT_LABEL.get(b["subject_code"], b["subject"]),
            "version": b["version"],
            "grade": b["grade"],
            "term": b["term"],
            "size_mb": round(b["size"] / 1048576, 1),
            "added": bool(have),
            "textbook_id": have.id if have else 0,
            "status": have.status if have else "",
        })
    return {
        "repo": cat.get("repo", ""),
        "built_at": cat.get("built_at", ""),
        "count": len(out),
        "total_available": cat.get("count", 0),
        "stages": svc.catalog_stages(),
        "versions": svc.catalog_versions(stage=stage, subject=subject),
        "books": out,
        "local_count": sum(1 for b in cat.get("books", [])
                           if (TEXTBOOK_DIR / svc.file_name_for(b["path"])).exists()),
    }


class FetchIn(BaseModel):
    paths: list[str]


@parent_router.post("/textbooks/fetch")
def fetch_from_catalog(body: FetchIn, parent: User = Depends(require_parent),
                       db: Session = Depends(get_db)):
    """
    把内置目录里的若干本加入书架并开始下载。

    已下载过（文件在本地）的直接就绪，不重复下载；
    这几百 MB 的东西没必要为了"确保最新"再拉一遍。
    """
    cat = {b["path"]: b for b in svc.load_catalog()["books"]}
    pages = svc.load_pages()
    added, started = [], []
    for path in (body.paths or [])[:60]:
        b = cat.get(path)
        if not b:
            continue
        name = svc.file_name_for(path)
        exist = db.scalar(
            select(Textbook).where(Textbook.family_id == parent.family_id,
                                   Textbook.catalog_path == path))
        if exist:
            if exist.status in ("failed", "download") and not svc.is_ready(exist):
                svc.start_download(exist.id)
                started.append(exist.id)
            continue

        p = TEXTBOOK_DIR / name
        ready = p.exists() and p.stat().st_size == b.get("size", 0)
        tb = Textbook(
            family_id=parent.family_id,
            title=b["title"],
            subject=b.get("subject_code", "other"),
            stage=b.get("stage", ""),
            grade=b.get("grade", ""),
            term=b.get("term", ""),
            version=b.get("version", ""),
            source="catalog",
            file_name=name,
            catalog_path=path,
            size_bytes=b.get("size", 0) if not ready else p.stat().st_size,
            page_count=int(pages.get(path) or 0),
            status="ready" if ready else "download",
        )
        db.add(tb)
        db.flush()
        added.append(tb.id)
        if not ready:
            started.append(tb.id)
    db.commit()
    for tid in started:
        svc.start_download(tid)
    return {"ok": True, "added": len(added), "downloading": len(started),
            "ids": added}


# ------------------------------------------------------------------ 家长端：阅读作业
class ReadingIn(BaseModel):
    kid_id: int
    textbook_id: int
    page_from: int = 1
    page_to: int = 1
    points: int = 5
    due_date: str = ""
    note: str = ""


@parent_router.get("/readings")
def parent_readings(kid_id: int = 0, parent: User = Depends(require_parent),
                    db: Session = Depends(get_db)):
    stmt = select(ReadingAssignment).where(ReadingAssignment.family_id == parent.family_id)
    if kid_id:
        stmt = stmt.where(ReadingAssignment.child_id == kid_id)
    rows = db.scalars(stmt.order_by(ReadingAssignment.id.desc()).limit(100)).all()
    return {"items": [_reading_dto(db, r) for r in rows]}


@parent_router.post("/reading")
def create_reading(body: ReadingIn, parent: User = Depends(require_parent),
                   db: Session = Depends(get_db)):
    kid = _kid(body.kid_id, parent, db)
    tb = _own(db, parent, body.textbook_id)
    if not svc.is_ready(tb):
        raise HTTPException(400, "这本教材还没下载好，等它下完再布置")

    a = max(1, int(body.page_from or 1))
    b = max(a, int(body.page_to or a))
    if tb.page_count and b > tb.page_count:
        raise HTTPException(400, f"这本书只有 {tb.page_count} 页")
    if b - a + 1 > 60:
        raise HTTPException(400, "一次最多布置 60 页，分几次更合适")

    row = ReadingAssignment(
        family_id=parent.family_id,
        child_id=kid.id,
        textbook_id=tb.id,
        page_from=a,
        page_to=b,
        points=max(0, min(int(body.points or 5), 50)),
        biz_date=dt.date.today().isoformat(),
        due_date=(body.due_date or "")[:10],
        note=(body.note or "").strip()[:120],
        created_by=parent.id,
    )
    db.add(row)
    db.commit()
    add_audit(db, parent.family_id, parent.id, "create_reading", "reading", row.id,
              f"{tb.title} 第 {a}-{b} 页")
    return {"ok": True, "reading": _reading_dto(db, row)}


class ReviewReadingIn(BaseModel):
    id: int
    action: str = "approve"          # approve / reject
    points: int | None = None
    reason: str = ""


@parent_router.post("/reading/review")
def review_reading(body: ReviewReadingIn, parent: User = Depends(require_parent),
                   db: Session = Depends(get_db)):
    """
    确认孩子读完了。

    加分严格走 PointService，所以自动受 daily_cap.study 约束 ——
    家长就算想多给，也超不过当天这一类目的上限，账本里也留痕。
    """
    row = db.get(ReadingAssignment, body.id)
    if not row or row.family_id != parent.family_id:
        raise HTTPException(404, "作业不存在")
    if row.status not in ("done", "pending"):
        raise HTTPException(400, "这份作业已经处理过了")

    kid = db.get(User, row.child_id)
    if not kid:
        raise HTTPException(404, "孩子不存在")

    if body.action == "reject":
        row.status = "rejected"
        row.reject_reason = (body.reason or "").strip()[:80] or "这次先不算，下次再来"
        row.reviewer_id = parent.id
        row.reviewed_at = dt.datetime.now()
        add_audit(db, parent.family_id, parent.id, "reject_reading", "reading", row.id,
                  row.reject_reason)
        db.commit()
        return {"ok": True, "awarded": 0}

    pts = max(0, int(body.points if body.points is not None else row.points))
    ps = PointService(db)
    res = ps.grant(
        kid, pts,
        source_type="reading",
        category="study",
        source_id=row.id,
        note=f"读完教材第 {row.page_from}-{row.page_to} 页",
        operator_id=parent.id,
        biz_date=row.biz_date or dt.date.today().isoformat(),
    )
    row.status = "approved"
    row.awarded = res["granted"]
    row.reviewer_id = parent.id
    row.reviewed_at = dt.datetime.now()
    if res["granted"] > 0:
        ps.update_streak(kid, row.biz_date or dt.date.today().isoformat())
        ps.check_achievements(kid)
    add_audit(db, parent.family_id, parent.id, "approve_reading", "reading", row.id,
              f"+{res['granted']}")
    db.commit()
    return {
        "ok": True,
        "awarded": res["granted"],
        "capped": res["capped"],
        "note": "今天学习类星星币已经到上限啦" if res["capped"] else "",
    }


@parent_router.delete("/reading/{rid}")
def delete_reading(rid: int, parent: User = Depends(require_parent),
                   db: Session = Depends(get_db)):
    row = db.get(ReadingAssignment, rid)
    if not row or row.family_id != parent.family_id:
        raise HTTPException(404, "作业不存在")
    db.delete(row)
    db.commit()
    return {"ok": True}
