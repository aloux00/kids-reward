# -*- coding: utf-8 -*-
"""
孩子端。三条铁律：
1. 响应里永远不含累计获得总数（只有"可用余额"），避免孩子把"攒过多少"误当成"能花多少"。
2. 没有任何创建任务的入口 —— 家长是唯一发布者。
3. 所有 reassemble 都经过 PointService，孩子端无法绕过每日上限。
"""
from __future__ import annotations

import datetime as dt
import json
import math
import random

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import load_rules, today_str
from ..db import get_db
from ..deps import current_user, require_child
from ..models import (
    Achievement,
    GameSession,
    PointApplication,
    PointLedger,
    Redemption,
    TaskRecord,
    TaskTemplate,
    User,
    UserAchievement,
    WrongQuestion,
    Wish,
)
from ..security import sign_answer, verify_answer
from ..serializers import (
    achievement_wall,
    achievements_of,
    assigned_to,
    certificate_of,
    date_matches,
    kid_brief,
    ledger_rows,
    level_events,
    list_today_tasks,
    list_wishes,
)
from ..services import (
    PointService,
    add_audit,
    collect_from_round,
    expire_applications,
    level_info,
)
from ..services.wrong import review_items as _due_items

router = APIRouter(prefix="/api/child", tags=["child"])

CAP_TYPES = ["task", "application", "game", "manual", "streak", "bonus"]


# ------------------------------------------------------------------ 首页
@router.get("/home")
def home(user: User = Depends(require_child), db: Session = Depends(get_db)):
    """
    首页。注意响应中没有 total_earned —— 孩子端累计总数从接口层就切断了。
    """
    rules = load_rules()
    ps = PointService(db)
    biz = today_str()

    summary = ps.coin_summary(user)
    exp = ps.exp_total(user.id)
    li = level_info(exp, rules)

    today_tasks, extra_tasks = list_today_tasks(db, user, biz)

    avg7 = ps.daily_average(user.id)
    wishes = list_wishes(db, user, ps)

    # 今天还能赚多少：各分类上限合计 - 今天已得
    total_cap = sum(int(v) for v in (rules.get("daily_cap") or {}).values())
    today_earned = ps.earned_total_today(user.id, biz)
    daily_remain = max(0, total_cap - today_earned)

    game_cfg = (rules.get("games") or [{}])[0]
    played_today = int(
        db.scalar(
            select(func.count())
            .select_from(GameSession)
            .where(GameSession.child_id == user.id, GameSession.biz_date == biz)
        )
        or 0
    )

    return {
        "profile": {
            "name": user.name,
            "avatar": user.avatar,
            "ui_mode": user.ui_mode,
            "level": li.get("level", 1),
            "level_title": li.get("title", ""),
            "level_perk": li.get("perk", ""),
            "streak_days": user.streak_days or 0,
            "display_title": _display_title(db, user),
        },
        "coin": {
            "available": summary["available"],
            "frozen": summary["frozen"],
            "daily_remain": daily_remain,
            "today_earned": today_earned,
        },
        "exp": {
            "total": exp,
            "level": li.get("level"),
            "next_level": li.get("next_level"),
            "next_title": li.get("next_title"),
            "next_perk": li.get("next_perk"),
            "to_next": li.get("to_next"),
            "percent": li.get("percent"),
            "max_level": li.get("max_level"),
        },
        "wishes": wishes,
        "today_tasks": today_tasks,
        "extra_tasks": extra_tasks,
        "game": {
            "code": game_cfg.get("code", "math"),
            "name": game_cfg.get("name", ""),
            "icon": game_cfg.get("icon", "🎮"),
            "enabled": bool(game_cfg.get("enabled")),
            "played_today": played_today,
            "limit": int((rules.get("gating") or {}).get("game_daily_play_limit", 3)),
            "unlocked": _game_unlocked(db, user, today_tasks, rules),
        },
        # 首页就告诉孩子「今天有几道错题等着」——
        # 错题本如果藏在深处没人进去，做错过的题就白错了。
        # 只算「今天到期」的，问隔复习的意义就是不让一堆题同时压过来。
        "wrong_pending": len(_due_items(db, user)),
    }


def _display_title(db, child: User) -> str:
    from ..models import UserAchievement

    code = child.display_title_code
    if code:
        a = db.scalar(select(Achievement).where(Achievement.code == code))
        if a:
            return a.name
    return ""


# ------------------------------------------------------------------ 打卡
class CheckinIn(BaseModel):
    template_id: int
    evidence_text: str = ""
    evidence_image: str = ""


@router.post("/checkin")
def checkin(body: CheckinIn, user: User = Depends(require_child),
            db: Session = Depends(get_db)):
    biz = today_str()
    ps = PointService(db)

    tpl = db.get(TaskTemplate, body.template_id)
    # 租户隔离：任务必须属于同一个家庭
    if not tpl or tpl.family_id != user.family_id or not tpl.active:
        raise HTTPException(404, "任务不存在")

    if not date_matches(tpl, biz) or not assigned_to(tpl, user.id):
        raise HTTPException(400, "这个任务今天不用做哦")

    dup = db.scalar(
        select(TaskRecord).where(
            TaskRecord.child_id == user.id,
            TaskRecord.template_id == tpl.id,
            TaskRecord.biz_date == biz,
        )
    )
    if dup:
        if dup.status == "rejected":
            # 被驳回后允许重做，更新原记录而不是新开一条，保持"一天一次"
            dup.status = "pending"
            dup.evidence_text = body.evidence_text
            dup.evidence_image = body.evidence_image
            dup.submitted_at = dt.datetime.now()
            dup.reject_reason = ""
            db.commit()
            return {"ok": True, "status": "pending", "points": 0, "resubmit": True}
        raise HTTPException(400, "今天已经打过卡啦")

    if tpl.need_photo and not body.evidence_image:
        raise HTTPException(400, "这个任务要拍张照片给爸爸妈妈看看 📷")

    rec = TaskRecord(
        family_id=user.family_id,
        child_id=user.id,
        template_id=tpl.id,
        biz_date=biz,
        status="pending" if tpl.need_approval else "approved",
        evidence_text=body.evidence_text[:400],
        evidence_image=body.evidence_image,
        submitted_at=dt.datetime.now(),
    )
    db.add(rec)
    db.flush()

    granted = 0
    capped = False
    streak_bonus = 0

    if not tpl.need_approval:
        # 无需审批的任务直接入账
        res = ps.grant(
            user,
            tpl.points,
            source_type="task",
            category=tpl.category,
            source_id=rec.id,
            note=tpl.name,
            operator_id=user.id,
            biz_date=biz,
        )
        granted = res["granted"]
        capped = res["capped"]
        rec.awarded_coin = granted
        rec.reviewer_id = user.id
        rec.reviewed_at = dt.datetime.now()
        add_audit(db, user.family_id, user.id, "auto_approve_task", "task_record", rec.id, tpl.name)
    else:
        add_audit(db, user.family_id, user.id, "submit_task", "task_record", rec.id, tpl.name)

    if granted > 0 or not tpl.need_approval:
        sr = ps.update_streak(user, biz)
        streak_bonus = sr.get("bonus", 0)
        ps.check_achievements(user)

    db.commit()
    return {
        "ok": True,
        "status": rec.status,
        "points": granted,
        "capped": capped,
        "streak_bonus": streak_bonus,
    }


# ------------------------------------------------------------------ 加分申请
class ApplyIn(BaseModel):
    title: str
    points: int = 5
    category: str = "habit"
    evidence_text: str = ""
    evidence_image: str = ""


@router.post("/apply")
def apply_points(body: ApplyIn, user: User = Depends(require_child),
                 db: Session = Depends(get_db)):
    """「我今天还想加分」—— 三重约束全部在这里生效。"""
    rules = load_rules()
    cfg = rules.get("application") or {}
    biz = today_str()

    if not cfg.get("enabled", True):
        raise HTTPException(403, "加分申请没有开启哦")

    used = int(
        db.scalar(
            select(func.count())
            .select_from(PointApplication)
            .where(
                PointApplication.child_id == user.id,
                PointApplication.biz_date == biz,
                PointApplication.status.in_(["pending", "approved"]),
            )
        )
        or 0
    )
    if used >= int(cfg.get("daily_limit", 2)):
        raise HTTPException(400, f"今天的申请次数用完啦，明天再来吧")

    max_points = int(cfg.get("max_points_per_apply", 10))
    points = max(1, min(int(body.points), max_points))

    if cfg.get("require_evidence", True) and not (body.evidence_text or body.evidence_image):
        raise HTTPException(400, "写一句话或者拍张照片，爸爸妈妈才知道你做了什么 😊")

    app = PointApplication(
        family_id=user.family_id,
        child_id=user.id,
        title=body.title.strip()[:40],
        points=points,
        category=body.category,
        biz_date=biz,
        evidence_text=body.evidence_text[:400],
        evidence_image=body.evidence_image,
    )
    db.add(app)
    db.commit()
    return {"ok": True, "id": app.id, "points": points,
            "remain_today": max(0, int(cfg.get("daily_limit", 2)) - used - 1)}


@router.get("/applications")
def my_applications(user: User = Depends(require_child), db: Session = Depends(get_db)):
    expire_applications(db, family_id=user.family_id)
    rows = db.scalars(
        select(PointApplication)
        .where(PointApplication.child_id == user.id)
        .order_by(PointApplication.id.desc())
        .limit(20)
    ).all()
    return [
        {
            "id": r.id,
            "title": r.title,
            "points": r.points,
            "awarded": r.awarded_coin,
            "status": r.status,
            "reject_reason": r.reject_reason,
            "date": r.biz_date,
        }
        for r in rows
    ]


# ------------------------------------------------------------------ 愿望
class WishIn(BaseModel):
    """孩子许愿只描述"想要什么"。

    需要多少星星币不在这里 —— 那是家长定的价。孩子自己填价，
    要么往低了填好快点兑换，要么往高了填根本攒不到，两头都不对。
    """

    title: str
    note: str = ""
    cover_image: str = ""
    target_date: str | None = None


@router.get("/wishes")
def get_wishes(user: User = Depends(require_child), db: Session = Depends(get_db)):
    ps = PointService(db)
    return {"wishes": list_wishes(db, user, ps)}


@router.post("/wish")
def create_wish(body: WishIn, user: User = Depends(require_child),
                db: Session = Depends(get_db)):
    """
    许愿免费、无门槛 —— 先有目标再攒星星币。
    多名孩子并存时，愿望各自独立，不与他人比较。

    新建的愿望一律 cost_coin = 0（待家长定价），
    家长确认时才会给出具体数字。
    """
    count = int(
        db.scalar(
            select(func.count())
            .select_from(Wish)
            .where(Wish.child_id == user.id, Wish.status.in_(["pending", "active"]))
        )
        or 0
    )
    if count >= 5:
        raise HTTPException(400, "在进行的愿望最多 5 个，先实现几个再许新的吧")

    # 第一个愿望自动成为主目标
    is_first = count == 0
    w = Wish(
        family_id=user.family_id,
        child_id=user.id,
        title=body.title.strip()[:40],
        note=body.note[:200],
        cover_image=body.cover_image,
        cost_coin=0,                    # 待家长定价
        priority=1 if is_first else 0,
        status="pending",
        target_date=body.target_date or None,
    )
    db.add(w)
    db.commit()
    add_audit(db, user.family_id, user.id, "create_wish", "wish", w.id, w.title)
    return {"ok": True, "id": w.id, "need_parent_confirm": True, "need_price": True}


@router.post("/wish/{wish_id}/primary")
def set_primary(wish_id: int, user: User = Depends(require_child),
                db: Session = Depends(get_db)):
    w = db.get(Wish, wish_id)
    if not w or w.child_id != user.id:
        raise HTTPException(404, "愿望不存在")
    others = db.scalars(
        select(Wish).where(
            Wish.child_id == user.id, Wish.status.in_(["pending", "active"])
        )
    ).all()
    for o in others:
        o.priority = 1 if o.id == wish_id else 0
    db.commit()
    return {"ok": True}


@router.delete("/wish/{wish_id}")
def abandon_wish(wish_id: int, user: User = Depends(require_child),
                 db: Session = Depends(get_db)):
    """放弃不扣分 —— 星星币是通用账户，不属于任何一个愿望。"""
    w = db.get(Wish, wish_id)
    if not w or w.child_id != user.id:
        raise HTTPException(404, "愿望不存在")
    pending_rdm = db.scalar(
        select(Redemption).where(
            Redemption.wish_id == w.id, Redemption.status == "pending"
        )
    )
    if pending_rdm:
        pending_rdm.status = "cancelled"
    w.status = "abandoned"
    db.commit()
    return {"ok": True}


class WishEditIn(BaseModel):
    """孩子编辑自己还没结束的愿望：改文案、配图、目标日期都行。

    不能改星星币（那是家长定的），也不能改已确认/已实现/已放弃的。
    """

    title: str | None = None
    note: str | None = None
    cover_image: str | None = None
    target_date: str | None = None


@router.put("/wish/{wish_id}")
def edit_wish(wish_id: int, body: WishEditIn,
              user: User = Depends(require_child), db: Session = Depends(get_db)):
    w = db.get(Wish, wish_id)
    if not w or w.child_id != user.id:
        raise HTTPException(404, "愿望不存在")
    if w.status in ("completed", "abandoned"):
        raise HTTPException(400, "这个愿望已经结束了，改不了啦")

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

    db.commit()
    add_audit(db, user.family_id, user.id, "edit_wish", "wish", w.id, w.title)
    return {"ok": True}


# ------------------------------------------------------------------ 兑换
@router.post("/redeem/{wish_id}")
def redeem(wish_id: int, user: User = Depends(require_child),
           db: Session = Depends(get_db)):
    """兑换。提交即冻结，家长核销时才真正扣除。"""
    rules = load_rules()
    ps = PointService(db)

    w = db.get(Wish, wish_id)
    if not w or w.child_id != user.id or w.status != "active":
        raise HTTPException(404, "愿望还没通过爸爸妈妈确认哦")

    if w.cost_coin <= 0:
        # 没定价就让它兑换，等于 0 星白拿 —— 必须拦在前面
        raise HTTPException(400, "爸爸妈妈还没给这个愿望定星星币，请他们先定一下哦")

    exist = db.scalar(
        select(Redemption).where(
            Redemption.wish_id == w.id, Redemption.status == "pending"
        )
    )
    if exist:
        raise HTTPException(400, "兑换申请已经提交啦，等爸爸妈妈确认")

    available = ps.available_coin(user.id)
    if available < w.cost_coin:
        raise HTTPException(
            400,
            f"还差 {w.cost_coin - available} 颗星星币，加油！",
        )

    auto = int((rules.get("redemption") or {}).get("auto_approve_below", 0))
    rdm = Redemption(
        family_id=user.family_id,
        child_id=user.id,
        wish_id=w.id,
        cost_coin=w.cost_coin,
        status="pending",
    )
    db.add(rdm)
    db.flush()

    if auto > 0 and w.cost_coin <= auto:
        rdm.status = "fulfilled"
        rdm.handled_at = dt.datetime.now()
        w.status = "completed"
        w.completed_at = dt.datetime.now()
        ps.spend(user, w.cost_coin, source_id=rdm.id, note=w.title, operator_id=user.id)
        add_audit(db, user.family_id, user.id, "auto_redeem", "redemption", rdm.id, w.title)

    db.commit()
    return {"ok": True, "mode": "fulfilled" if rdm.status == "fulfilled" else "pending"}


# ------------------------------------------------------------------ 小游戏
def _game_cfg() -> dict:
    rules = load_rules()
    games = rules.get("games") or []
    return games[0] if games else {}


def _game_unlocked(db, child: User, today_tasks: list, rules: dict) -> bool:
    gating = rules.get("gating") or {}
    if not gating.get("game_unlock_after_study", True):
        return True
    study_tasks = [t for t in today_tasks if t["category"] == "study"]
    if not study_tasks:
        return True
    return all(t["status"] == "approved" for t in study_tasks)


@router.get("/game/round")
def game_round(code: str = "math", user: User = Depends(require_child),
               db: Session = Depends(get_db)):
    """
    服务端出题 + 签名。前端只负责展示题目和收集答案，
    分数由服务端判定，孩子无法通过改前端代码给自己加分。
    """
    rules = load_rules()
    biz = today_str()
    cfg = _game_cfg()
    if not cfg.get("enabled"):
        raise HTTPException(403, "游戏没有开启")

    limit = int((rules.get("gating") or {}).get("game_daily_play_limit", 3))
    played = int(
        db.scalar(
            select(func.count())
            .select_from(GameSession)
            .where(GameSession.child_id == user.id, GameSession.biz_date == biz)
        )
        or 0
    )
    if played >= limit:
        raise HTTPException(400, "今天的游戏次数用完啦，明天再来 ⏳")

    all_today, _ = list_today_tasks(db, user, biz)
    if not _game_unlocked(db, user, all_today, rules):
        raise HTTPException(400, "先把今天的学习任务完成，游戏就解锁啦 🔓")

    n = int(cfg.get("questions", 10))
    ops = cfg.get("ops", ["+", "-"])
    rmax = int(cfg.get("range_max", 20))
    questions, answers = [], []
    for _ in range(n):
        op = random.choice(ops)
        if op == "+":
            a = random.randint(1, max(2, rmax - 1))
            b = random.randint(1, max(1, rmax - a))
            ans = a + b
        elif op == "-":
            a = random.randint(2, rmax)
            b = random.randint(1, a)
            ans = a - b
        elif op == "*":
            a = random.randint(2, 9)
            b = random.randint(2, 9)
            ans = a * b
        else:
            a, b, ans = 1, 1, 2
        questions.append({"a": a, "op": op, "b": b})
        answers.append(ans)

    token = sign_answer(
        {
            "uid": user.id,
            "code": code,
            "d": biz,
            "seq": played + 1,
            "ans": answers,
            # 题面也签进来：服务端结算时需要知道「错的是哪道题」才能进错题本。
            # 因为有签名，孩子改不掉，等价于服务端自己存了题。
            "qs": questions,
        }
    )
    return {
        "round_token": token,
        "questions": questions,
        "time_limit": int(cfg.get("time_limit", 90)),
        "played_today": played,
        "limit": limit,
        "points_per_correct": int(cfg.get("points_per_correct", 1)),
        "clear_bonus": int(cfg.get("clear_bonus", 2)),
    }


class GameSubmitIn(BaseModel):
    round_token: str
    answers: list
    used_seconds: int = 0


@router.post("/game/submit")
def game_submit(body: GameSubmitIn, user: User = Depends(require_child),
                db: Session = Depends(get_db)):
    cfg = _game_cfg()
    ps = PointService(db)
    biz = today_str()

    key = verify_answer(body.round_token)
    if not key or key.get("uid") != user.id or key.get("d") != biz:
        raise HTTPException(400, "这一局已经失效，请重新开始")

    played_now = int(
        db.scalar(
            select(func.count())
            .select_from(GameSession)
            .where(GameSession.child_id == user.id, GameSession.biz_date == biz)
        )
        or 0
    )
    # 防重放：题面序号必须正好是下一局，重复提交会被拒绝
    if played_now + 1 != int(key.get("seq", -1)):
        raise HTTPException(400, "这一局已经提交过啦")

    answers = [str(x).strip() for x in body.answers]
    right = [str(a).strip() for a in key.get("ans", [])]
    correct = sum(1 for i, a in enumerate(right) if i < len(answers) and answers[i] == a)

    total = len(right)
    used = max(0, int(body.used_seconds))

    # ---- 用时校验 ---------------------------------------------------------
    # 倒计时原本只在前端跑，服务端从不检查，等于"慢慢查答案也能拿满分"。
    # 这里补上两道判定，但要留足误差空间，不能误伤手慢的小朋友。
    min_sec = max(3, int(total * float(cfg.get("min_seconds_per_question", 1.2))))
    if total >= 3 and used < min_sec:
        # 快得不可能是人答的。不入账、不记这局，让他重做即可 ——
        # 关键是别消耗当日局数，否则误判一次就少一次机会，太伤。
        raise HTTPException(
            400, f"这一局太快啦，看起来没有认真算。再试一次吧")

    overtime = used > int(cfg.get("time_limit", 90)) + 15

    cleared = correct == total and total > 0 and not overtime
    points = correct * int(cfg.get("points_per_correct", 1)) + (
        int(cfg.get("clear_bonus", 2)) if cleared else 0
    )

    sess = GameSession(
        family_id=user.family_id,
        child_id=user.id,
        game_code=key.get("code", "math"),
        correct_count=correct,
        total_count=total,
        cleared=cleared,
        used_seconds=used,
        points=points,
        biz_date=biz,
    )
    db.add(sess)
    db.flush()

    # ---- 自动收录错题 -------------------------------------------------
    # 做错了不是终点 —— 沉淀下来让孩子有能力回头看，这是练习真正的价值。
    new_wrong = collect_from_round(
        db,
        user,
        key.get("qs", []),
        right,
        answers,
        source="game",
        subject="math",
        kind="mental-math",
    )
    db.flush()

    res = ps.grant(
        user,
        points,
        source_type="game",
        category="game",
        source_id=sess.id,
        note=f"{cfg.get('name','小游戏')} 答对 {correct}/{len(right)}",
        operator_id=user.id,
        biz_date=biz,
    )
    sess.points = res["granted"]
    db.commit()

    return {
        "ok": True,
        "correct": correct,
        "total": len(right),
        "cleared": cleared,
        "points": res["granted"],
        "capped": res["capped"],
        "overtime": overtime,
        "note": "这次超时啦，答案对了得分还在，通关奖励下次再拿"
        if overtime else "",
        "played_today": played_now + 1,
        "limit": int((load_rules().get("gating") or {}).get("game_daily_play_limit", 3)),
        "new_wrong": new_wrong,
    }


# ------------------------------------------------------------------ 错题本
@router.get("/wrong")
def wrong_list(
    user: User = Depends(require_child),
    db: Session = Depends(get_db),
    subject: str | None = None,
    order: str = Query("recent", pattern="^(recent|times|oldest|manual)$"),
    keyword: str | None = None,
):
    """错题本。subject / order / keyword 用于孩子自己按学科翻查。"""
    from ..services.wrong import dto, list_wrong, review_items, subjects, wrong_cfg

    pending = review_items(db, user)
    all_wrong = list_wrong(db, user)
    cfg = wrong_cfg()
    return {
        "review": [dto(r) for r in pending],
        "total_pending": sum(1 for r in all_wrong if not r.mastered),
        "total_mastered": sum(1 for r in all_wrong if r.mastered),
        "list": [dto(r) for r in all_wrong],
        "filtered": [
            dto(r)
            for r in list_wrong(
                db, user, subject=subject, order=order, keyword=keyword
            )
        ],
        "subjects": subjects(),
        "filter": {"subject": subject or "", "order": order, "keyword": keyword or ""},
        "all_clear": (
            "太棒了，错题本空空的！继续保持 🎉" if not pending else ""
        ),
        "review_bonus": int(cfg.get("review_all_correct_points", 2)),
    }


class WrongReviewIn(BaseModel):
    answers: list
    ratings: list = []      # 孩子自评：hard / ok / easy，没选就按 "会了" 处理


@router.post("/wrong/review")
def wrong_review(body: WrongReviewIn, user: User = Depends(require_child),
                 db: Session = Depends(get_db)):
    """
    提交一组重做结果。全对给少量奖励 —— 目的是奖励「真的搞懂了」，
    所以给分刻意压得很低，绝不能让刷错题本比乖乖打卡更划算。

    批改之后按孩子的自评排下一次复习时间（1/2/4/7/15/30 天）：
    答错 = 明天重来；答对且觉得简单 = 直接跳两档。
    这样「今天说会了、明天又不会」的情况会被自动抓出来。
    """
    from ..services.wrong import dto, review_items, schedule, wrong_cfg

    items = review_items(db, user)
    if not items:
        raise HTTPException(400, "今天没有到期的错题，明天再来吧 ✨")

    given = [str(x).strip() for x in body.answers]
    ratings = [str(x) for x in (body.ratings or [])]
    results, right_n = [], 0
    for i, row in enumerate(items):
        mine = given[i] if i < len(given) else ""
        ok = mine != "" and mine == str(row.correct_answer).strip()
        rating = "forgot"
        if ok:
            r = ratings[i] if i < len(ratings) else ""
            rating = r if r in ("hard", "easy") else "ok"
        res = schedule(row, rating)
        results.append({
            "id": row.id,
            "seq": dto(row)["seq"],
            "question": row.question,
            "correct": ok,
            "your": mine,
            "answer": row.correct_answer,
            "due_date": res["due_date"],
            "next_gap": dto(row)["next_gap"],
            "mastered": res["mastered"],
            "tip": res["tip"],
            "rating": rating,
        })
        if ok:
            right_n += 1

    cfg = wrong_cfg()
    all_ok = right_n == len(items)
    bonus_cfg = int(cfg.get("review_all_correct_points", 2))
    points = bonus_cfg if all_ok else 0
    granted, capped = 0, False
    if points > 0:
        ps = PointService(db)
        # 走 study 分类：错题订正是学习活动，天然受学习类每日上限约束
        res = ps.grant(
            user,
            points,
            source_type="wrong_review",
            category="study",
            source_id=0,
            note="错题全改对啦",
            operator_id=user.id,
            biz_date=today_str(),
        )
        granted, capped = res["granted"], res["capped"]

    db.commit()
    return {
        "ok": True,
        "results": results,
        "right": right_n,
        "total": len(items),
        "all_correct": all_ok,
        "points": granted,
        "capped": capped,
        "note": "全部改对了，真棒！🧠"
        if all_ok
        else f"改对 {right_n}/{len(items)}，明天再来一次就一定行",
        "left": sum(1 for r in items if not r.mastered),
        # 下一次复习的时间，告诉孩子什么时候再见它
        "next_due": min([r["due_date"] for r in results] or [today_str()]),
    }


@router.get("/wrong/{wid}/variants")
def wrong_variants(wid: int, user: User = Depends(require_child),
                   db: Session = Depends(get_db)):
    """举一反三：给这道错题派生几道同类题（离线规则，不用 AI）。"""
    from ..services.wrong import variants

    row = db.get(WrongQuestion, wid)
    if not row or row.child_id != user.id:
        raise HTTPException(404, "没有找到这道题")
    return {"id": wid, "question": row.question, "variants": variants(row)}


@router.post("/wrong/{wid}/rate")
def wrong_rate(wid: int,
               rating: str = Query("ok", pattern="^(forgot|hard|ok|easy)$"),
               adjust: int = 0,
               user: User = Depends(require_child),
               db: Session = Depends(get_db)):
    """补一次自评（订正时选了会了，回家发现其实还是有点蒙）。"""
    from ..services.wrong import dto, schedule

    row = db.get(WrongQuestion, wid)
    if not row or row.child_id != user.id:
        raise HTTPException(404, "没有找到这道题")
    res = schedule(row, rating, count=not bool(adjust))
    db.commit()
    return {"ok": True, "id": wid, **res, "item": dto(row)}


@router.post("/wrong/{wid}/forget")
def wrong_forget(wid: int, user: User = Depends(require_child),
                 db: Session = Depends(get_db)):
    """把已掌握的题重新放回错题本（比如家长发现孩子其实还没懂）。"""
    row = db.get(WrongQuestion, wid)
    if not row or row.child_id != user.id:
        raise HTTPException(404, "没有找到这道题")
    row.mastered = False
    row.mastered_at = None
    db.commit()
    return {"ok": True, "id": row.id}


# ------------------------------------------------------------------ 我的
@router.get("/me/detail")
def me_detail(user: User = Depends(require_child), db: Session = Depends(get_db)):
    from ..services.level import all_levels

    rules = load_rules()
    ps = PointService(db)
    exp = ps.exp_total(user.id)

    return {
        "profile": kid_brief(db, user, ps),
        "level_now": level_info(exp, rules),
        "levels": all_levels(rules),
        "level_events": level_events(db, user),
        "achievements": achievements_of(db, user),
        "achievement_wall": achievement_wall(db, user, ps),
        "display_title_code": user.display_title_code or "",
        "display_title": _display_title(db, user),
        "ledger": ledger_rows(db, user, days=14),
        "wish_done": [
            {
                "id": w.id,
                "title": w.title,
                "cover": w.cover_image,
                "cost": w.cost_coin,
                "at": w.completed_at.strftime("%Y-%m-%d") if w.completed_at else "",
            }
            for w in db.scalars(
                select(Wish).where(
                    Wish.child_id == user.id, Wish.status == "completed"
                ).order_by(Wish.completed_at.desc())
            ).all()
        ],
    }


# ------------------------------------------------------------------ 荣誉
class TitleIn(BaseModel):
    code: str = ""


@router.post("/title")
def set_display_title(body: TitleIn, user: User = Depends(require_child),
                      db: Session = Depends(get_db)):
    """自选展示称号。

    只能从"已经拿到手"的称号里挑 —— 想展示一个称号，就得先去挣它。
    传空字符串表示不展示（回到只显示等级称号）。
    """
    code = (body.code or "").strip()
    if not code:
        # 该列非空，"未选择称号" 用空字符串表示
        user.display_title_code = ""
        db.commit()
        return {"ok": True, "display_title": "", "code": ""}

    a = db.scalar(
        select(Achievement).where(
            Achievement.family_id == user.family_id, Achievement.code == code
        )
    )
    if not a:
        raise HTTPException(404, "没有这个称号")
    owned = db.scalar(
        select(UserAchievement).where(
            UserAchievement.child_id == user.id,
            UserAchievement.achievement_id == a.id,
        )
    )
    if not owned:
        raise HTTPException(403, "还没有获得这个称号哦，加油！")

    user.display_title_code = code
    db.commit()
    return {"ok": True, "display_title": a.name, "code": a.code}


@router.get("/certificate")
def certificate(user: User = Depends(require_child), db: Session = Depends(get_db)):
    """荣誉证书数据。孩子端用它渲染一张可以打印 / 保存成图片的证书。"""
    ps = PointService(db)
    return certificate_of(db, user, ps)
