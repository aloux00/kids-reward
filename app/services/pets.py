# -*- coding: utf-8 -*-
"""
宠物养成（纯矢量，无图片依赖）。

三条与其他养成类游戏不同的设定：
1. 宠物等级直接 mirror 孩子的成长值（exp_total）——
   孩子这一周是不是真的在努力，宠物跟着长大；靠花钱喂是喂不大的。
2. 心情（mood）只影响表情和对话，不扣任何分，也不会「死亡」。
   这个系统里不应该有惩罚性的意外，7 岁的孩子不该为忘记喂食焦虑。
3. 喂食要花星星币且有每日次数上限 —— 让它成为一个真实的选择，
   而不是把攒下的星星币白白倒掉的通道。
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import load_rules, today_str
from ..models import Pet, User


def cfg() -> dict:
    return load_rules().get("pet") or {}


SPECIES = {
    "dragon": {"name": "小火龙", "emoji": "\U0001F409", "line": "会把你的作业本守住"},
    "cat": {"name": "小奶猫", "emoji": "\U0001F431", "line": "喜欢趴在书桌上陪你"},
    "owl": {"name": "猫头鹰", "emoji": "\U0001F989", "line": "夜里读书它最精神"},
    "penguin": {"name": "小企鹅", "emoji": "\U0001F427", "line": "走得慢，但一直往前"},
}

STAGE_NAME = ["蛋宝宝", "小幼崽", "小少年", "守护兽", "传说伙伴"]


def species_list() -> list:
    return [dict(code=k, **v) for k, v in SPECIES.items()]


def mood_word(v: int) -> str:
    for floor, word in ((85, "超开心"), (65, "很满足"), (45, "有点无聊"),
                        (30, "想你了")):
        if v >= floor:
            return word
    return "闷闷的"


def _stage(exp: int) -> tuple:
    steps = list(cfg().get("stage_by_exp") or [0, 100, 400, 1000, 2500])
    stage, nxt = 0, None
    for i, need in enumerate(steps):
        if exp >= int(need):
            stage = i
        else:
            nxt = int(need)
            break
    return stage, nxt


def _roll_date(pet: Pet) -> None:
    """跨天就把喂食 / 玩耍次数清零；这是每天都能重新陪伴的意义。"""
    today = today_str()
    if pet.last_date != today:
        pet.feed_count = 0
        pet.play_count = 0
        pet.last_date = today


def _idle_days(pet: Pet) -> int:
    base = pet.last_date or pet.adopted_at.strftime("%Y-%m-%d")
    try:
        d0 = dt.date.fromisoformat(base)
    except ValueError:
        return 0
    return max(0, (dt.date.today() - d0).days)


def get_pet(db: Session, child: User) -> Pet | None:
    return db.scalar(select(Pet).where(Pet.child_id == child.id))


def state(db: Session, child: User, exp_total: int) -> dict:
    c = cfg()
    pet = get_pet(db, child)
    if pet is None:
        return {
            "enabled": bool(c.get("enabled", True)),
            "has_pet": False,
            "species": species_list(),
            "cost_adopt": int(c.get("adopt_cost", 0)),
            "stage_names": STAGE_NAME,
        }

    _roll_date(pet)
    decay = int(c.get("mood_decay_per_day", 10))
    idle = _idle_days(pet)
    floor = int(c.get("mood_floor", 35))
    # 今天有互动（喂食或玩耍）就不衰减；否则按闲置天数慢慢往下走
    if int(pet.feed_count or 0) == 0 and int(pet.play_count or 0) == 0:
        pet.mood = max(floor, int(pet.mood or 70) - decay * idle)
    pet.mood = max(0, min(100, int(pet.mood or 70)))
    db.flush()

    stage, nxt = _stage(int(exp_total or 0))
    max_feed = int(c.get("max_feed_per_day", 3))
    max_play = int(c.get("max_play_per_day", 3))
    feed_cost = int(c.get("feed_cost", 2))

    return {
        "enabled": bool(c.get("enabled", True)),
        "has_pet": True,
        "name": pet.name,
        "species": pet.species,
        "species_name": SPECIES.get(pet.species, {}).get("name", "小伙伴"),
        "species_line": SPECIES.get(pet.species, {}).get("line", ""),
        "emoji": SPECIES.get(pet.species, {}).get("emoji", "\U0001F43E"),
        "stage": stage,
        "stage_name": STAGE_NAME[min(stage, len(STAGE_NAME) - 1)],
        "exp": int(exp_total or 0),
        "next_stage_exp": nxt,
        "to_next": max(0, nxt - int(exp_total or 0)) if nxt is not None else 0,
        "max_stage": nxt is None,
        "mood": int(pet.mood),
        "mood_word": mood_word(int(pet.mood)),
        "bond": int(pet.bond or 0),
        "feed_cost": feed_cost,
        "play_cost": int(c.get("play_cost", 0)),
        "feed_left": max(0, max_feed - int(pet.feed_count or 0)),
        "play_left": max(0, max_play - int(pet.play_count or 0)),
        "max_feed": max_feed,
        "max_play": max_play,
        "adopted_days": max(1, (dt.date.today() - pet.adopted_at.date()).days + 1),
        "say": _say(pet, int(pet.mood), stage),
    }


def _say(pet: Pet, mood: int, stage: int) -> str:
    if mood >= 85:
        return f"有你在真好！今天我们一起长大一点点吧 ✨"
    if mood >= 60:
        return "我很精神！你今天的任务完成了吗？"
    if mood >= 40:
        return "陪我玩一会儿吧，我等你很久啦"
    return "这两天没见到你啦…今天见到你就很开心了 \U0001F97A"


def adopt(db: Session, child: User, species: str, name: str, ps=None) -> dict:
    c = cfg()
    if not c.get("enabled", True):
        raise ValueError("宠物没有开启")
    if get_pet(db, child) is not None:
        raise ValueError("你已经有一个小伙伴啦")
    if species not in SPECIES:
        raise ValueError("没有这种小伙伴")

    cost = int(c.get("adopt_cost", 0))
    if cost > 0:
        if ps is None:
            raise ValueError("无法支付")
        if ps.available_coin(child.id) < cost:
            raise ValueError(f"领养它需要 {cost} 星")
        ps.spend(child, cost, source_id=0, note="领养了一个小伙伴")

    pet = Pet(
        family_id=child.family_id,
        child_id=child.id,
        name=(name or SPECIES[species]["name"])[:20],
        species=species,
        mood=75,
        last_date=today_str(),
        adopted_at=dt.datetime.now(),
    )
    db.add(pet)
    db.flush()
    return {"ok": True, "name": pet.name, "species": species}


def feed(db: Session, child: User, ps) -> dict:
    c = cfg()
    pet = get_pet(db, child)
    if pet is None:
        raise ValueError("先去领养一个小伙伴吧")
    _roll_date(pet)
    cost = int(c.get("feed_cost", 2))
    max_n = int(c.get("max_feed_per_day", 3))
    if int(pet.feed_count or 0) >= max_n:
        raise ValueError(f"今天已经喂过 {max_n} 次啦，明天再来 \U0001F371")
    if ps.available_coin(child.id) < cost:
        raise ValueError(f"星星币不够，喂一次要 {cost} 星")

    ps.spend(child, cost, source_id=0, note=f"给{pet.name}喂食")
    pet.feed_count = int(pet.feed_count or 0) + 1
    pet.bond = int(pet.bond or 0) + 1
    pet.mood = max(0, min(100, int(pet.mood or 70) + int(c.get("feed_mood_gain", 8))))
    pet.last_date = today_str()
    db.flush()
    return {
        "ok": True,
        "mood": int(pet.mood),
        "cost": cost,
        "feed_left": max(0, max_n - int(pet.feed_count or 0)),
        "bond": int(pet.bond or 0),
        "note": f"{pet.name}吃得好开心 \U0001F60B",
    }


def play(db: Session, child: User) -> dict:
    c = cfg()
    pet = get_pet(db, child)
    if pet is None:
        raise ValueError("先去领养一个小伙伴吧")
    _roll_date(pet)
    max_n = int(c.get("max_play_per_day", 3))
    if int(pet.play_count or 0) >= max_n:
        raise ValueError(f"今天已经玩了 {max_n} 次啦，明天再来 \U0001F3B2")

    pet.play_count = int(pet.play_count or 0) + 1
    pet.bond = int(pet.bond or 0) + 1
    pet.mood = max(0, min(100, int(pet.mood or 70) + int(c.get("play_mood_gain", 10))))
    pet.last_date = today_str()
    db.flush()
    return {
        "ok": True,
        "mood": int(pet.mood),
        "play_left": max(0, max_n - int(pet.play_count or 0)),
        "bond": int(pet.bond or 0),
        "note": f"和{pet.name}玩了一会儿，它可开心啦 \U0001F495",
    }
