# -*- coding: utf-8 -*-
"""
识字与单词离线引擎。

题库全部内置在本机 Python 文件里：不联网、不调大模型、不需要申请 Key。
学校换教材或想加内容时，直接改 `app/content/words.py` 即可。

两种用法：
1. 每日识字 —— 每天推几个新字，认识了就点掉，没记住的明天自动再来一次。
2. 识字闯关 —— 服务端出题 + 签名，答错的自动进错题本，第二天还要重见一次。
"""
from __future__ import annotations

import datetime as dt
import random

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import load_rules
from ..content.words import ENWORDS, HANZI
from ..models import ItemProgress, User
from .wrong import record_wrong


def cfg() -> dict:
    return load_rules().get("words") or {}


# ------------------------------------------------------------------ 每日识字
def _progress_rows(db: Session, child: User) -> dict:
    rows = db.scalars(
        select(ItemProgress).where(
            ItemProgress.child_id == child.id, ItemProgress.bucket == "literacy"
        )
    ).all()
    return {r.item_key: r for r in rows}


def today_cards(db: Session, child: User) -> dict:
    c = cfg()
    per_day = max(1, int(c.get("new_per_day", 6)))
    known_map = _progress_rows(db, child)
    known_chars = [k for k, v in known_map.items() if v.known]

    # 新字按顺序往下走：认识了就往前推，中间不需要跳过（跳过＝默认不认识）
    idx = 0
    for i, item in enumerate(HANZI):
        if item["c"] in known_chars:
            idx = i + 1
        else:
            break
    new = HANZI[idx: idx + per_day]

    # 复习队列：最近点过「还没记住」的字优先
    review_rows = sorted(
        [r for r in known_map.values() if not r.known],
        key=lambda r: r.last_at,
        reverse=True,
    )[:5]
    dict_c = {x["c"]: x for x in HANZI}
    review = [dict_c[r.item_key] for r in review_rows if r.item_key in dict_c]

    total = len(HANZI)
    return {
        "new": [
            {"char": x["c"], "pinyin": x["p"], "word": x["w"], "mean": x["m"]}
            for x in new
        ],
        "review": [
            {"char": x["c"], "pinyin": x["p"], "word": x["w"], "mean": x["m"]}
            for x in review
        ],
        "known_count": len(known_chars),
        "total_chars": total,
        "percent": round(len(known_chars) * 100.0 / max(1, total), 1),
        "per_day": per_day,
        "note": f"已经认识 {len(known_chars)} / {total} 个字了 \U0001F4D6",
    }


def mark(db: Session, child: User, key: str, known: bool) -> dict:
    row = db.scalar(
        select(ItemProgress).where(
            ItemProgress.child_id == child.id,
            ItemProgress.bucket == "literacy",
            ItemProgress.item_key == key,
        )
    )
    if row is None:
        row = ItemProgress(
            family_id=child.family_id,
            child_id=child.id,
            bucket="literacy",
            item_key=key,
            known=bool(known),
            seen=1,
        )
        db.add(row)
    else:
        row.known = bool(known)
        row.seen = int(row.seen or 0) + 1
        row.last_at = dt.datetime.now()
    db.flush()
    known_n = int(
        db.scalar(
            select(func.count())
            .select_from(ItemProgress)
            .where(
                ItemProgress.child_id == child.id,
                ItemProgress.bucket == "literacy",
                ItemProgress.known.is_(True),
            )
        )
        or 0
    )
    return {
        "ok": True,
        "char": key,
        "known": bool(known),
        "known_count": known_n,
        "note": "真棒，又认识一个新字 \U0001F389" if known else "没关系，明天它还会来找你 🙂",
    }


# ------------------------------------------------------------------ 识字闯关
def _pick_options(pool: list, right: str, field: str, n: int = 4) -> list:
    """拼出 4 个选项，干扰项来自同一个词库 —— 保证难度接近而不是乱凑。"""
    others = [x[field] for x in pool if str(x[field]) != str(right)]
    random.shuffle(others)
    opts = [str(right)] + others[: max(0, n - 1)]
    random.shuffle(opts)
    return opts


def build_round(n: int | None = None) -> dict:
    c = cfg()
    total = int(n or c.get("questions", 8))
    use_hanzi = bool(c.get("use_hanzi", True))
    use_en = bool(c.get("use_english", True))
    kinds = []
    if use_hanzi:
        kinds += ["pinyin", "hanzi"]
    if use_en:
        kinds += ["en2zh", "zh2en"]
    if not kinds:
        kinds = ["pinyin"]

    questions, answers = [], []
    for _ in range(total):
        kind = random.choice(kinds)
        if kind in ("pinyin", "hanzi"):
            item = random.choice(HANZI)
            if kind == "pinyin":
                q = {
                    "kind": "pinyin",
                    "prompt": item["c"],
                    "hint": item["w"],
                    "options": _pick_options(HANZI, item["p"], "p"),
                    "explain": f"{item['c']}（{item['p']}）{item['w']}：{item['m']}",
                }
                answers.append(item["p"])
            else:
                q = {
                    "kind": "hanzi",
                    "prompt": item["p"],
                    "hint": item["m"],
                    "options": _pick_options(HANZI, item["c"], "c"),
                    "explain": f"{item['c']}（{item['p']}）{item['w']}：{item['m']}",
                }
                answers.append(item["c"])
            q["subject"] = "chinese"
            q["qkey"] = item["c"]
        else:
            item = random.choice(ENWORDS)
            if kind == "en2zh":
                q = {
                    "kind": "en2zh",
                    "prompt": item["en"],
                    "hint": "选出中文意思",
                    "options": _pick_options(ENWORDS, item["zh"], "zh"),
                    "explain": f"{item['en']} = {item['zh']}",
                }
                answers.append(item["zh"])
            else:
                q = {
                    "kind": "zh2en",
                    "prompt": item["zh"],
                    "hint": "选出英文单词",
                    "options": _pick_options(ENWORDS, item["en"], "en"),
                    "explain": f"{item['zh']} = {item['en']}",
                }
                answers.append(item["en"])
            q["subject"] = "english"
            q["qkey"] = item["en"]
        questions.append(q)

    return {"questions": questions, "answers": answers}


def kind_to_subject(kind: str) -> tuple:
    return ("english", "word-en-zh") if kind.startswith("en") or kind.startswith("zh2") \
        else ("chinese", "hanzi-pinyin")


def question_text(q: dict) -> str:
    return {
        "pinyin": f"{q['prompt']} 的读音是？",
        "hanzi": f"拼音 {q['prompt']}（{q['hint']}）是哪个字？",
        "en2zh": f"{q['prompt']} 是什么意思？",
        "zh2en": f"「{q['prompt']}」的英文是？",
    }.get(q["kind"], q["prompt"])


def collect_wrong(db: Session, child: User, questions: list, answers: list,
                  given: list) -> int:
    n = 0
    for i, right in enumerate(answers):
        mine = str(given[i]).strip() if i < len(given) else ""
        if mine and mine == str(right).strip():
            continue
        q = questions[i] if i < len(questions) else {}
        subject, k = kind_to_subject(q.get("kind", "pinyin"))
        record_wrong(
            db,
            child,
            question=question_text(q) if q else f"第 {i + 1} 题",
            correct_answer=str(right),
            wrong_answer=mine,
            source="word_game",
            subject=subject,
            kind=k,
            explain=q.get("explain", ""),
        )
        n += 1
    return n


def round_cfg() -> dict:
    c = cfg()
    return {
        "enabled": bool(c.get("enabled", True)),
        "questions": int(c.get("questions", 8)),
        "points_per_correct": int(c.get("points_per_correct", 1)),
        "clear_bonus": int(c.get("clear_bonus", 2)),
        "daily_limit": int(c.get("daily_round_limit", 3)),
        "use_hanzi": bool(c.get("use_hanzi", True)),
        "use_english": bool(c.get("use_english", True)),
    }
