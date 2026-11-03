# -*- coding: utf-8 -*-
"""
错题本路由：学科维护、筛选排序、编辑移动、分科汇总、打印与 Word 导出。

孩子端只做「改自己的题」，删除和科目维护归家长 ——
孩子一键删掉自己不会的题，错题本就失去意义了。
"""
from __future__ import annotations

import urllib.parse

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import save_wrong_subjects, wrong_subjects
from ..db import get_db
from ..deps import require_child, require_parent
from ..models import User, WrongQuestion
from ..services import wrong as WS
from ..services.docx_export import build_docx


def _kid(kid_id: int, parent: User = Depends(require_parent),
         db: Session = Depends(get_db)) -> User:
    """孩子校验：家长只能动自己家里的孩子，且对象必须是 child 角色。

    本项目家长端统一用 kid_id 作为查询参数，所以这里直接用同名参数，
    不复用 deps.child_in_family（它读的是 child_id）。
    """
    kid = db.get(User, kid_id)
    if not kid or kid.family_id != parent.family_id or kid.role != "child":
        raise HTTPException(404, "孩子不存在")
    return kid

child_router = APIRouter(prefix="/api/child", tags=["wrong-child"])
parent_router = APIRouter(prefix="/api/parent", tags=["wrong-parent"])


def _bad(fn, code: int = 400):
    """把业务层的 ValueError 转成 400，别让异常裸奔成 500。"""
    try:
        return fn()
    except ValueError as e:
        raise HTTPException(code, str(e))
    except RuntimeError as e:
        raise HTTPException(code, str(e))


class SubjectIn(BaseModel):
    subjects: list


class WrongEditIn(BaseModel):
    question: str | None = None
    correct_answer: str | None = None
    wrong_answer: str | None = None
    explain: str | None = None
    subject: str | None = None
    cause: str | None = None     # 错因：家长看过之后填，才知道问题出在哪
    tag: str | None = None       # 知识点，如「进位加法」


# ================================================================ 孩子端
@child_router.get("/wrong/subjects")
def child_subjects(user: User = Depends(require_child)):
    return {"subjects": WS.subjects()}


@child_router.patch("/wrong/{wid}")
def child_edit(wid: int, body: WrongEditIn,
               user: User = Depends(require_child),
               db: Session = Depends(get_db)):
    fields = body.model_dump(exclude_none=True)
    row = _bad(lambda: WS.update_item(db, user, wid, fields))
    db.commit()
    return {"ok": True, "item": WS.dto(row)}


@child_router.post("/wrong/{wid}/move")
def child_move(wid: int, direction: str = Query("up", pattern="^(up|down)$"),
               user: User = Depends(require_child),
               db: Session = Depends(get_db)):
    order = _bad(lambda: WS.move_item(db, user, wid, direction))
    db.commit()
    return {"ok": True, "order": order}


@child_router.post("/wrong/renumber")
def child_renumber(user: User = Depends(require_child),
                   db: Session = Depends(get_db)):
    WS.renumber(db, user)
    db.commit()
    return {"ok": True}


@child_router.post("/wrong/reset-order")
def child_reset_order(user: User = Depends(require_child),
                      db: Session = Depends(get_db)):
    WS.reset_order(db, user)
    db.commit()
    return {"ok": True}


# ================================================================ 家长端 · 科目
@parent_router.get("/wrong/subjects")
def list_subjects(_p: User = Depends(require_parent)):
    rows = wrong_subjects()
    return {"subjects": rows, "codes": [r["code"] for r in rows]}


@parent_router.put("/wrong/subjects")
def update_subjects(body: SubjectIn, parent: User = Depends(require_parent),
                    db: Session = Depends(get_db)):
    rows = _bad(lambda: save_wrong_subjects(body.subjects))
    db.commit()
    return {"ok": True, "subjects": rows}


# ================================================================ 家长端 · 列表与编辑
@parent_router.get("/wrong/list")
def parent_list(
    kid_id: int,
    subject: str | None = None,
    status: str = Query("pending", pattern="^(pending|mastered|all)$"),
    order: str = Query("manual", pattern="^(recent|times|oldest|manual)$"),
    kid: User = Depends(_kid),
    db: Session = Depends(get_db),
):
    mastered = None if status == "all" else (status == "mastered")
    rows = WS.list_wrong(db, kid, mastered=mastered, subject=subject, order=order)
    return {
        "child": {"id": kid.id, "name": kid.name, "avatar": kid.avatar},
        "subjects": WS.subjects(),
        "items": [WS.dto(r) for r in rows],
        "total": len(rows),
        "pending": sum(1 for r in rows if not r.mastered),
    }


@parent_router.patch("/wrong/{wid}")
def parent_edit(wid: int, body: WrongEditIn,
                parent: User = Depends(require_parent),
                db: Session = Depends(get_db)):
    row = db.get(WrongQuestion, wid)
    if not row or row.family_id != parent.family_id:
        raise HTTPException(404, "没有找到这道题")
    kid = db.get(User, row.child_id)
    fields = body.model_dump(exclude_none=True)
    updated = _bad(lambda: WS.update_item(db, kid, wid, fields))
    db.commit()
    return {"ok": True, "item": WS.dto(updated)}


@parent_router.delete("/wrong/{wid}")
def parent_delete(wid: int, parent: User = Depends(require_parent),
                  db: Session = Depends(get_db)):
    row = db.get(WrongQuestion, wid)
    if not row or row.family_id != parent.family_id:
        raise HTTPException(404, "没有找到这道题")
    db.delete(row)
    db.commit()
    return {"ok": True, "id": wid}


@parent_router.post("/wrong/{wid}/move")
def parent_move(wid: int, direction: str = Query("up", pattern="^(up|down)$"),
                parent: User = Depends(require_parent),
                db: Session = Depends(get_db)):
    row = db.get(WrongQuestion, wid)
    if not row or row.family_id != parent.family_id:
        raise HTTPException(404, "没有找到这道题")
    kid = db.get(User, row.child_id)
    order = _bad(lambda: WS.move_item(db, kid, wid, direction))
    db.commit()
    return {"ok": True, "order": order}


@parent_router.post("/kid/{kid_id}/wrong/renumber")
def renumber(kid_id: int, kid: User = Depends(_kid),
             _p: User = Depends(require_parent),
             db: Session = Depends(get_db)):
    """把当前的默认顺序固化成手动顺序，之后用上下箭头微调最省事。"""
    WS.renumber(db, kid)
    db.commit()
    return {"ok": True}


@parent_router.post("/kid/{kid_id}/wrong/reset-order")
def reset_order(kid_id: int, kid: User = Depends(_kid),
                _p: User = Depends(require_parent),
                db: Session = Depends(get_db)):
    WS.reset_order(db, kid)
    db.commit()
    return {"ok": True}


# ================================================================ 家长端 · 汇总与导出
def _summary_payload(db: Session, kid: User, subject: str | None, status: str,
                     ids: list[int] | None, days: int | None) -> dict:
    return WS.summary(db, kid, subject=subject, status=status, ids=ids, days=days)


@parent_router.get("/wrong/summary")
def wrong_summary(
    kid_id: int,
    subject: str | None = None,
    status: str = Query("pending", pattern="^(pending|mastered|all)$"),
    ids: str | None = None,
    days: int | None = None,
    variants: int = 0,
    kid: User = Depends(_kid),
    parent: User = Depends(require_parent),
    db: Session = Depends(get_db),
):
    """分科目汇总。打印和导出 Word 共用这一份数据，保证屏幕与纸面一致。"""
    wanted = None
    if ids:
        wanted = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    payload = _summary_payload(db, kid, subject, status, wanted, days)
    if variants:
        for g in payload["groups"]:
            for it in g["items"]:
                row = db.get(WrongQuestion, it["id"])
                it["variants"] = WS.variants(row) if row else []

    kids = db.scalars(
        select(User).where(
            User.family_id == parent.family_id,
            User.role == "child",
            User.active.is_(True),
        )
    ).all()
    payload["kids"] = [{"id": k.id, "name": k.name, "avatar": k.avatar} for k in kids]
    payload["subjects"] = WS.subjects()
    payload["filter"] = {
        "kid_id": kid.id, "subject": subject or "", "status": status,
        "days": days or 0, "ids": wanted or [],
    }
    return payload


@parent_router.get("/wrong/stats")
def wrong_stats(kid_id: int, days: int = 30,
                kid: User = Depends(_kid),
                _p: User = Depends(require_parent),
                db: Session = Depends(get_db)):
    """学情统计：掌握率、分科分布、错因分布、最近趋势。"""
    return WS.stats(db, kid, days=days)


@parent_router.get("/wrong/export")
def wrong_export(
    kid_id: int,
    subject: str | None = None,
    status: str = Query("pending", pattern="^(pending|mastered|all)$"),
    ids: str | None = None,
    days: int | None = None,
    answers: int = 1,
    variants: int = 0,
    kid: User = Depends(_kid),
    _p: User = Depends(require_parent),
    db: Session = Depends(get_db),
):
    wanted = None
    if ids:
        wanted = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    payload = _summary_payload(db, kid, subject, status, wanted, days)

    if variants:
        for g in payload["groups"]:
            for it in g["items"]:
                row = db.get(WrongQuestion, it["id"])
                it["variants"] = WS.variants(row) if row else []

    from datetime import date

    today = payload.get("generated_at") or date.today().isoformat()
    fname = f"{payload['child']['name']}错题重做_{today}.docx"
    quoted = urllib.parse.quote(fname)
    data = build_docx(payload, with_answers=bool(answers), with_variants=bool(variants))
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument."
                   "wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quoted}",
            "Cache-Control": "no-store",
        },
    )
