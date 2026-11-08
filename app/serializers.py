# -*- coding: utf-8 -*-
"""统一的序列化层。孩子端的字段裁剪全部在这里做掉，路由里不再散落判断。"""
from __future__ import annotations

import datetime as dt
import json
import math
from typing import Optional

from sqlalchemy import func, select

from .models import (
    LevelEvent,
    PointApplication,
    PointLedger,
    Redemption,
    TaskRecord,
    TaskTemplate,
    User,
    UserAchievement,
    Wish,
    Achievement,
    GameSession,
)


# ------------------------------------------------------------------ 日期
def date_matches(tpl: TaskTemplate, biz_date: str) -> bool:
    """判断某任务在某天是否需要出现。"""
    start = tpl.effective_from or "0000-01-01"
    end = tpl.effective_to or "9999-12-31"
    if not (start <= biz_date <= end):
        return False

    if tpl.repeat_type == "daily":
        return True
    if tpl.repeat_type == "weekly":
        try:
            days = json.loads(tpl.repeat_rule or "[]")
        except Exception:
            return False
        # 界面上 1=周一 … 7=周日
        weekday = dt.date.fromisoformat(biz_date).weekday() + 1
        return weekday in days
    return True  # none：随机任务，在有效期内一直出现（完成后由展示层隐藏）


def assigned_to(tpl: TaskTemplate, child_id: int) -> bool:
    if not tpl.assignee_ids or tpl.assignee_ids in ("[]", "null"):
        return True  # 未指定则面向全部孩子
    try:
        ids = json.loads(tpl.assignee_ids)
    except Exception:
        return True
    return child_id in ids


# ------------------------------------------------------------------ 任务
def list_today_tasks(db, child: User, biz_date: str) -> tuple[list, list]:
    """返回 (今日任务, 额外任务)。分区由 display_zone 决定，不由任务类型写死。"""
    tpls = db.scalars(
        select(TaskTemplate).where(
            TaskTemplate.family_id == child.family_id,
            TaskTemplate.active.is_(True),
        )
    ).all()

    records = {
        (r.template_id, r.id): r
        for r in db.scalars(
            select(TaskRecord).where(
                TaskRecord.child_id == child.id, TaskRecord.biz_date == biz_date
            )
        ).all()
    }

    today_list, extra_list = [], []
    for tpl in tpls:
        if not date_matches(tpl, biz_date) or not assigned_to(tpl, child.id):
            continue
        rec = next((r for (tid, _), r in records.items() if tid == tpl.id), None)
        # 随机任务是一次性的，通过后自然消失
        if rec and rec.status == "approved" and tpl.repeat_type == "none":
            continue

        dto = {
            "instance_id": rec.id if rec else None,
            "template_id": tpl.id,
            "name": tpl.name,
            "category": tpl.category,
            "points": tpl.points,
            "icon": tpl.icon,
            "need_photo": tpl.need_photo,
            "need_approval": tpl.need_approval,
            "status": rec.status if rec else "todo",
            "awarded_coin": rec.awarded_coin if rec else 0,
            "evidence_image": rec.evidence_image if rec else "",
            "reject_reason": rec.reject_reason if rec else "",
        }
        (today_list if tpl.display_zone == "today" else extra_list).append(dto)

    today_list.sort(key=lambda x: x["status"] == "approved")
    return today_list, extra_list


# ------------------------------------------------------------------ 愿望
def wish_dto(db, wish: Wish, ps, available: int, avg7: float) -> dict:
    frozen_here = int(
        db.scalar(
            select(Redemption.cost_coin)
            .where(
                Redemption.wish_id == wish.id,
                Redemption.status == "pending",
            )
            .limit(1)
        )
        or 0
    )
    # 星星币由家长定价。cost_coin == 0 表示"爸爸妈妈还没定"，
    # 这时候进度、差额都没有意义，一律按 0 处理，别让孩子看到满格进度条。
    priced = wish.cost_coin > 0
    have = min(wish.cost_coin, available + frozen_here) if priced else 0
    gap = max(0, wish.cost_coin - available - frozen_here) if priced else 0
    progress = int(have * 100 / wish.cost_coin) if priced else 0
    progress = max(0, min(100, progress))

    eta_days = None
    if gap > 0 and avg7 > 0:
        eta_days = math.ceil(gap / avg7)
        eta = (dt.date.today() + dt.timedelta(days=eta_days)).isoformat()
    elif gap == 0:
        eta = dt.date.today().isoformat()
    else:
        eta = None

    return {
        "id": wish.id,
        "title": wish.title,
        "note": wish.note,
        "cover": wish.cover_image,
        "cost": wish.cost_coin,
        "priced": priced,
        "progress": progress,
        "gap": gap,
        "is_primary": wish.priority == 1,
        "status": wish.status,
        "target_date": wish.target_date or "",
        "eta": eta,
        "eta_days": eta_days,
        "frozen_here": frozen_here,
        # 家长驳回愿望时写的理由必须让孩子看到，否则他不知道该怎么改
        "reject_reason": wish.reject_reason or "",
    }


def list_wishes(db, child: User, ps, active_only: bool = True) -> list:
    available = ps.available_coin(child.id)
    avg7 = ps.daily_average(child.id)
    q = select(Wish).where(Wish.child_id == child.id)
    if active_only:
        q = q.where(Wish.status.in_(["pending", "active"]))
    q = q.order_by(Wish.priority.desc(), Wish.created_at.desc())
    return [wish_dto(db, w, ps, available, avg7) for w in db.scalars(q).all()]


# ------------------------------------------------------------------ 用户
def kid_brief(db, kid: User, ps) -> dict:
    from .services.level import level_info
    from .config import load_rules

    exp = ps.exp_total(kid.id)
    summary = ps.coin_summary(kid)
    return {
        "id": kid.id,
        "name": kid.name,
        "avatar": kid.avatar,
        "role": kid.role,
        "birth_year": kid.birth_year,
        "ui_mode": kid.ui_mode,
        "level": kid.level,
        **{k: v for k, v in level_info(exp, load_rules()).items()},
        "exp_total": exp,
        "coin_available": summary["available"],
        "coin_frozen": summary["frozen"],
        "coin_net": summary["net"],
        "streak_days": kid.streak_days,
    }


def ledger_rows(db, child: User, days: int = 14, limit: int = 60) -> list:
    start = (dt.date.today() - dt.timedelta(days=days - 1)).isoformat()
    rows = db.scalars(
        select(PointLedger)
        .where(PointLedger.child_id == child.id, PointLedger.biz_date >= start)
        .order_by(PointLedger.id.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": r.id,
            "date": r.biz_date,
            "delta_coin": r.delta_coin,
            "delta_exp": r.delta_exp,
            "source_type": r.source_type,
            "category": r.category,
            "note": r.note,
            "coin_after": r.coin_after,
        }
        for r in rows
    ]


def achievements_of(db, child: User) -> list:
    """只列出已获得的成就（保留给需要精简结果的场合）。"""
    rows = db.execute(
        select(Achievement, UserAchievement.got_at)
        .join(UserAchievement, UserAchievement.achievement_id == Achievement.id)
        .where(UserAchievement.child_id == child.id)
        .order_by(UserAchievement.got_at.desc())
    ).all()
    return [
        {
            "code": a.code,
            "name": a.name,
            "icon": a.icon,
            "got_at": got_at.strftime("%Y-%m-%d") if got_at else "",
        }
        for a, got_at in rows
    ]


_HINT = {
    "coin_total": "累计获得的星星币",
    "streak_days": "连续打卡天数",
    "wish_completed": "已实现的愿望",
    "game_cleared": "闯关通关次数",
}


def achievement_wall(db, child: User, ps) -> list:
    """完整徽章墙：全部成就（含未获得）+ 各自的当前进度。

    只展示已获得的成就会让孩子不知道还能追求什么；
    把未达成的也显示出来并给出进度，才是"下一目标"的来源。
    """
    achvs = db.scalars(
        select(Achievement).where(
            Achievement.family_id == child.family_id,
            Achievement.enabled.is_(True),
        ).order_by(Achievement.condition_value, Achievement.id)
    ).all()
    if not achvs:
        return []

    got = {
        ua.achievement_id: ua.got_at
        for ua in db.scalars(
            select(UserAchievement).where(UserAchievement.child_id == child.id)
        ).all()
    }

    # 四类条件的当前值集中算一次，避免每条成就重复扫表
    cur = {
        "coin_total": ps.total_earned(child.id),
        "streak_days": int(child.streak_days or 0),
        "wish_completed": int(db.scalar(
            select(func.count()).select_from(Wish).where(
                Wish.child_id == child.id, Wish.status == "completed"
            )) or 0),
        "game_cleared": int(db.scalar(
            select(func.count()).select_from(GameSession).where(
                GameSession.child_id == child.id, GameSession.cleared.is_(True)
            )) or 0),
    }

    out = []
    for a in achvs:
        target = max(1, int(a.condition_value or 1))
        have = max(0, int(cur.get(a.condition_type, 0) or 0))
        at = got.get(a.id)
        out.append({
            "code": a.code,
            "name": a.name,
            "desc": a.desc or "",
            "icon": a.icon or "🏅",
            "got": bool(at),
            "got_at": at.strftime("%Y-%m-%d") if at else "",
            "target": target,
            "current": min(have, target) if not at else target,
            "percent": 100 if at else max(0, min(100, int(have * 100 / target))),
            "hint": _HINT.get(a.condition_type, "完成条件"),
        })
    # 已获得排前面，其余按完成度倒序 —— 最接近的排最前，孩子一眼看到"再努努力就是它"
    out.sort(key=lambda x: (not x["got"], -x["percent"]))
    return out


def certificate_of(db, child: User, ps) -> dict:
    """荣誉证书所需的数据。打印页直接用它渲染。"""
    from .services.level import level_info
    from .config import load_rules

    exp = ps.exp_total(child.id)
    li = level_info(exp, load_rules())
    summary = ps.coin_summary(child)

    done = db.scalars(
        select(Wish).where(
            Wish.child_id == child.id, Wish.status == "completed"
        ).order_by(Wish.completed_at.desc())
    ).all()

    return {
        "name": child.name,
        "avatar": child.avatar or "⭐",
        "level": li.get("level"),
        "title": li.get("title"),
        "perk": li.get("perk"),
        "exp": exp,
        "coin_total": ps.total_earned(child.id),
        "coin_available": summary["available"],
        "streak_days": int(child.streak_days or 0),
        "achievements": [
            {"name": a["name"], "icon": a["icon"], "got_at": a["got_at"]}
            for a in achievement_wall(db, child, ps) if a["got"]
        ],
        "wishes_done": [
            {
                "title": w.title,
                "cost": w.cost_coin,
                "at": w.completed_at.strftime("%Y-%m-%d") if w.completed_at else "",
            }
            for w in done
        ],
        "issued_at": dt.date.today().isoformat(),
        "serial": f"SK{child.id:03d}{dt.date.today().strftime('%Y%m%d')}",
    }


def level_events(db, child: User) -> list:
    rows = db.scalars(
        select(LevelEvent)
        .where(LevelEvent.child_id == child.id)
        .order_by(LevelEvent.id.desc())
        .limit(20)
    ).all()
    return [
        {
            "level": e.level,
            "title": e.title,
            "perk": e.perk,
            "at": e.reached_at.strftime("%Y-%m-%d"),
        }
        for e in rows
    ]


def pending_dto(db, family_id: int) -> list:
    """家长的待办清单：打卡确认 + 加分申请 + 兑换申请，三类合并按时间倒序。"""
    out = []

    recs = db.scalars(
        select(TaskRecord)
        .where(TaskRecord.family_id == family_id, TaskRecord.status == "pending")
        .order_by(TaskRecord.submitted_at.desc())
    ).all()
    for r in recs:
        kid = db.get(User, r.child_id)
        tpl = db.get(TaskTemplate, r.template_id)
        out.append(
            {
                "kind": "task",
                "id": r.id,
                "child_id": r.child_id,
                "child_name": kid.name if kid else "",
                "child_avatar": kid.avatar if kid else "",
                "title": tpl.name if tpl else "（任务已删除）",
                "icon": tpl.icon if tpl else "✅",
                "category": tpl.category if tpl else "habit",
                "points": tpl.points if tpl else r.awarded_coin,
                "evidence_text": r.evidence_text,
                "evidence_image": r.evidence_image,
                "at": r.submitted_at.strftime("%m-%d %H:%M"),
                "biz_date": r.biz_date,
            }
        )

    apps = db.scalars(
        select(PointApplication)
        .where(
            PointApplication.family_id == family_id, PointApplication.status == "pending"
        )
        .order_by(PointApplication.submitted_at.desc())
    ).all()
    for a in apps:
        kid = db.get(User, a.child_id)
        out.append(
            {
                "kind": "apply",
                "id": a.id,
                "child_id": a.child_id,
                "child_name": kid.name if kid else "",
                "child_avatar": kid.avatar if kid else "",
                "title": a.title,
                "icon": "⭐",
                "category": a.category,
                "points": a.points,
                "evidence_text": a.evidence_text,
                "evidence_image": a.evidence_image,
                "at": a.submitted_at.strftime("%m-%d %H:%M"),
                "biz_date": a.biz_date,
            }
        )

    rdms = db.scalars(
        select(Redemption)
        .where(Redemption.family_id == family_id, Redemption.status == "pending")
        .order_by(Redemption.created_at.desc())
    ).all()
    for r in rdms:
        kid = db.get(User, r.child_id)
        wish = db.get(Wish, r.wish_id)
        out.append(
            {
                "kind": "redeem",
                "id": r.id,
                "child_id": r.child_id,
                "child_name": kid.name if kid else "",
                "child_avatar": kid.avatar if kid else "",
                "title": wish.title if wish else "（愿望已删除）",
                "icon": "🎁",
                "category": "",
                "points": r.cost_coin,
                "cover": wish.cover_image if wish else "",
                "at": r.created_at.strftime("%m-%d %H:%M"),
                "biz_date": r.created_at.strftime("%Y-%m-%d"),
            }
        )

    out.sort(key=lambda x: x["at"], reverse=True)
    return out
