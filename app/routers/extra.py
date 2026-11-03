# -*- coding: utf-8 -*-
"""
扩展模块路由：星星花园 / 番茄钟 / 识字闯关 / 宠物 / 家长学堂。

设计上刻意独立成一个文件：
这些功能是后加的，单独存放可以避免动到已经跑稳的主流程，
将来要拆成独立应用也可以整块搬走。

所有加分依旧只有一条路径 —— PointService，
这里没有任何一处自己改余额。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import today_str
from ..db import get_db
from ..deps import require_child, require_parent
from ..models import GameSession, User
from ..security import sign_answer, verify_answer
from ..services import PointService
from ..services import focus as FS
from ..services import garden as GD
from ..services import pets as PT
from ..services import school as SC
from ..services import wordgame as WD

child_router = APIRouter(prefix="/api/child", tags=["extra-child"])
parent_router = APIRouter(prefix="/api/parent", tags=["extra-parent"])

WORDS_LOG_CODE = "words"


def _ps(db) -> PointService:
    return PointService(db)


def _bad(fn):
    """统一把业务层的 ValueError 转成 400，不让异常漏到前端变成 500。"""
    try:
        return fn()
    except ValueError as e:
        raise HTTPException(400, str(e))


# ================================================================== 星星花园
@child_router.get("/garden")
def garden_view(user: User = Depends(require_child), db: Session = Depends(get_db)):
    ps = _ps(db)
    st = GD.state(db, user)
    st["coins"] = ps.coin_summary(user)
    return st


class SlotIn(BaseModel):
    slot: int
    code: str = ""


@child_router.post("/garden/plant")
def garden_plant(body: SlotIn, user: User = Depends(require_child),
                 db: Session = Depends(get_db)):
    ps = _ps(db)
    def _run():
        r = GD.plant(db, user, ps, body.slot, body.code)
        db.commit()
        return r
    r = _bad(_run)
    r["coins"] = ps.coin_summary(user)
    return r


@child_router.post("/garden/water")
def garden_water(body: SlotIn, user: User = Depends(require_child),
                 db: Session = Depends(get_db)):
    def _run():
        r = GD.water(db, user, body.slot)
        db.commit()
        return r
    return _bad(_run)


@child_router.post("/garden/harvest")
def garden_harvest(body: SlotIn, user: User = Depends(require_child),
                   db: Session = Depends(get_db)):
    ps = _ps(db)
    def _run():
        r = GD.harvest(db, user, ps, body.slot)
        db.commit()
        return r
    r = _bad(_run)
    r["coins"] = ps.coin_summary(user)
    return r


# ================================================================== 番茄钟
@child_router.get("/focus")
def focus_view(user: User = Depends(require_child), db: Session = Depends(get_db)):
    return FS.state(db, user)


class FocusStartIn(BaseModel):
    minutes: int = 15
    topic: str = ""


@child_router.post("/focus/start")
def focus_start(body: FocusStartIn, user: User = Depends(require_child),
                db: Session = Depends(get_db)):
    def _run():
        r = FS.start(db, user, body.minutes, body.topic)
        db.commit()
        return r
    return _bad(_run)


class FocusEndIn(BaseModel):
    session_id: int
    mode: str = "finish"      # finish / abort


@child_router.post("/focus/end")
def focus_end(body: FocusEndIn, user: User = Depends(require_child),
              db: Session = Depends(get_db)):
    ps = _ps(db)
    if body.mode == "abort":
        def _run():
            r = FS.abort(db, user, body.session_id)
            db.commit()
            return r
        return _bad(_run)

    def _run():
        r = FS.finish(db, user, ps, body.session_id)
        db.commit()
        return r
    r = _bad(_run)
    r["coins"] = ps.coin_summary(user)
    return r


# ================================================================== 每日识字
@child_router.get("/word/today")
def word_today(user: User = Depends(require_child), db: Session = Depends(get_db)):
    return WD.today_cards(db, user)


class WordMarkIn(BaseModel):
    key: str
    known: bool = True


@child_router.post("/word/mark")
def word_mark(body: WordMarkIn, user: User = Depends(require_child),
              db: Session = Depends(get_db)):
    def _run():
        r = WD.mark(db, user, body.key, body.known)
        db.commit()
        return r
    return _bad(_run)


@child_router.get("/word/round")
def word_round(user: User = Depends(require_child), db: Session = Depends(get_db)):
    """服务端出题 + 签名。和速算闯关一样，答案孩子改不了。"""
    cfg = WD.round_cfg()
    if not cfg["enabled"]:
        raise HTTPException(403, "识字闯关没有开启")

    biz = today_str()
    played = int(
        db.scalar(
            select(func.count())
            .select_from(GameSession)
            .where(
                GameSession.child_id == user.id,
                GameSession.biz_date == biz,
                GameSession.game_code == WORDS_LOG_CODE,
            )
        )
        or 0
    )
    if played >= cfg["daily_limit"]:
        raise HTTPException(400, "今天的识字闯关次数用完啦，明天再来 \U0001F4DA")

    bundle = WD.build_round(cfg["questions"])
    token = sign_answer(
        {
            "uid": user.id,
            "code": WORDS_LOG_CODE,
            "d": biz,
            "seq": played + 1,
            "ans": bundle["answers"],
            "qs": bundle["questions"],
        }
    )
    return {
        "round_token": token,
        "questions": [
            {k: v for k, v in q.items() if k != "explain"} for q in bundle["questions"]
        ],
        "played_today": played,
        "limit": cfg["daily_limit"],
        "points_per_correct": cfg["points_per_correct"],
        "clear_bonus": cfg["clear_bonus"],
    }


class WordSubmitIn(BaseModel):
    round_token: str
    answers: list
    used_seconds: int = 0


@child_router.post("/word/submit")
def word_submit(body: WordSubmitIn, user: User = Depends(require_child),
                db: Session = Depends(get_db)):
    cfg = WD.round_cfg()
    biz = today_str()
    key = verify_answer(body.round_token)
    if not key or key.get("uid") != user.id or key.get("d") != biz:
        raise HTTPException(400, "这一局已经失效，请重新开始")

    played_now = int(
        db.scalar(
            select(func.count())
            .select_from(GameSession)
            .where(
                GameSession.child_id == user.id,
                GameSession.biz_date == biz,
                GameSession.game_code == WORDS_LOG_CODE,
            )
        )
        or 0
    )
    if played_now + 1 != int(key.get("seq", -1)):
        raise HTTPException(400, "这一局已经提交过啦")

    right = [str(x).strip() for x in key.get("ans", [])]
    given = [str(x).strip() for x in body.answers]
    correct = sum(1 for i, a in enumerate(right) if i < len(given) and given[i] == a)
    total = len(right)

    used = max(0, int(body.used_seconds))
    if total >= 3 and used < 3:
        raise HTTPException(400, "这一局太快啦，再认真看一遍吧")

    cleared = correct == total and total > 0
    points = correct * cfg["points_per_correct"] + (
        cfg["clear_bonus"] if cleared else 0
    )

    sess = GameSession(
        family_id=user.family_id,
        child_id=user.id,
        game_code=WORDS_LOG_CODE,
        correct_count=correct,
        total_count=total,
        cleared=cleared,
        used_seconds=used,
        points=points,
        biz_date=biz,
    )
    db.add(sess)
    db.flush()

    # 答错的字词自动进错题本 —— 识字不是一锤子买卖
    new_wrong = WD.collect_wrong(db, user, key.get("qs", []), right, given)
    db.flush()

    ps = _ps(db)
    res = ps.grant(
        user,
        points,
        source_type="game",
        category="study",
        source_id=sess.id,
        note=f"识字闯关 答对 {correct}/{total}",
        operator_id=user.id,
        biz_date=biz,
    )
    sess.points = res["granted"]
    db.commit()
    return {
        "ok": True,
        "correct": correct,
        "total": total,
        "cleared": cleared,
        "points": res["granted"],
        "capped": res["capped"],
        "new_wrong": new_wrong,
        "played_today": played_now + 1,
        "limit": cfg["daily_limit"],
        "note": "全对了，这些字都是你的啦 \U0001F389"
        if cleared else f"答对 {correct}/{total}，错的字进错题本了，明天再复习",
    }


# ================================================================== 宠物
@child_router.get("/pet")
def pet_view(user: User = Depends(require_child), db: Session = Depends(get_db)):
    ps = _ps(db)
    st = PT.state(db, user, ps.exp_total(user.id))
    st["coins"] = ps.coin_summary(user)
    return st


class PetIn(BaseModel):
    species: str = "dragon"
    name: str = ""


@child_router.post("/pet/adopt")
def pet_adopt(body: PetIn, user: User = Depends(require_child),
              db: Session = Depends(get_db)):
    ps = _ps(db)
    def _run():
        r = PT.adopt(db, user, body.species, body.name, ps)
        db.commit()
        return r
    r = _bad(_run)
    r["state"] = PT.state(db, user, ps.exp_total(user.id))
    r["coins"] = ps.coin_summary(user)
    return r


@child_router.post("/pet/feed")
def pet_feed(user: User = Depends(require_child), db: Session = Depends(get_db)):
    ps = _ps(db)
    def _run():
        r = PT.feed(db, user, ps)
        db.commit()
        return r
    r = _bad(_run)
    r["coins"] = ps.coin_summary(user)
    return r


@child_router.post("/pet/play")
def pet_play(user: User = Depends(require_child), db: Session = Depends(get_db)):
    ps = _ps(db)
    def _run():
        r = PT.play(db, user)
        db.commit()
        return r
    r = _bad(_run)
    r["state_mood"] = PT.state(db, user, ps.exp_total(user.id))["mood"]
    return r


# ================================================================== 家庭共学（孩子端）
@child_router.get("/family")
def child_family(user: User = Depends(require_child), db: Session = Depends(get_db)):
    return SC.child_records(db, user)


# ================================================================== 家长学堂
@parent_router.get("/school")
def school_view(parent: User = Depends(require_parent), db: Session = Depends(get_db)):
    return SC.overview(db, parent)


class ArticleIn(BaseModel):
    code: str
    topic: str = ""


@parent_router.get("/school/articles")
def school_articles(topic: str = "", depth: int = 0,
                    parent: User = Depends(require_parent)):
    """depth=1 时返回全文（要点 + 今晚做的一件事），列表页不带全文。"""
    if not depth:
        return {
            "articles": [
                {k: v for k, v in a.items() if k != "bullets"} for a in SC.by_topic(topic)
            ]
        }
    return {"articles": SC.by_topic(topic)}


@parent_router.post("/school/read")
def school_read(body: ArticleIn, parent: User = Depends(require_parent),
                db: Session = Depends(get_db)):
    def _run():
        r = SC.mark_read(db, parent, body.code)
        db.commit()
        return r
    return _bad(_run)


class FamilyLearnIn(BaseModel):
    child_id: int
    kind: str = "read"
    minutes: int = 15
    note: str = ""


@parent_router.post("/school/family-learn")
def family_learn(body: FamilyLearnIn, parent: User = Depends(require_parent),
                 db: Session = Depends(get_db)):
    kid = db.get(User, body.child_id)
    if not kid or kid.family_id != parent.family_id or kid.role != "child":
        raise HTTPException(404, "孩子不存在")

    def _run():
        r = SC.add_family_learn(db, parent, kid, body.kind, body.minutes, body.note)
        db.commit()
        return r
    r = _bad(_run)
    r["week_minutes"] = SC.overview(db, parent)["week_minutes"]
    return r
