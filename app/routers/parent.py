# -*- coding: utf-8 -*-
"""
家长端。多名家长共享同一个家庭，谁审批都可以，所有动作都写审计日志。
所有越权判断在这里做：孩子必须属于同一个 family_id。
"""
from __future__ import annotations

import datetime as dt
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import load_rules, rules_structured, rules_text, save_rules_structured, save_rules_text, today_str
from ..db import get_db
from ..deps import require_parent
from ..models import (
    PointApplication,
    PointLedger,
    Redemption,
    TaskRecord,
    TaskTemplate,
    User,
    Wish,
)
from ..security import hash_pin
from ..serializers import kid_brief, ledger_rows, pending_dto
from ..services import PointService, add_audit, expire_applications
from ..services.level import level_info

router = APIRouter(prefix="/api/parent", tags=["parent"])


def _kid(db: Session, parent: User, kid_id: int) -> User:
    kid = db.get(User, kid_id)
    if not kid or kid.family_id != parent.family_id or kid.role != "child":
        raise HTTPException(404, "孩子不存在")
    return kid


# ------------------------------------------------------------------ 概览
@router.get("/overview")
def overview(parent: User = Depends(require_parent), db: Session = Depends(get_db)):
    ps = PointService(db)
    kids = db.scalars(
        select(User).where(
            User.family_id == parent.family_id,
            User.role == "child",
            User.active.is_(True),
        )
    ).all()

    pending = pending_dto(db, parent.family_id)
    task_pending = sum(1 for p in pending if p["kind"] == "task")
    apply_pending = sum(1 for p in pending if p["kind"] == "apply")
    redeem_pending = sum(1 for p in pending if p["kind"] == "redeem")

    return {
        "parent": {"id": parent.id, "name": parent.name, "role": parent.role},
        "counts": {
            "task": task_pending,
            "apply": apply_pending,
            "redeem": redeem_pending,
            "total": len(pending),
        },
        "kids": [kid_brief(db, k, ps) for k in kids],
    }


@router.get("/pending")
def pending_list(parent: User = Depends(require_parent), db: Session = Depends(get_db)):
    # 顺手把超期的申请作废，避免待办列表被几个月的旧申请堆满
    expire_applications(db, family_id=parent.family_id)
    return {"items": pending_dto(db, parent.family_id)}


# ------------------------------------------------------------------ 审批
class ReviewIn(BaseModel):
    id: int
    action: str                 # approve / reject
    points: int | None = None
    reason: str = ""


@router.post("/review/task")
def review_task(body: ReviewIn, parent: User = Depends(require_parent),
                db: Session = Depends(get_db)):
    ps = PointService(db)
    rec = db.get(TaskRecord, body.id)
    if not rec or rec.family_id != parent.family_id or rec.status != "pending":
        raise HTTPException(404, "记录不存在或已处理")

    kid = _kid(db, parent, rec.child_id)
    tpl = db.get(TaskTemplate, rec.template_id)

    if body.action == "reject":
        rec.status = "rejected"
        rec.reviewer_id = parent.id
        rec.reviewed_at = dt.datetime.now()
        rec.reject_reason = (body.reason or "").strip()[:80] or "这次先不算，下次加油"
        add_audit(db, parent.family_id, parent.id, "reject_task", "task_record", rec.id,
                  rec.reject_reason)
        db.commit()
        return {"ok": True, "awarded": 0}

    points = body.points if body.points is not None else (tpl.points if tpl else 0)
    points = max(0, int(points))
    res = ps.grant(
        kid,
        points,
        source_type="task",
        category=tpl.category if tpl else "habit",
        source_id=rec.id,
        note=tpl.name if tpl else "任务",
        operator_id=parent.id,
        biz_date=rec.biz_date,
    )
    rec.status = "approved"
    rec.awarded_coin = res["granted"]
    rec.reviewer_id = parent.id
    rec.reviewed_at = dt.datetime.now()

    if res["granted"] > 0:
        ps.update_streak(kid, rec.biz_date)
        ps.check_achievements(kid)
    add_audit(db, parent.family_id, parent.id, "approve_task", "task_record", rec.id,
              f"{tpl.name if tpl else ''} +{res['granted']}")
    db.commit()
    return {
        "ok": True,
        "awarded": res["granted"],
        "capped": res["capped"],
        "note": "今天这类星星币已经到上限啦" if res["capped"] else "",
    }


@router.post("/review/apply")
def review_apply(body: ReviewIn, parent: User = Depends(require_parent),
                 db: Session = Depends(get_db)):
    """
    审批加分申请。家长只能下修，不能突破单次上限 —— 申请本身就是完整的防通胀通道。
    """
    rules = load_rules()
    cfg = rules.get("application") or {}
    ps = PointService(db)

    app = db.get(PointApplication, body.id)
    if not app or app.family_id != parent.family_id or app.status != "pending":
        raise HTTPException(404, "申请不存在或已处理")

    kid = _kid(db, parent, app.child_id)

    if body.action == "reject":
        if not (body.reason or "").strip():
            raise HTTPException(400, "驳回请写一句理由，孩子需要知道为什么")
        app.status = "rejected"
        app.reject_reason = body.reason[:80]
        app.reviewer_id = parent.id
        app.reviewed_at = dt.datetime.now()
        add_audit(db, parent.family_id, parent.id, "reject_apply", "point_application",
                  app.id, app.reject_reason)
        db.commit()
        return {"ok": True, "awarded": 0}

    max_points = min(int(cfg.get("max_points_per_apply", 10)), app.points)
    want = body.points if body.points is not None else app.points
    points = max(1, min(int(want), max_points))

    # 关掉这个开关等于给申请开后门：孩子可以绕开每日上限不断申报。
    # 默认值与文案都建议保持开启，这里按配置决定是否计入额度。
    into_cap = bool(cfg.get("count_into_daily_cap", True))

    res = ps.grant(
        kid,
        points,
        source_type="application",
        category=app.category,
        source_id=app.id,
        note=app.title,
        operator_id=parent.id,
        biz_date=app.biz_date,
        apply_cap=into_cap,
    )
    app.status = "approved"
    app.awarded_coin = res["granted"]
    app.reviewer_id = parent.id
    app.reviewed_at = dt.datetime.now()
    if res["granted"] > 0:
        ps.update_streak(kid, app.biz_date)
        ps.check_achievements(kid)
    db.commit()
    return {"ok": True, "awarded": res["granted"], "capped": res["capped"]}


@router.post("/review/redeem")
def review_redeem(body: ReviewIn, parent: User = Depends(require_parent),
                  db: Session = Depends(get_db)):
    """兑换核销：只有 fulfilled 的这一刻才真正扣星，之前是冻结状态。"""
    ps = PointService(db)
    rdm = db.get(Redemption, body.id)
    if not rdm or rdm.family_id != parent.family_id or rdm.status != "pending":
        raise HTTPException(404, "兑换申请不存在或已处理")

    kid = _kid(db, parent, rdm.child_id)
    wish = db.get(Wish, rdm.wish_id)

    if body.action == "reject":
        rdm.status = "cancelled"
        rdm.handled_by = parent.id
        rdm.handled_at = dt.datetime.now()
        add_audit(db, parent.family_id, parent.id, "cancel_redeem", "redemption", rdm.id,
                  body.reason[:80])
        db.commit()
        return {"ok": True, "mode": "cancelled"}

    available = ps.available_coin(kid.id)
    if available + rdm.cost_coin < rdm.cost_coin:
        raise HTTPException(400, "余额不足")

    ps.spend(kid, rdm.cost_coin, source_id=rdm.id,
             note=wish.title if wish else "兑换", operator_id=parent.id)
    rdm.status = "fulfilled"
    rdm.handled_by = parent.id
    rdm.handled_at = dt.datetime.now()
    if wish:
        wish.status = "completed"
        wish.completed_at = dt.datetime.now()
    add_audit(db, parent.family_id, parent.id, "fulfill_redeem", "redemption", rdm.id,
              wish.title if wish else "")
    db.commit()
    return {"ok": True, "mode": "fulfilled"}


# ------------------------------------------------------------------ 任务 CRUD
class TaskIn(BaseModel):
    name: str
    category: str = "study"
    points: int = 5
    icon: str = "✅"
    repeat_type: str = "daily"          # daily / weekly / none
    repeat_rule: list = []              # weekly 时为周几 [1..7]
    assignee_ids: list = []
    display_zone: str = "today"         # today / extra
    need_approval: bool = True
    need_photo: bool = False
    effective_from: str | None = None
    effective_to: str | None = None


@router.get("/tasks")
def list_tasks(parent: User = Depends(require_parent), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(TaskTemplate)
        .where(TaskTemplate.family_id == parent.family_id)
        .order_by(TaskTemplate.active.desc(), TaskTemplate.id.desc())
    ).all()
    kids = db.scalars(
        select(User).where(User.family_id == parent.family_id, User.role == "child")
    ).all()
    kname = {k.id: k.name for k in kids}
    return {
        "tasks": [
            {
                "id": t.id,
                "name": t.name,
                "category": t.category,
                "points": t.points,
                "icon": t.icon,
                "repeat_type": t.repeat_type,
                "repeat_rule": json.loads(t.repeat_rule or "[]"),
                "display_zone": t.display_zone,
                "need_approval": t.need_approval,
                "need_photo": t.need_photo,
                "assignee_ids": json.loads(t.assignee_ids or "[]"),
                "assignee_names": [
                    kname[i] for i in json.loads(t.assignee_ids or "[]") if i in kname
                ],
                "effective_from": t.effective_from or "",
                "effective_to": t.effective_to or "",
                "active": t.active,
            }
            for t in rows
        ],
        "kids": [{"id": k.id, "name": k.name, "avatar": k.avatar} for k in kids],
    }


@router.post("/task")
def create_task(body: TaskIn, parent: User = Depends(require_parent),
                db: Session = Depends(get_db)):
    """家长是唯一发布者。孩子端不存在任何创建入口。"""
    if body.repeat_type not in ("daily", "weekly", "none"):
        raise HTTPException(400, "重复方式不正确")
    if body.category not in ("study", "exercise", "chore", "habit"):
        raise HTTPException(400, "分类不正确")
    if int(body.points) <= 0:
        raise HTTPException(400, "分值要大于 0")
    if int(body.points) > 50:
        raise HTTPException(400, "单个任务分值不宜超过 50，否则积分会贬值")

    t = TaskTemplate(
        family_id=parent.family_id,
        name=body.name.strip()[:20],
        category=body.category,
        points=int(body.points),
        icon=body.icon or "✅",
        repeat_type=body.repeat_type,
        repeat_rule=json.dumps(body.repeat_rule or []),
        assignee_ids=json.dumps(body.assignee_ids or []),
        display_zone=body.display_zone if body.display_zone in ("today", "extra") else "today",
        need_approval=body.need_approval,
        need_photo=body.need_photo,
        effective_from=body.effective_from or None,
        effective_to=body.effective_to or None,
        created_by=parent.id,
    )
    db.add(t)
    db.flush()
    add_audit(db, parent.family_id, parent.id, "create_task", "task_template", t.id, t.name)
    db.commit()
    return {"ok": True, "id": t.id}


@router.patch("/task/{task_id}")
def update_task(task_id: int, body: TaskIn, parent: User = Depends(require_parent),
                db: Session = Depends(get_db)):
    t = db.get(TaskTemplate, task_id)
    if not t or t.family_id != parent.family_id:
        raise HTTPException(404, "任务不存在")
    t.name = body.name.strip()[:20]
    t.category = body.category
    t.points = int(body.points)
    t.icon = body.icon or "✅"
    t.repeat_type = body.repeat_type
    t.repeat_rule = json.dumps(body.repeat_rule or [])
    t.assignee_ids = json.dumps(body.assignee_ids or [])
    t.display_zone = body.display_zone
    t.need_approval = body.need_approval
    t.need_photo = body.need_photo
    t.effective_from = body.effective_from or None
    t.effective_to = body.effective_to or None
    add_audit(db, parent.family_id, parent.id, "update_task", "task_template", t.id, t.name)
    db.commit()
    return {"ok": True}


@router.delete("/task/{task_id}")
def retire_task(task_id: int, parent: User = Depends(require_parent),
                db: Session = Depends(get_db)):
    """停用而不是删除 —— 历史打卡记录还要能追溯到任务名字。"""
    t = db.get(TaskTemplate, task_id)
    if not t or t.family_id != parent.family_id:
        raise HTTPException(404, "任务不存在")
    t.active = False
    add_audit(db, parent.family_id, parent.id, "retire_task", "task_template", t.id, t.name)
    db.commit()
    return {"ok": True}


# ------------------------------------------------------------------ 愿望审批
@router.get("/wishes")
def list_all_wishes(parent: User = Depends(require_parent), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Wish)
        .where(Wish.family_id == parent.family_id)
        .order_by(Wish.created_at.desc())
    ).all()
    return {
        "wishes": [
            {
                "id": w.id,
                "child_id": w.child_id,
                "child_name": (db.get(User, w.child_id).name if db.get(User, w.child_id) else ""),
                "title": w.title,
                "cover": w.cover_image,
                "cost": w.cost_coin,
                # 孩子许愿时不填价格，0 表示"还差一个定价"，前端要提示家长
                "priced": w.cost_coin > 0,
                "note": w.note,
                "status": w.status,
                "target_date": w.target_date or "",
                "is_primary": w.priority == 1,
                "created_at": w.created_at.strftime("%m-%d %H:%M"),
            }
            for w in rows
        ]
    }


class WishEditIn(BaseModel):
    """家长编辑愿望：可以只改内容，也可以只改价，或一起改。

    确认前(pending)改价即视作通过；确认后改价只是调价。
    """

    cost_coin: int | None = None
    title: str | None = None
    note: str | None = None
    cover_image: str | None = None
    target_date: str | None = None


@router.patch("/wish/{wish_id}")
def edit_wish(wish_id: int, body: WishEditIn,
              parent: User = Depends(require_parent),
              db: Session = Depends(get_db)):
    w = db.get(Wish, wish_id)
    if not w or w.family_id != parent.family_id:
        raise HTTPException(404, "愿望不存在")
    if w.status in ("completed", "abandoned"):
        raise HTTPException(400, "这个愿望已经结束了，改不了啦")

    # —— 内容字段：有传才改，缺省不动 ——
    if body.title is not None:
        t = body.title.strip()
        if not t:
            raise HTTPException(400, "标题不能为空")
        w.title = t[:40]
    if body.note is not None:
        w.note = body.note[:200]
    if body.cover_image is not None:
        w.cover_image = body.cover_image
    if body.target_date is not None:
        w.target_date = body.target_date or None

    # —— 价格字段：有传才改并走审批/调价逻辑 ——
    if body.cost_coin is not None:
        if int(body.cost_coin) < 1:
            raise HTTPException(400, "星星币数量要是大于 0 的整数")
        old = w.cost_coin
        w.cost_coin = int(body.cost_coin)
        if w.status == "pending":
            # 定价即视作通过：孩子已经许了愿，家长给了价，没必要再走一次确认
            w.status = "active"
            add_audit(db, parent.family_id, parent.id, "approve_wish", "wish", w.id, w.title)
        else:
            add_audit(db, parent.family_id, parent.id, "reprice_wish", "wish", w.id,
                      f"{old}→{w.cost_coin}")

    db.commit()
    return {"ok": True, "cost": w.cost_coin, "status": w.status}


@router.delete("/wish/{wish_id}")
def delete_wish(wish_id: int,
                parent: User = Depends(require_parent),
                db: Session = Depends(get_db)):
    """家长彻底删除一个愿望（含其兑换申请）。

    不是软删除：行直接移除，列表里就不再出现。已实现的愿望也能删，
    只是会连同一并清掉它的兑换记录 —— 星星币流水(coin ledger)不受影响，
    孩子的账户余额不会错乱。
    """
    w = db.get(Wish, wish_id)
    if not w or w.family_id != parent.family_id:
        raise HTTPException(404, "愿望不存在")
    # 先清掉外键指向它的兑换申请，否则 SQLite 外键约束会拦删除
    for r in db.scalars(
        select(Redemption).where(Redemption.wish_id == wish_id)
    ).all():
        db.delete(r)
    add_audit(db, parent.family_id, parent.id, "delete_wish", "wish", w.id, w.title)
    db.delete(w)
    db.commit()
    return {"ok": True}


class WishReviewIn(BaseModel):
    wish_id: int
    action: str                     # approve / reject
    cost_coin: int | None = None
    reason: str = ""


@router.post("/wish/review")
def review_wish(body: WishReviewIn, parent: User = Depends(require_parent),
                db: Session = Depends(get_db)):
    w = db.get(Wish, body.wish_id)
    if not w or w.family_id != parent.family_id:
        raise HTTPException(404, "愿望不存在")

    if body.action == "reject":
        w.status = "abandoned"
        w.reject_reason = body.reason[:80]
        add_audit(db, parent.family_id, parent.id, "reject_wish", "wish", w.id, body.reason[:80])
        db.commit()
        return {"ok": True, "status": "abandoned"}

    if body.cost_coin is not None:
        if int(body.cost_coin) < 1:
            raise HTTPException(400, "星星币数量要是大于 0 的整数")
        w.cost_coin = int(body.cost_coin)
    if w.cost_coin <= 0:
        # 孩子许愿时不填价格，所以确认这一步必须把价定下来
        raise HTTPException(400, "给这个愿望定一个星星币数量吧")

    w.status = "active"
    add_audit(db, parent.family_id, parent.id, "approve_wish", "wish", w.id, w.title)
    db.commit()
    return {"ok": True, "status": "active", "cost": w.cost_coin}


# ------------------------------------------------------------------ 手动调整与报表
class GrantIn(BaseModel):
    kid_id: int
    points: int
    note: str = ""
    category: str = "habit"


@router.post("/grant")
def manual_grant(body: GrantIn, parent: User = Depends(require_parent),
                 db: Session = Depends(get_db)):
    """家长手动奖励。同样受每日上限约束，没有后门。"""
    ps = PointService(db)
    kid = _kid(db, parent, body.kid_id)
    biz = today_str()

    if int(body.points) == 0:
        raise HTTPException(400, "分值不能为 0")

    if int(body.points) > 0:
        res = ps.grant(
            kid,
            int(body.points),
            source_type="manual",
            category=body.category,
            note=body.note or "家长特别奖励",
            operator_id=parent.id,
            biz_date=biz,
        )
        add_audit(db, parent.family_id, parent.id, "manual_grant", "user", kid.id,
                  f"{res['granted']} {body.note}")
        if res["granted"] > 0:
            ps.update_streak(kid, biz)
        db.commit()
        return {"ok": True, "granted": res["granted"], "capped": res["capped"]}

    raise HTTPException(400, "不建议直接扣分，可以用「暂缓某项特权」来代替")


@router.get("/report")
def report(kid_id: int, days: int = Query(14, ge=1, le=90),
           parent: User = Depends(require_parent), db: Session = Depends(get_db)):
    ps = PointService(db)
    kid = _kid(db, parent, kid_id)

    start = (dt.date.today() - dt.timedelta(days=days - 1)).isoformat()
    rows = db.execute(
        select(PointLedger.biz_date, func.sum(PointLedger.delta_coin))
        .where(
            PointLedger.child_id == kid.id,
            PointLedger.biz_date >= start,
            PointLedger.delta_coin != 0,
        )
        .group_by(PointLedger.biz_date)
    ).all()
    daily = {d: int(v or 0) for d, v in rows}

    by_cat = db.execute(
        select(PointLedger.category, func.sum(PointLedger.delta_coin))
        .where(
            PointLedger.child_id == kid.id,
            PointLedger.biz_date >= start,
            PointLedger.delta_coin > 0,
        )
        .group_by(PointLedger.category)
    ).all()

    return {
        "kid": kid_brief(db, kid, ps),
        "total_earned": ps.total_earned(kid.id),     # 仅家长端可见
        "available": ps.available_coin(kid.id),
        "frozen": ps.frozen_coin(kid.id),
        "exp": ps.exp_total(kid.id),
        "avg7": ps.daily_average(kid.id, 7),
        "daily": [{"date": (dt.date.today() - dt.timedelta(days=days - 1 - i)).isoformat(),
                   "coin": daily.get((dt.date.today() - dt.timedelta(days=days - 1 - i)).isoformat(), 0)}
                  for i in range(days)],
        "by_category": [{"category": c or "other", "coin": int(v or 0)} for c, v in by_cat],
        "ledger": ledger_rows(db, kid, days=days, limit=200),
    }


# ------------------------------------------------------------------ 成员
@router.get("/members")
def members(parent: User = Depends(require_parent), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(User).where(User.family_id == parent.family_id, User.active.is_(True))
    ).all()
    return {
        "members": [
            {"id": u.id, "name": u.name, "avatar": u.avatar, "role": u.role,
             "birth_year": u.birth_year, "ui_mode": u.ui_mode, "username": u.username}
            for u in rows
        ]
    }


class KidIn(BaseModel):
    name: str
    avatar: str = "🙂"
    pin: str
    birth_year: int | None = None
    ui_mode: str = "childish"


@router.post("/kid")
def add_kid(body: KidIn, parent: User = Depends(require_parent),
            db: Session = Depends(get_db)):
    if len(body.pin) < 4:
        raise HTTPException(400, "口令至少 4 位")
    kid = User(
        family_id=parent.family_id,
        name=body.name.strip()[:10],
        avatar=body.avatar or "🙂",
        role="child",
        pin_hash=hash_pin(body.pin),
        birth_year=body.birth_year,
        ui_mode=body.ui_mode,
    )
    db.add(kid)
    db.flush()
    add_audit(db, parent.family_id, parent.id, "add_kid", "user", kid.id, kid.name)
    db.commit()
    return {"ok": True, "id": kid.id}


# ------------------------------------------------------------------ 规则
@router.get("/rules")
def get_rules(parent: User = Depends(require_parent)):
    """结构化规则，供网页表单直接渲染。"""
    return rules_structured()


@router.get("/rules/raw")
def get_rules_raw(parent: User = Depends(require_parent)):
    """原始 YAML 文本，给需要精细调整的场景留一个入口。"""
    return {"text": rules_text()}


class RulesIn(BaseModel):
    text: str


@router.post("/rules/raw")
def update_rules_raw(body: RulesIn, parent: User = Depends(require_parent),
                     db: Session = Depends(get_db)):
    try:
        data = save_rules_text(body.text)
    except Exception as e:
        raise HTTPException(400, f"规则格式有误：{e}")
    _recompute_levels(db, parent.family_id)
    add_audit(db, parent.family_id, parent.id, "update_rules_raw", "family", parent.family_id, "")
    db.commit()
    return {"ok": True, "version": data.get("version")}


class RulesStructuredIn(BaseModel):
    currency: dict | None = None
    daily_cap: dict | None = None
    streak_bonus: list | None = None
    streak_shield_per_month: int | None = None
    levels: list | None = None
    gating: dict | None = None
    application: dict | None = None
    redemption: dict | None = None
    games: list | None = None


@router.put("/rules")
def update_rules(body: RulesStructuredIn, parent: User = Depends(require_parent),
                 db: Session = Depends(get_db)):
    """
    保存后立即热加载，不需要重启服务。
    等级门槛一旦变化，所有孩子的等级当场重算 —— 否则改了表孩子等级却不动，
    孩子会以为系统坏了。
    """
    payload = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        data = save_rules_structured(payload)
    except Exception as e:
        raise HTTPException(400, f"规则写入失败：{e}")

    changed = _recompute_levels(db, parent.family_id)
    add_audit(db, parent.family_id, parent.id, "update_rules", "family", parent.family_id,
              ",".join(payload.keys()))
    db.commit()
    return {"ok": True, "version": data.get("version"), "levels_changed": changed}


def _recompute_levels(db: Session, family_id: int) -> list:
    """按新规则重算每个孩子的等级，返回发生过变化的孩子。"""
    ps = PointService(db)
    kids = db.scalars(
        select(User).where(User.family_id == family_id, User.role == "child")
    ).all()
    changed = []
    for k in kids:
        exp = ps.exp_total(k.id)
        before = k.level or 1
        ps._sync_level(k, exp)
        k.level = level_info(exp, load_rules()).get("level", k.level)
        db.flush()
        if k.level != before:
            changed.append({"name": k.name, "from": before, "to": k.level})
    return changed
