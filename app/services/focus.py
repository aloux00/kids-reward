# -*- coding: utf-8 -*-
"""
番茄钟 / 专注计时。

与一般「前端计时器」的区别：时长不由前端上报。
数据库里记的是服务端写入的开始时间，结束时由服务端用真实时间差判卷 ——
孩子就算把手机时钟改了也没用。

判卷留了两道缓冲：
- 早于计划时长 90%：判无效，不计一次番茄（也不扣任何东西）。
- 超过计划时长 5 分钟以上：说明中途跑开了，同样不计 —— 但也不惩罚。
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import load_rules, today_str
from ..models import FocusSession, User


def cfg() -> dict:
    return load_rules().get("pomodoro") or {}


def today_rows(db: Session, child: User, biz: str | None = None) -> list:
    biz = biz or today_str()
    return list(
        db.scalars(
            select(FocusSession)
            .where(
                FocusSession.child_id == child.id,
                FocusSession.biz_date == biz,
                FocusSession.status != "aborted",
            )
            .order_by(FocusSession.id)
        ).all()
    )


def valid_today(db: Session, child: User, biz: str | None = None) -> int:
    biz = biz or today_str()
    v = db.scalar(
        select(func.count())
        .select_from(FocusSession)
        .where(
            FocusSession.child_id == child.id,
            FocusSession.biz_date == biz,
            FocusSession.valid.is_(True),
        )
    )
    return int(v or 0)


def _dto(row: FocusSession, elapsed_min: float = 0.0) -> dict:
    plan = max(1, int(row.plan_minutes or 15))
    remain = int(max(0, plan * 60 - float(elapsed_min) * 60))
    return {
        "id": row.id,
        "topic": row.topic,
        "plan_minutes": plan,
        "actual_minutes": int(row.actual_minutes or 0),
        "status": row.status,
        "valid": bool(row.valid),
        "points": int(row.points or 0),
        "started_at": row.started_at.strftime("%H:%M"),
        "elapsed_minutes": int(elapsed_min),
        "remain_seconds": remain,
    }


def _stale_limit(plan: int) -> int:
    """超过这么久仍挂着「进行中」，就认定孩子早就离开了 —— 自动收场。"""
    c = cfg()
    return plan + int(c.get("grace_minutes", 5)) + 30


def auto_close_stale(db: Session, child: User, biz: str | None = None) -> int:
    """
    关掉「忘了收尾」的番茄。

    孩子关掉网页、手机没电、平板被收走 —— 这些都会留下一条永远是 running 的记录。
    不处理的话，他会永远卡在「上一次专注还没结束」，再也开不了新的番茄。
    这里按「计划 + 宽限 + 30 分钟」判定：超时就判为无效收场，不扣任何东西。
    """
    biz = biz or today_str()
    rows = list(
        db.scalars(
            select(FocusSession).where(
                FocusSession.child_id == child.id,
                FocusSession.biz_date == biz,
                FocusSession.status == "running",
            )
        ).all()
    )
    n = 0
    for row in rows:
        plan = max(1, int(row.plan_minutes or 15))
        elapsed = (dt.datetime.now() - row.started_at).total_seconds() / 60.0
        if elapsed <= _stale_limit(plan):
            continue
        row.status = "done"
        row.valid = False
        row.ended_at = dt.datetime.now()
        row.actual_minutes = int(round(elapsed))
        n += 1
    if n:
        db.flush()
    return n


def state(db: Session, child: User) -> dict:
    c = cfg()
    biz = today_str()
    auto_close_stale(db, child, biz)
    rows = today_rows(db, child, biz)
    running = next((r for r in rows if r.status == "running"), None)
    elapsed = 0.0
    if running:
        elapsed = (dt.datetime.now() - running.started_at).total_seconds() / 60.0
    limit = int(c.get("daily_limit", 4))
    done = sum(1 for r in rows if r.status == "done")
    return {
        "enabled": bool(c.get("enabled", True)),
        "running": _dto(running, elapsed) if running else None,
        "limit": limit,
        "today_used": done,
        "today_valid": valid_today(db, child, biz),
        "today_left": max(0, limit - done),
        "points_per_pomodoro": int(c.get("points_per_pomodoro", 2)),
        "minutes_options": list(c.get("minutes_options", [10, 15, 20, 25])),
        "default_minutes": int(c.get("default_minutes", 15)),
        "bonus_at": int(c.get("bonus_at", 4)),
        "bonus_points": int(c.get("bonus_points", 3)),
        "history": [
            _dto(r) for r in rows if r.status == "done"
        ][-6:],
        "tip": "专注的时候手机要放到一边哦，中途跑开这一次就不算啦 ⏳",
    }


def start(db: Session, child: User, minutes: int, topic: str = "") -> dict:
    c = cfg()
    if not c.get("enabled", True):
        raise ValueError("番茄钟没有开启")
    biz = today_str()
    auto_close_stale(db, child, biz)
    rows = today_rows(db, child, biz)
    if any(r.status == "running" for r in rows):
        raise ValueError("上一次专注还没结束呢")
    done = sum(1 for r in rows if r.status == "done")
    if done >= int(c.get("daily_limit", 4)):
        raise ValueError("今天的番茄用完啦，休息一下 🍅")

    opts = [int(x) for x in c.get("minutes_options", [10, 15, 20, 25])]
    plan = int(minutes or c.get("default_minutes", 15))
    if opts and plan not in opts:
        plan = min(opts, key=lambda x: abs(x - plan))
    plan = max(1, min(60, plan))

    row = FocusSession(
        family_id=child.family_id,
        child_id=child.id,
        topic=(topic or "专注学习")[:40],
        plan_minutes=plan,
        status="running",
        biz_date=biz,
        started_at=dt.datetime.now(),
    )
    db.add(row)
    db.flush()
    return {"ok": True, "session": _dto(row)}


def finish(db: Session, child: User, ps, session_id: int) -> dict:
    c = cfg()
    biz = today_str()
    row = db.get(FocusSession, session_id)
    if not row or row.child_id != child.id:
        raise ValueError("没有找到这次专注")
    if row.status != "running":
        raise ValueError("这次专注已经结束啦")

    elapsed = (dt.datetime.now() - row.started_at).total_seconds() / 60.0
    plan = max(1, int(row.plan_minutes or 15))
    need = plan * float(c.get("min_ratio", 0.9))
    grace = plan + int(c.get("grace_minutes", 5))

    row.ended_at = dt.datetime.now()
    row.actual_minutes = int(round(elapsed))
    row.status = "done"

    # 时间不够或拖太久：都算这次没成，但绝不影响心情 —— 不扣分、不占次数奖励
    if elapsed < need:
        row.valid = False
        db.flush()
        return _no_reward(db, child, biz, row,
                          f"这次只坚持了 {int(round(elapsed))} 分钟，还差一点点。"
                          "没关系，再试一次吧 \U0001F331")
    if elapsed > grace:
        row.valid = False
        db.flush()
        return _no_reward(db, child, biz, row,
                          f"这次超过了计划的 {plan} 分钟太多啦（{int(round(elapsed))} 分钟），"
                          "说明中间跑开了 —— 下次试试把手机放远一点")

    row.valid = True
    per = int(c.get("points_per_pomodoro", 2))
    amount = per
    note = f"番茄钟 {row.topic} {plan} 分钟"
    valid_n = valid_today(db, child, biz) + 1      # 含本次
    at = int(c.get("bonus_at", 4))
    bonus = 0
    if at > 0 and valid_n == at:
        bonus = int(c.get("bonus_points", 3))
        amount += bonus
        note += f"（当天第 {at} 个番茄奖励）"

    res = ps.grant(
        child,
        amount,
        source_type="focus",
        category=str(c.get("category", "study")),
        source_id=row.id,
        note=note[:120],
        operator_id=child.id,
        biz_date=biz,
    )
    row.points = res["granted"]
    db.flush()
    today_done = sum(1 for r in today_rows(db, child, biz) if r.status == "done")
    return {
        "ok": True,
        "valid": True,
        "points": res["granted"],
        "capped": res["capped"],
        "bonus": bonus,
        "minutes": row.actual_minutes,
        "today_valid": valid_n,
        "today_used": today_done,
        "limit": int(c.get("daily_limit", 4)),
        "note": f"专注完成！{row.topic} {plan} 分钟 ⏳"
        + (f" 额外奖励 +{bonus}" if bonus else ""),
    }


def _no_reward(db: Session, child: User, biz: str, row: FocusSession, note: str) -> dict:
    """这一次不算数时的统一返回结构 —— 前端按 points=0 走安慰话术，不弹错误。"""
    done = sum(1 for r in today_rows(db, child, biz) if r.status == "done")
    return {
        "ok": True,
        "valid": False,
        "points": 0,
        "capped": False,
        "bonus": 0,
        "minutes": int(row.actual_minutes or 0),
        "today_valid": valid_today(db, child, biz),
        "today_used": done,
        "limit": int(cfg().get("daily_limit", 4)),
        "note": note,
    }


def abort(db: Session, child: User, session_id: int) -> dict:
    row = db.get(FocusSession, session_id)
    if not row or row.child_id != child.id:
        raise ValueError("没有找到这次专注")
    if row.status != "running":
        raise ValueError("这次专注已经结束啦")
    elapsed = (dt.datetime.now() - row.started_at).total_seconds() / 60.0
    row.status = "aborted"
    row.ended_at = dt.datetime.now()
    row.actual_minutes = int(round(elapsed))
    row.valid = False
    db.flush()
    return {"ok": True, "minutes": row.actual_minutes}
