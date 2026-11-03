# -*- coding: utf-8 -*-
"""
错题本内核。

只做两件事：把错的题收进来，把重做的判回去。
积分永远交给 PointService，绝不自己改余额 —— 这样错题订正的奖励天然受每日上限约束，
不会出现「刷错题本比乖乖打卡更划算」。
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from ..config import load_rules, wrong_subjects
from ..models import User, WrongQuestion


def quiz_text(q: dict) -> str:
    """把速算构造题转成孩子看得懂的题面。"""
    op = q.get("op", "+")
    a, b = q.get("a", 0), q.get("b", 0)
    sign = {"+": "＋", "-": "－", "*": "×"}.get(op, op)
    return f"{a} {sign} {b} = ?"


def wrong_cfg() -> dict:
    return load_rules().get("wrong_book") or {}


def today_iso() -> str:
    return dt.date.today().isoformat()


def subjects() -> list:
    """科目列表。家长可维护，取不到就用默认四科。"""
    return wrong_subjects()


def subject_map() -> dict:
    return {s["code"]: s for s in subjects()}


def subject_label(code: str) -> str:
    """找不到对应科目时（比如家长刚删掉）退回原 code，不要显示空白。"""
    m = subject_map()
    return (m.get(code) or {}).get("name") or code


def prompt_of(question: str) -> str:
    """把 "7 + 8 = ?" 变成给孩子手写重做的 "7 + 8 = ＿＿＿"。"""
    q = str(question or "").strip()
    for tail in ("= ?", "=？", "=?"):
        if q.endswith(tail):
            return q[: -len(tail)].strip() + " = ＿＿＿"
    return q


def record_wrong(
    db: Session,
    child: User,
    *,
    question: str,
    correct_answer: str,
    wrong_answer: str = "",
    source: str = "game",
    subject: str = "math",
    kind: str = "mental-math",
    explain: str = "",
) -> WrongQuestion:
    """
    收录一道错题。

    同一道题（同一孩子 + 同一题型 + 同一题面）再次做错时只累加次数，
    不新增一行 —— 否则列表会被同一个坑刷满，孩子就懒得看了。
    """
    row = db.scalar(
        select(WrongQuestion).where(
            WrongQuestion.child_id == child.id,
            WrongQuestion.kind == kind,
            WrongQuestion.question == question,
        )
    )
    if row is None:
        row = WrongQuestion(
            family_id=child.family_id,
            child_id=child.id,
            source=source,
            subject=subject,
            kind=kind,
            question=question,
            correct_answer=str(correct_answer),
            wrong_answer=str(wrong_answer),
            explain=explain,
            times_wrong=1,
            mastered=False,
            mastered_at=None,
            last_wrong_at=dt.datetime.now(),
            # 当天就能订正一次：错完立刻重做，印象最深
            due_date=today_iso(),
            review_stage=0,
        )
        db.add(row)
        return row

    row.times_wrong = int(row.times_wrong or 0) + 1
    row.wrong_answer = str(wrong_answer)
    row.last_wrong_at = dt.datetime.now()
    # 关键 1：已经掌握的题又错了，说明其实没真懂，退回未掌握。
    row.mastered = False
    row.mastered_at = None
    # 关键 2：间隔梯子从头爬 —— 又错一次就得重新走一遍短期记忆
    row.review_stage = 0
    row.due_date = today_iso()
    if explain:
        row.explain = explain
    return row


def collect_from_round(
    db: Session,
    child: User,
    questions: list,
    answers: list,
    given: list,
    *,
    source: str = "game",
    subject: str = "math",
    kind: str = "mental-math",
) -> int:
    """结算一局练习，把答错的题逐道收录。返回收录条数。"""
    n = 0
    for i, ans in enumerate(answers):
        if i >= len(given):
            break
        mine = str(given[i]).strip()
        if mine == str(ans).strip():
            continue
        # 留空也算错，否则孩子不填就能绕过错题本
        q = questions[i] if i < len(questions) else {}
        record_wrong(
            db,
            child,
            question=quiz_text(q) if q else f"第 {i + 1} 题",
            correct_answer=str(ans),
            wrong_answer=mine,
            source=source,
            subject=subject,
            kind=kind,
        )
        n += 1
    return n


# ------------------------------------------------------------------ 间隔复习
# 参照艾宾浩斯遗忘曲线：第一次 1 天后，之后 2、4、7、15、30 天。
# 走到最后一档仍然答对，才算真正掌握（短期记住不算学会）。
INTERVALS = [1, 2, 4, 7, 15, 30]

# 走到第几档才算真正掌握：0=刚收进来的，1=当天订正对了，2=隔几天又对了。
# 自评「太简单」一次跳两档，所以一眼看就会的题当天就能归档。
MASTER_STAGE = 2

RATING = {
    # 孩子自评 → 档位变化、是否算对
    "forgot": (-99, False, "没关系，我们再讲一遍"),
    "hard": (-1, True, "记牢一点，明天再见它一次"),
    "ok": (1, True, "很好，隔几天再巩固一次"),
    "easy": (2, True, "这么简单啦！下次换更难的给你"),
}

CAUSES = [
    {"code": "careless", "name": "粗心大意", "icon": "💫", "tip": "会的题做错，练的是检查习惯"},
    {"code": "misread", "name": "看错题目", "icon": "👀", "tip": "读题时用手指点着读一遍"},
    {"code": "calc", "name": "算错了", "icon": "🧮", "tip": "这一块要专项练熟"},
    {"code": "unknown", "name": "真的不会", "icon": "📚", "tip": "知识点没懂，先讲再做"},
    {"code": "slow", "name": "没做完", "icon": "⏱️", "tip": "限时练几次找手感"},
    {"code": "other", "name": "其它", "icon": "📌", "tip": ""},
]

_CAUSE_MAP = {c["code"]: c for c in CAUSES}


def cause_label(code: str) -> str:
    return (_CAUSE_MAP.get(code or "") or {}).get("name", "")


def _today() -> dt.date:
    return dt.date.today()


def due_of(stage: int) -> str:
    n = max(0, min(int(stage), len(INTERVALS) - 1))
    return (_today() + dt.timedelta(days=INTERVALS[n])).isoformat()


def schedule(row: WrongQuestion, rating: str, count: bool = True) -> dict:
    """
    按孩子自评更新复习档位。

    rating: forgot 忘了 / hard 有点难 / ok 会了 / easy 太简单
    count=False 表示是订正之后「改主意」补评一次，不重复记一次准时复习次数。
    """
    step, ok, tip = RATING.get(rating, RATING["ok"])
    if count:
        row.times_reviewed = int(row.times_reviewed or 0) + 1
    if step == -99:
        row.review_stage = 0
    else:
        row.review_stage = max(0, min(len(INTERVALS) - 1,
                                      int(row.review_stage or 0) + step))
    row.due_date = due_of(row.review_stage)

    # 隔两天还能答对，才敢说「真的会了」—— 当天订正正确只代表短期记住
    if ok and int(row.review_stage) >= MASTER_STAGE:
        row.mastered = True
        row.mastered_at = dt.datetime.now()
    elif not ok:
        row.mastered = False
        row.mastered_at = None
        row.times_wrong = int(row.times_wrong or 0) + 1
        row.last_wrong_at = dt.datetime.now()
    return {"ok": ok, "tip": tip, "stage": int(row.review_stage),
            "due_date": row.due_date, "mastered": bool(row.mastered)}


def stage_state(row: WrongQuestion) -> str:
    """待复习 / 复习中 / 已掌握 —— 三态比「掌握/未掌握」更贴近真实学习过程。"""
    if row.mastered:
        return "mastered"
    return "new" if int(row.times_reviewed or 0) == 0 else "reviewing"


def review_items(db: Session, child: User, limit: int | None = None) -> list[WrongQuestion]:
    """
    今天该复习的错题：只看**到期**的。

    不是今天该复习的题不出现 —— 一次把几十道题堆到 7 岁孩子面前，
    他只会全部糊弄一遍，这就是间隔复习存在的理由。
    """
    cap = limit or int(wrong_cfg().get("review_batch_size", 8))
    today = _today().isoformat()
    rows = db.scalars(
        select(WrongQuestion)
        .where(
            WrongQuestion.child_id == child.id,
            WrongQuestion.mastered.is_(False),
            (WrongQuestion.due_date.is_(None))
            | (WrongQuestion.due_date <= today),
        )
        .order_by(WrongQuestion.due_date.asc(), WrongQuestion.times_wrong.desc())
        .limit(cap)
    ).all()
    return list(rows)


ORDER_MAP = {
    # recent: 没掌握的排前面，同状态里最近错的排前 —— 默认视图，保证先搞定最新的坑
    "recent": (WrongQuestion.mastered.asc(), WrongQuestion.last_wrong_at.desc()),
    "times": (WrongQuestion.times_wrong.desc(), WrongQuestion.last_wrong_at.desc()),
    "oldest": (WrongQuestion.last_wrong_at.asc(),),
    # manual: 家长排的打印顺序；没排过（0）的统一沉到最后
    "manual": (
        case((WrongQuestion.sort_order == 0, 999999),
             else_=WrongQuestion.sort_order).asc(),
        WrongQuestion.id.asc(),
    ),
}


def list_wrong(
    db: Session,
    child: User,
    *,
    mastered: bool | None = None,
    subject: str | None = None,
    keyword: str | None = None,
    order: str = "recent",
    limit: int = 200,
) -> list[WrongQuestion]:
    q = select(WrongQuestion).where(WrongQuestion.child_id == child.id)
    if mastered is not None:
        q = q.where(WrongQuestion.mastered.is_(mastered))
    if subject:
        q = q.where(WrongQuestion.subject == subject)
    if keyword:
        kw = f"%{keyword.strip()}%"
        q = q.where(WrongQuestion.question.ilike(kw))

    if mastered is not None and order == "recent":
        # 只看某一类时不需要再按 mastered 分堆
        q = q.order_by(WrongQuestion.last_wrong_at.desc())
    else:
        q = q.order_by(*ORDER_MAP.get(order, ORDER_MAP["recent"]))
    return list(db.scalars(q.limit(limit)).all())


# ------------------------------------------------------------------ 编辑
EDITABLE = ("question", "correct_answer", "wrong_answer", "explain",
            "subject", "cause", "tag")


def update_item(db: Session, child: User, wid: int, fields: dict) -> WrongQuestion:
    row = db.get(WrongQuestion, wid)
    if not row or row.child_id != child.id:
        raise ValueError("没有找到这道题")

    for k, v in fields.items():
        if k not in EDITABLE or v is None:
            continue
        s = str(v).strip()
        if k == "question" and not s:
            raise ValueError("题面不能为空")
        if k == "subject":
            if s not in subject_map():
                raise ValueError("没有这个科目，先去「科目管理」里加一个")
            row.subject = s
            continue
        setattr(row, k, s[:300])
    row.updated_at = dt.datetime.now()
    return row


def delete_item(db: Session, child: User, wid: int) -> None:
    row = db.get(WrongQuestion, wid)
    if not row or row.child_id != child.id:
        raise ValueError("没有找到这道题")
    db.delete(row)


def move_item(db: Session, child: User, wid: int, direction: str) -> list:
    """在自己这一批里上移 / 下移一位。返回重排后的 id 顺序，方便前端直接重画。"""
    rows = list_wrong(db, child, order="manual", limit=500)
    i = next((n for n, r in enumerate(rows) if r.id == wid), -1)
    if i < 0:
        raise ValueError("没有找到这道题")

    j = i - 1 if direction == "up" else i + 1
    if j < 0 or j >= len(rows):
        return [r.id for r in rows]

    rows[i], rows[j] = rows[j], rows[i]
    for n, r in enumerate(rows, start=1):
        r.sort_order = n
    return [r.id for r in rows]


def reset_order(db: Session, child: User) -> None:
    """一键清空手动排序，回到默认的「最近错优先」。"""
    for r in db.scalars(
        select(WrongQuestion).where(WrongQuestion.child_id == child.id)
    ).all():
        r.sort_order = 0


def renumber(db: Session, child: User) -> None:
    """把当前默认顺序固化成手动顺序，家长从这个基础上微调更省事。"""
    rows = list_wrong(db, child, order="recent", limit=500)
    for n, r in enumerate(rows, start=1):
        r.sort_order = n


# ------------------------------------------------------------------ 汇总
def summary(
    db: Session,
    child: User,
    *,
    subject: str | None = None,
    status: str = "pending",
    ids: list[int] | None = None,
    days: int | None = None,
) -> dict:
    """
    按科目分组的错题汇总 —— 打印与导出 Word 都用它。

    status: pending 没掌握 / mastered 已掌握 / all 全部
    ids:    只导出勾选题（前端复选框），为空表示全部
    """
    rows = list_wrong(db, child, order="manual", limit=500)
    if ids:
        want = set(int(x) for x in ids)
        rows = [r for r in rows if r.id in want]
    if subject:
        rows = [r for r in rows if r.subject == subject]
    if status == "pending":
        rows = [r for r in rows if not r.mastered]
    elif status == "mastered":
        rows = [r for r in rows if r.mastered]
    if days:
        since = dt.date.today() - dt.timedelta(days=int(days))
        rows = [r for r in rows if (r.last_wrong_at.date() if r.last_wrong_at else None)
                and r.last_wrong_at.date() >= since]

    order = {s["code"]: n for n, s in enumerate(subjects())}
    buckets: dict[str, list] = {}
    for r in rows:
        buckets.setdefault(r.subject, []).append(r)

    groups = []
    for code in sorted(buckets, key=lambda c: order.get(c, 99)):
        items = buckets[code]
        if not isinstance(items, list) or not items:
            continue
        groups.append(
            {
                "code": code,
                "name": subject_label(code),
                "icon": (subject_map().get(code) or {}).get("icon", "📌"),
                "count": len(items),
                "pending": sum(1 for x in items if not x.mastered),
                "items": [dto(x) for x in items],
            }
        )

    return {
        "child": {"id": child.id, "name": child.name, "avatar": child.avatar},
        "generated_at": dt.date.today().isoformat(),
        "total": sum(g["count"] for g in groups),
        "pending_total": sum(g["pending"] for g in groups),
        "groups": groups,
    }


def dto(row: WrongQuestion) -> dict:
    return {
        "id": row.id,
        "question": row.question,
        "correct_answer": row.correct_answer,
        "wrong_answer": row.wrong_answer,
        "explain": row.explain,
        "subject": row.subject,
        "subject_name": subject_label(row.subject),
        "kind": row.kind,
        "cause": row.cause or "",
        "cause_name": cause_label(row.cause),
        "tag": row.tag or "",
        "times_wrong": int(row.times_wrong or 0),
        "times_reviewed": int(row.times_reviewed or 0),
        "mastered": bool(row.mastered),
        "mastered_at": row.mastered_at.strftime("%Y-%m-%d") if row.mastered_at else "",
        "last_wrong_at": row.last_wrong_at.strftime("%Y-%m-%d"),
        "due_date": row.due_date or "",
        "review_stage": int(row.review_stage or 0),
        "next_gap": INTERVALS[min(int(row.review_stage or 0), len(INTERVALS) - 1)],
        "state": stage_state(row),
        "seq": f"#{row.id:06d}",
        "sort_order": int(row.sort_order or 0),
        "prompt": prompt_of(row.question),
    }


# ------------------------------------------------------------------ 举一反三
def variants(row: WrongQuestion, n: int = 3) -> list:
    """
    给一道错题派生同类题（离线、不用 AI）。

    算理相通才叫举一反三：两位数进位加法配同类进位题，乘法换另一个因数。
    语文/英语错题目前没有可靠的离线构题规则，宁缺毋滥 —— 返回空数组，前端自动不显示。
    """
    import random

    if row.kind not in ("mental-math",):
        return []

    q = str(row.question or "")
    import re

    m = re.match(r"^\s*(\d+)\s*([＋+\-－×*])\s*(\d+)\s*=\s*\?", q)
    if not m:
        return []

    a, sign, b = int(m.group(1)), m.group(2), int(m.group(3))
    if sign in ("＋", "+"):
        op, ops = lambda x, y: x + y, "＋"
    elif sign in ("－", "-"):
        op, ops = lambda x, y: x - y, "－"
        if b > a:
            a, b = b, a
    else:
        op, ops = lambda x, y: x * y, "×"

    out, seen = [], {f"{a}{ops}{b}"}
    rnd = random.Random(f"{row.id}-{n}")
    for _ in range(n * 6):
        if len(out) >= n:
            break
        if ops == "×":
            na, nb = (a, max(2, b + rnd.randint(-2, 2))) if rnd.random() < .5 \
                else (max(2, a + rnd.randint(-2, 2)), b)
            na, nb = max(2, na), max(2, nb)
        elif ops == "＋":
            na, nb = max(1, a + rnd.randint(-3, 3)), max(1, b + rnd.randint(-3, 3))
        else:
            na = max(2, a + rnd.randint(-3, 3))
            nb = max(1, min(na, b + rnd.randint(-3, 3)))
        key = f"{na}{ops}{nb}"
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "question": f"{na} {ops} {nb} = ?",
                "correct_answer": str(op(na, nb)),
                "prompt": f"{na} {ops} {nb} = ＿＿＿",
            }
        )
    return out


# ------------------------------------------------------------------ 学情统计
def stats(db: Session, child: User, days: int = 30) -> dict:
    """错因分布 + 分科掌握率 + 最近录入趋势。给家长判断「到底是粗心还是没懂」。"""
    rows = list_wrong(db, child, limit=1000)
    total = len(rows)

    by_subject, by_cause = {}, {}
    for r in rows:
        s = by_subject.setdefault(
            r.subject, {"code": r.subject, "name": subject_label(r.subject),
                        "total": 0, "pending": 0, "mastered": 0}
        )
        s["total"] += 1
        if r.mastered:
            s["mastered"] += 1
        else:
            s["pending"] += 1
        c = by_cause.setdefault(r.cause or "", {"code": r.cause or "",
                                                "name": cause_label(r.cause) or "没填",
                                                "count": 0})
        c["count"] += 1

    for s in by_subject.values():
        s["rate"] = int(s["mastered"] * 100 / s["total"]) if s["total"] else 0

    since = dt.date.today() - dt.timedelta(days=days - 1)
    trend = {}
    for n in range(days):
        d = (dt.date.today() - dt.timedelta(days=n)).isoformat()
        trend[d] = 0
    for r in rows:
        d = r.last_wrong_at.date().isoformat() if r.last_wrong_at else ""
        if d and d >= since.isoformat():
            trend[d] = trend.get(d, 0) + 1
    series = [{"date": d, "count": trend[d]} for d in sorted(trend)]

    due_today = sum(
        1 for r in rows
        if not r.mastered and (not r.due_date or r.due_date <= today_iso())
    )
    return {
        "total": total,
        "pending": sum(1 for r in rows if not r.mastered),
        "mastered": sum(1 for r in rows if r.mastered),
        "master_rate": int(sum(1 for r in rows if r.mastered) * 100 / total) if total else 0,
        "due_today": due_today,
        "by_subject": sorted(by_subject.values(), key=lambda x: -x["total"]),
        "by_cause": sorted(by_cause.values(), key=lambda x: -x["count"]),
        "trend": series,
        "days": days,
    }
