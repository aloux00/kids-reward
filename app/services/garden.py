# -*- coding: utf-8 -*-
"""
星星花园。

这一版刻意修正了同类产品最常见的漏洞：
「浇水就能拿积分」等于把花园做成了无限提款机。

这里三条硬约束：
1. 浇水本身一分不给 —— 只有最后收成才结算，且收益率压到 15%~25%。
2. 每次浇水强制间隔（默认 30 分钟），急不来，也刷不动。
3. 收益单独走 garden 分类并受每日上限约束，绝不会比乖乖打卡更划算。

种地的真正目的是让孩子体验「等一等才有」，
所以它必须比做任务慢、比做任务少，否则这个模块就没有存在价值。
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import today_str
from ..config import load_rules
from ..models import GardenPlot, User


def cfg() -> dict:
    return load_rules().get("garden") or {}


def plants() -> list:
    return list(cfg().get("plants") or [])


def plant_meta(code: str) -> dict | None:
    return next((p for p in plants() if p.get("code") == code), None)


def slot_count(level: int) -> int:
    c = cfg()
    base = int(c.get("slots_base", 2))
    step = max(1, int(c.get("slots_unlock_step", 2)))
    n = base + max(0, int(level or 1) - 1) // step
    return max(1, min(int(c.get("max_slots", 6)), n))


def ensure_plots(db: Session, child: User) -> list:
    """保证孩子的地块数量与等级匹配；升级后自动多给一块地。"""
    total = slot_count(child.level or 1)
    rows = list(
        db.scalars(
            select(GardenPlot)
            .where(GardenPlot.child_id == child.id, GardenPlot.slot < total)
            .order_by(GardenPlot.slot)
        ).all()
    )
    have = {r.slot for r in rows}
    for i in range(total):
        if i not in have:
            row = GardenPlot(
                family_id=child.family_id, child_id=child.id, slot=i, status="empty"
            )
            db.add(row)
            rows.append(row)
    db.flush()
    rows.sort(key=lambda r: r.slot)
    return rows


def cooldown_min() -> int:
    return max(1, int(cfg().get("water_cooldown_min", 30)))


def _minutes_since(moment: dt.datetime | None) -> float:
    if not moment:
        return 1e9
    return (dt.datetime.now() - moment).total_seconds() / 60.0


def _stage_emoji(row: GardenPlot, meta: dict) -> str:
    ratio = row.water_count / max(1, row.water_needed)
    if row.status == "ripe":
        return meta.get("emoji", "\U0001F33B")
    if ratio >= 0.6:
        return meta.get("mid_emoji", "\U0001F33F")
    if ratio >= 0.25:
        return "\U0001F331"
    return "\U0001F330"


def plot_dto(row: GardenPlot) -> dict:
    meta = plant_meta(row.plant_code) or {}
    wait = 0
    if row.status == "growing":
        wait = max(0, int(cooldown_min() - _minutes_since(row.last_water_at)))
    since = _minutes_since(row.last_water_at)
    droopy = row.status == "growing" and since > 60 * int(cfg().get("wither_hours", 72))
    return {
        "slot": row.slot,
        "empty": row.status == "empty",
        "status": row.status,
        "plant_code": row.plant_code,
        "name": meta.get("name", ""),
        "emoji": meta.get("emoji", "\U0001FAB4"),
        "stage_emoji": _stage_emoji(row, meta) if meta else "\U0001F7EB",
        "desc": meta.get("desc", ""),
        "seed_cost": int(meta.get("seed_cost", 0)),
        "yield_coin": int(row.yield_coin or 0),
        "water_count": int(row.water_count or 0),
        "water_needed": int(row.water_needed or 4),
        "wait_minutes": wait,
        "can_water": row.status == "growing" and wait <= 0,
        "can_harvest": row.status == "ripe",
        "droopy": droopy,
        "dead": row.status == "dead",
        "planted_hours": int(since / 60) if row.planted_at else 0,
    }


def state(db: Session, child: User) -> dict:
    rows = ensure_plots(db, child)
    plots = [plot_dto(r) for r in rows]
    return {
        "enabled": bool(cfg().get("enabled", True)),
        "plots": plots,
        "plants": plants(),
        "cooldown_min": cooldown_min(),
        "yield_rate": float(cfg().get("yield_rate", 1.2)),
        "slot_total": len(plots),
        "slot_locked": max(0, slot_count((child.level or 1) + 1) - len(plots)),
        "next_slot_hint": f"再升 1 级就多一块地（现在 {len(plots)} 块）",
        "tip": "浇水不给星星币，只有最后收成才算 —— 慢慢来，急着刷是刷不出来的 \U0001F331",
    }


# ------------------------------------------------------------------ 动作
def plant(db: Session, child: User, ps, slot: int, code: str) -> dict:
    c = cfg()
    if not c.get("enabled", True):
        raise ValueError("花园没有开启")
    meta = plant_meta(code)
    if not meta:
        raise ValueError("没有这种种子")
    rows = ensure_plots(db, child)
    row = next((r for r in rows if r.slot == slot), None)
    if row is None:
        raise ValueError("这块地还锁着呢")
    if row.status not in ("empty", "dead"):
        raise ValueError("这块地里已经种了东西")

    cost = int(meta.get("seed_cost", 10))
    if ps.available_coin(child.id) < cost:
        raise ValueError(f"星星币不够，种它需要 {cost} 星")

    needed = int(meta.get("water_needed", c.get("water_needed", 4)))
    ps.spend(child, cost, source_id=0, note=f"买下{meta.get('name', '种子')}种子")
    row.plant_code = code
    row.status = "growing"
    row.seed_cost = cost
    row.yield_coin = int(cost * float(c.get("yield_rate", 1.2)))
    row.water_count = 0
    row.water_needed = needed
    row.planted_at = dt.datetime.now()
    row.last_water_at = dt.datetime.now()
    row.harvested_at = None
    row.times_withered = 0
    db.flush()
    return {
        "ok": True,
        "slot": slot,
        "cost": cost,
        "yield": row.yield_coin,
        "water_needed": needed,
    }


def water(db: Session, child: User, slot: int) -> dict:
    rows = ensure_plots(db, child)
    row = next((r for r in rows if r.slot == slot), None)
    if row is None or row.status != "growing":
        raise ValueError("这里现在不用浇水")

    left = cooldown_min() - _minutes_since(row.last_water_at)
    if left > 0:
        raise ValueError(f"刚浇过水，再等 {int(left) + 1} 分钟再来吧 \U0001F4A7")

    row.water_count = int(row.water_count or 0) + 1
    row.last_water_at = dt.datetime.now()
    ready = row.water_count >= row.water_needed
    if ready:
        row.status = "ripe"
    db.flush()
    return {
        "ok": True,
        "slot": slot,
        "water_count": row.water_count,
        "water_needed": row.water_needed,
        "ripe": ready,
        "note": "熟啦，可以收获啦 \U0001F389"
        if ready
        else f"又长大一点（{row.water_count}/{row.water_needed}）",
    }


def harvest(db: Session, child: User, ps, slot: int) -> dict:
    rows = ensure_plots(db, child)
    row = next((r for r in rows if r.slot == slot), None)
    if row is None or row.status != "ripe":
        raise ValueError("还没有成熟")

    meta = plant_meta(row.plant_code) or {}
    gain = int(row.yield_coin or 0)
    overdue = _minutes_since(row.last_water_at) > 60 * int(cfg().get("dead_hours", 168))

    res = ps.grant(
        child,
        gain,
        source_type="garden",
        category=str(cfg().get("category", "garden")),
        source_id=0,
        note=f"收获{meta.get('name', '作物')}",
        operator_id=child.id,
        biz_date=today_str(),
    )
    row.status = "empty"
    row.plant_code = ""
    row.seed_cost = 0
    row.yield_coin = 0
    row.water_count = 0
    row.harvested_at = dt.datetime.now()
    db.flush()
    return {
        "ok": True,
        "slot": slot,
        "gain": res["granted"],
        "capped": res["capped"],
        "name": meta.get("name", "作物"),
        "note": "收获啦！种地就是这样，等一等才有 \U0001F31F"
        + ("（放得有点久啦，下次早点来收）" if overdue else ""),
    }
