# -*- coding: utf-8 -*-
"""等级与称号：由成长值决定，称号必须挂载真实特权，否则三天就失效。"""
from __future__ import annotations


def level_info(exp_total: int, rules: dict) -> dict:
    levels = sorted(rules.get("levels", []), key=lambda x: x["level"])
    if not levels:
        return {}

    cur = levels[0]
    for lv in levels:
        if exp_total >= lv["exp"]:
            cur = lv
        else:
            break

    idx = levels.index(cur)
    has_next = idx + 1 < len(levels)
    nxt = levels[idx + 1] if has_next else None

    if has_next:
        span = nxt["exp"] - cur["exp"]
        got = exp_total - cur["exp"]
        percent = int(got * 100 / span) if span > 0 else 100
        percent = max(0, min(100, percent))
        to_next = max(0, nxt["exp"] - exp_total)
    else:
        percent, to_next = 100, 0

    return {
        "level": cur["level"],
        "title": cur["title"],
        "perk": cur.get("perk", ""),
        "next_level": nxt["level"] if has_next else None,
        "next_title": nxt["title"] if has_next else None,
        "next_exp": nxt["exp"] if has_next else None,
        "next_perk": nxt.get("perk", "") if has_next else None,
        "to_next": to_next,
        "percent": percent,
        "max_level": not has_next,
    }


def all_levels(rules: dict) -> list:
    return sorted(rules.get("levels", []), key=lambda x: x["level"])


def recommended_ui_mode(birth_year: int | None, rules: dict) -> str:
    """按年龄推荐界面模式；家长与孩子都能手动切换。"""
    import datetime as _dt

    if not birth_year:
        return "childish"
    age = _dt.date.today().year - birth_year
    for mode, rng in rules.get("age_modes", {}).items():
        if rng.get("min_age", 0) <= age <= rng.get("max_age", 99):
            return mode
    return "normal"
