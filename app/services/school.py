# -*- coding: utf-8 -*-
"""
家长学堂与家庭共学。

出发点只有一个：如果家里只有孩子被考核，这套系统迟早会被孩子理解成
「大人给小孩打分」。所以这里提供了另一半 ——

1. 内置微课：离线可读，每篇收在「今晚就能做的一件事」上，不写空道理。
2. 家庭共学：记录爸爸妈妈陪读、一起运动、一起做饭的分钟数。
   它不会变成孩子的星星币 —— 陪伴本身就是回报，不该再标价。
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import load_rules, today_str
from ..content.articles import ARTICLES
from ..content.articles import TOPICS
from ..models import FamilyLearn, SchoolRead, User

KINDS = {
    "read": {"n": "亲子阅读", "e": "\U0001F4D6"},
    "sport": {"n": "一起运动", "e": "\U0001F3C3"},
    "cook": {"n": "一起做饭", "e": "\U0001F373"},
    "talk": {"n": "聊天谈心", "e": "\U0001F4AC"},
    "game": {"n": "一起玩", "e": "\U0001F3AE"},
    "other": {"n": "其他", "e": "⭐"},
}


def cfg() -> dict:
    return load_rules().get("parent_school") or {}


def week_start(d: dt.date | None = None) -> dt.date:
    d = d or dt.date.today()
    return d - dt.timedelta(days=d.weekday())


# ------------------------------------------------------------------ 微课
def recommend(db: Session, parent: User, n: int = 3) -> list:
    """今日推荐：没读过的优先；同一批里按天轮换，保证每天换一批。"""
    read = set(
        db.scalars(
            select(SchoolRead.article_code).where(SchoolRead.parent_id == parent.id)
        ).all()
    )
    unread = [a for a in ARTICLES if a["code"] not in read]
    pool = unread or ARTICLES
    pool = sorted(pool, key=lambda a: a["code"])
    # 按天旋转：每天换一批推荐，避免每次打开都是同一篇
    seed = dt.date.today().toordinal()
    k = seed % max(1, len(pool))
    pool = pool[k:] + pool[:k]
    return pool[:n]


def my_read(db: Session, parent: User) -> list:
    rows = db.scalars(
        select(SchoolRead).where(SchoolRead.parent_id == parent.id)
        .order_by(SchoolRead.read_at.desc())
    ).all()
    return [
        {
            "code": r.article_code,
            "title": next((a["title"] for a in ARTICLES if a["code"] == r.article_code), ""),
            "date": r.read_at.strftime("%Y-%m-%d"),
        }
        for r in rows
    ]


def mark_read(db: Session, parent: User, code: str) -> dict:
    if not any(a["code"] == code for a in ARTICLES):
        raise ValueError("没有这篇文章")
    exists = db.scalar(
        select(SchoolRead).where(
            SchoolRead.parent_id == parent.id, SchoolRead.article_code == code
        )
    )
    if exists:
        return {"ok": True, "code": code, "read_count": _read_count(db, parent)}
    db.add(
        SchoolRead(family_id=parent.family_id, parent_id=parent.id, article_code=code)
    )
    db.flush()
    return {"ok": True, "code": code, "read_count": _read_count(db, parent)}


def _read_count(db: Session, parent: User) -> int:
    v = db.scalar(
        select(func.count())
        .select_from(SchoolRead)
        .where(SchoolRead.parent_id == parent.id)
    )
    return int(v or 0)


# ------------------------------------------------------------------ 共学
def add_family_learn(db: Session, parent: User, kid: User, kind: str,
                     minutes: int, note: str = "") -> dict:
    if kind not in KINDS:
        kind = "other"
    minutes = max(1, min(240, int(minutes or 15)))
    row = FamilyLearn(
        family_id=parent.family_id,
        parent_id=parent.id,
        child_id=kid.id,
        kind=kind,
        minutes=minutes,
        note=(note or "")[:200],
        biz_date=today_str(),
    )
    db.add(row)
    db.flush()
    return {"ok": True, "id": row.id, "minutes": minutes}


def _week_records(db: Session, family_id: int) -> list:
    since = week_start().isoformat()
    return list(
        db.scalars(
            select(FamilyLearn)
            .where(FamilyLearn.family_id == family_id, FamilyLearn.biz_date >= since)
            .order_by(FamilyLearn.id.desc())
        ).all()
    )


def kid_rows(db: Session, family_id: int) -> list:
    return list(
        db.scalars(
            select(User)
            .where(User.family_id == family_id, User.role == "child", User.active.is_(True))
            .order_by(User.id)
        ).all()
    )


def overview(db: Session, parent: User) -> dict:
    c = cfg()
    goal = int(c.get("weekly_goal_minutes", 150))
    rows = _week_records(db, parent.family_id)
    total_min = sum(int(r.minutes or 0) for r in rows)
    by_kid = {}
    for r in rows:
        by_kid.setdefault(r.child_id, 0)
        by_kid[r.child_id] += int(r.minutes or 0)

    kids = [
        {
            "id": k.id,
            "name": k.name,
            "avatar": k.avatar,
            "minutes": by_kid.get(k.id, 0),
        }
        for k in kid_rows(db, parent.family_id)
    ]
    recent = rows[:12]

    return {
        "enabled": bool(c.get("enabled", True)),
        "goal_minutes": goal,
        "week_minutes": total_min,
        "week_percent": min(100, round(total_min * 100.0 / max(1, goal))),
        "week_count": len(rows),
        "kids": kids,
        "recent": [
            {
                "id": r.id,
                "date": r.biz_date,
                "kind": r.kind,
                "kind_name": KINDS.get(r.kind, {}).get("n", r.kind),
                "kind_emoji": KINDS.get(r.kind, {}).get("e", "⭐"),
                "minutes": int(r.minutes or 0),
                "note": r.note,
                "parent": _name(db, r.parent_id),
                "child": _name(db, r.child_id),
            }
            for r in recent
        ],
        "kinds": [dict(code=k, **v) for k, v in KINDS.items()],
        "topics": [
            dict(t, count=sum(1 for a in ARTICLES if a["topic"] == t["code"]))
            for t in TOPICS
        ],
        "recommend": recommend(db, parent),
        "read_count": _read_count(db, parent),
        "total_articles": len(ARTICLES),
        "read_list": my_read(db, parent)[:10],
    }


def _name(db: Session, uid: int) -> str:
    u = db.get(User, uid)
    return u.name if u else ""


def by_topic(topic: str) -> list:
    if not topic:
        return ARTICLES
    return [a for a in ARTICLES if a["topic"] == topic]


# ------------------------------------------------------------------ 孩子端
def child_records(db: Session, child: User, days: int = 7) -> dict:
    since = (dt.date.today() - dt.timedelta(days=days - 1)).isoformat()
    rows = list(
        db.scalars(
            select(FamilyLearn)
            .where(FamilyLearn.child_id == child.id, FamilyLearn.biz_date >= since)
            .order_by(FamilyLearn.id.desc())
        ).all()
    )
    today = [r for r in rows if r.biz_date == today_str()]
    return {
        "today_minutes": sum(int(r.minutes or 0) for r in today),
        "week_minutes": sum(int(r.minutes or 0) for r in rows),
        "count": len(rows),
        "records": [
            {
                "date": r.biz_date,
                "kind_name": KINDS.get(r.kind, {}).get("n", r.kind),
                "kind_emoji": KINDS.get(r.kind, {}).get("e", "⭐"),
                "minutes": int(r.minutes or 0),
                "note": r.note,
                "parent": _name(db, r.parent_id),
            }
            for r in rows[:20]
        ],
        "note": "" if today else "今天还没有记录哦，晚上可以找爸爸妈妈一起读会儿书 \U0001F4D6",
    }
