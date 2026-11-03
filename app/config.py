# -*- coding: utf-8 -*-
"""全局配置与规则热加载。"""
from __future__ import annotations

import os
import threading
from datetime import date
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent


def _env_path(key: str, default: Path) -> Path:
    """
    把某个目录 / 文件指到别处。

    默认值就是项目内的相对位置，所以裸机（Windows 双击 start.bat、Linux 跑
    systemd）行为完全不变；只有显式设了环境变量才改道 —— Docker 部署靠这个
    把 data / uploads / rules.yaml 挪到挂载卷上。
    """
    raw = (os.environ.get(key) or "").strip()
    return Path(raw).expanduser().resolve() if raw else default


DATA_DIR = _env_path("KIDS_DATA_DIR", BASE_DIR / "data")
UPLOAD_DIR = _env_path("KIDS_UPLOAD_DIR", BASE_DIR / "uploads")
STATIC_DIR = _env_path("KIDS_STATIC_DIR", BASE_DIR / "static")
RULES_PATH = _env_path("KIDS_RULES_PATH", BASE_DIR / "rules.yaml")
DB_PATH = DATA_DIR / "kids.db"

# 教材库：PDF 落在这里，App 运行时只读本地文件，不碰外网
TEXTBOOK_DIR = DATA_DIR / "textbooks"
# 内置教材目录（ChinaTextbook 的离线索引），由 tools/build_textbook_catalog.py 生成
CATALOG_PATH = DATA_DIR / "textbook-catalog.json"
# 已下载教材的页数（tools/probe_pages.mjs 生成），布置作业时用来校验页码范围
PAGES_PATH = DATA_DIR / "textbook-pages.json"

for _d in (DATA_DIR, UPLOAD_DIR, STATIC_DIR, STATIC_DIR / "css", STATIC_DIR / "js",
           TEXTBOOK_DIR, RULES_PATH.parent):
    _d.mkdir(parents=True, exist_ok=True)

SECRET = os.environ.get("KIDS_SECRET", "kids-reward-local-secret-change-me")
TOKEN_TTL_DAYS = 30

_lock = threading.Lock()
_cache: dict = {"mtime": 0.0, "data": {}, "text": ""}


def load_rules(force: bool = False) -> dict:
    """读取规则；文件 mtime 变化时自动热加载，不需要重启服务。"""
    try:
        mt = RULES_PATH.stat().st_mtime
    except OSError:
        return _cache["data"]
    with _lock:
        if force or mt != _cache["mtime"]:
            text = RULES_PATH.read_text(encoding="utf-8")
            _cache["data"] = yaml.safe_load(text) or {}
            _cache["text"] = text
            _cache["mtime"] = mt
        return _cache["data"]


def rules_text() -> str:
    load_rules()
    return _cache["text"]


def save_rules_text(text: str) -> dict:
    """家长在网页上编辑规则后写回文件，下次读取即生效。"""
    data = yaml.safe_load(text) or {}
    RULES_PATH.write_text(text, encoding="utf-8")
    return load_rules(force=True)


try:  # ruamel 支持 round-trip：改写 rules.yaml 时保留中文注释
    from ruamel.yaml import YAML as _RuamelYAML

    _rt = _RuamelYAML()
    _rt.preserve_quotes = True
    try:
        _rt.allow_unicode = True
    except Exception:
        pass
    HAS_RUAMEL = True
except Exception:  # pragma: no cover
    _rt = None
    HAS_RUAMEL = False


DEFAULT_APP = {"name": "星星成长记", "subtitle": "让好习惯看得见", "logo": "⭐"}


def app_info() -> dict:
    """首页左上角、标题栏、登录页用的品牌信息。"""
    node = dict(load_rules().get("app") or {})
    return {
        "name": str(node.get("name") or DEFAULT_APP["name"])[:20],
        "subtitle": str(node.get("subtitle") or DEFAULT_APP["subtitle"])[:40],
        "logo": str(node.get("logo") or DEFAULT_APP["logo"])[:8],
    }


def save_app_info(new: dict) -> dict:
    """单独写 app 段，保留 rules.yaml 里的中文注释。"""
    if not HAS_RUAMEL:
        raise RuntimeError("缺少 ruamel.yaml，无法保留注释写入")

    doc = _rt.load(RULES_PATH.read_text(encoding="utf-8"))
    node = doc.setdefault("app", {})
    for k in ("name", "subtitle", "logo"):
        if k in new and str(new[k]).strip():
            node[k] = str(new[k]).strip()
    import io

    buf = io.StringIO()
    _rt.dump(doc, buf)
    RULES_PATH.write_text(buf.getvalue(), encoding="utf-8")
    return load_rules(force=True)


def wrong_subjects() -> list:
    """错题科目。家长可以自己增删，所以要有兜底默认值。"""
    rows = (load_rules().get("wrong_book") or {}).get("subjects") or []
    out = []
    for i, row in enumerate(rows):
        try:
            code = str(row.get("code", "")).strip()
            name = str(row.get("name", "")).strip()
        except AttributeError:
            continue
        if not code or not name:
            continue
        out.append(
            {
                "code": code,
                "name": name,
                "icon": str(row.get("icon") or "📌")[:4],
            }
        )
    return out or [
        {"code": "math", "name": "数学", "icon": "🔢"},
        {"code": "chinese", "name": "语文", "icon": "📖"},
        {"code": "english", "name": "英语", "icon": "🔤"},
        {"code": "other", "name": "其它", "icon": "📌"},
    ]


def save_wrong_subjects(rows: list) -> list:
    """覆盖写 subjects。返回的科目列表即为写入结果。"""
    if not HAS_RUAMEL:
        raise RuntimeError("缺少 ruamel.yaml，无法保留注释写入")

    doc = _rt.load(RULES_PATH.read_text(encoding="utf-8"))
    wb = doc.setdefault("wrong_book", {})
    clean = []
    seen = set()
    for row in rows:
        code = str(row.get("code", "")).strip()
        name = str(row.get("name", "")).strip()
        if not code or not name or code in seen:
            continue
        seen.add(code)
        clean.append(
            {"code": code, "name": name, "icon": str(row.get("icon") or "📌")[:4]}
        )
    if not clean:
        raise ValueError("至少要保留一个科目")

    wb["subjects"] = _as_compact_maps(clean)

    import io

    buf = io.StringIO()
    _rt.dump(doc, buf)
    RULES_PATH.write_text(buf.getvalue(), encoding="utf-8")
    load_rules(force=True)
    return clean


def today_str() -> str:
    return date.today().isoformat()


# ------------------------------------------------------------------ 结构化读写
def _assign(node, updates: dict) -> None:
    """逐字段赋值而不是整体替换，这样 rules.yaml 里的注释不会被冲掉。"""
    for k, v in updates.items():
        node[k] = v


def rules_structured() -> dict:
    """把 YAML 转成前端好用的结构。整数键（连击天数）转成数组，避免 JSON 不支持整数键。"""
    r = load_rules()
    return {
        "version": r.get("version", 1),
        "app": app_info(),
        "currency": dict(r.get("currency") or {}),
        "daily_cap": {k: int(v) for k, v in (r.get("daily_cap") or {}).items()},
        "streak_bonus": [
            {"days": int(k), "points": int(v)}
            for k, v in sorted((r.get("streak_bonus") or {}).items(), key=lambda x: int(x[0]))
        ],
        "streak_shield_per_month": int(r.get("streak_shield_per_month", 0)),
        "levels": [
            {
                "level": int(x.get("level", i + 1)),
                "title": x.get("title", ""),
                "exp": int(x.get("exp", 0)),
                "perk": x.get("perk", ""),
            }
            for i, x in enumerate(r.get("levels") or [])
        ],
        "task_defaults": list(r.get("task_defaults") or []),
        "gating": {
            "game_unlock_after_study": bool((r.get("gating") or {}).get("game_unlock_after_study", True)),
            "game_daily_play_limit": int((r.get("gating") or {}).get("game_daily_play_limit", 3)),
        },
        "games": list(r.get("games") or []),
        "application": dict(r.get("application") or {}),
        "age_modes": r.get("age_modes") or {},
        "redemption": dict(r.get("redemption") or {}),
        "wrong_book": dict(r.get("wrong_book") or {}, subjects=wrong_subjects()),
        "garden": dict(r.get("garden") or {}),
        "pomodoro": dict(r.get("pomodoro") or {}),
        "words": dict(r.get("words") or {}),
        "pet": dict(r.get("pet") or {}),
        "parent_school": dict(r.get("parent_school") or {}),
        "has_raw_editor": HAS_RUAMEL,
    }


def save_rules_structured(new: dict) -> dict:
    """
    家长在网页上点保存后写回文件。
    逐字段合并、保留原有注释与格式，改完立即热加载。
    """
    if not HAS_RUAMEL:
        raise RuntimeError("缺少 ruamel.yaml，无法保留注释写入")

    doc = _rt.load(RULES_PATH.read_text(encoding="utf-8"))

    if isinstance(new.get("currency"), dict):
        _assign(doc.setdefault("currency", {}), new["currency"])
    if isinstance(new.get("daily_cap"), dict):
        _assign(doc.setdefault("daily_cap", {}),
                {k: int(v) for k, v in new["daily_cap"].items()})

    if isinstance(new.get("streak_bonus"), list):
        rows = sorted([x for x in new["streak_bonus"] if int(x.get("days", 0)) > 0],
                      key=lambda x: int(x["days"]))
        doc["streak_bonus"] = {int(x["days"]): int(x["points"]) for x in rows}
    if new.get("streak_shield_per_month") is not None:
        doc["streak_shield_per_month"] = int(new["streak_shield_per_month"])

    if isinstance(new.get("levels"), list) and new["levels"]:
        rows = sorted(new["levels"], key=lambda x: int(x.get("exp", 0)))
        seq = []
        for i, row in enumerate(rows, start=1):
            seq.append({
                "level": i,
                "title": str(row.get("title", "")).strip() or f"第{i}级",
                "exp": int(row.get("exp", 0)),
                "perk": str(row.get("perk", "")).strip(),
            })
        # 第一级门槛强制为 0，保证注册就是 Lv1
        if seq:
            seq[0]["exp"] = 0
        seq = _dedup_exp(seq)
        doc["levels"] = _as_compact_maps(seq)

    if isinstance(new.get("gating"), dict):
        _assign(doc.setdefault("gating", {}), new["gating"])

    if isinstance(new.get("application"), dict):
        _assign(doc.setdefault("application", {}), new["application"])
    if isinstance(new.get("redemption"), dict):
        _assign(doc.setdefault("redemption", {}), new["redemption"])
    if isinstance(new.get("games"), list):
        _merge_games(doc, new["games"])

    # 扩展模块：只合并家长在页面上能改的字段，其余保持文件里原有的写法
    _merge_flat(doc, "garden", new.get("garden"),
                {"enabled", "water_cooldown_min", "water_needed", "yield_rate",
                 "slots_base", "slots_unlock_step", "max_slots"})
    _merge_flat(doc, "pomodoro", new.get("pomodoro"),
                {"enabled", "daily_limit", "default_minutes", "points_per_pomodoro",
                 "min_ratio", "grace_minutes", "bonus_at", "bonus_points"})
    if isinstance(new.get("pomodoro"), dict) and isinstance(
            new["pomodoro"].get("minutes_options"), list):
        doc.setdefault("pomodoro", {})["minutes_options"] = [
            int(x) for x in new["pomodoro"]["minutes_options"] if int(x) > 0
        ]
    _merge_flat(doc, "words", new.get("words"),
                {"enabled", "new_per_day", "daily_round_limit", "questions",
                 "points_per_correct", "clear_bonus", "use_hanzi", "use_english"})
    _merge_flat(doc, "pet", new.get("pet"),
                {"enabled", "adopt_cost", "feed_cost", "max_feed_per_day",
                 "play_cost", "max_play_per_day", "mood_decay_per_day", "mood_floor"})
    _merge_flat(doc, "parent_school", new.get("parent_school"),
                {"enabled", "weekly_goal_minutes"})
    # subjects 走独立接口维护，这里白名单合并，避免被规则页整体覆盖掉
    _merge_flat(doc, "wrong_book", new.get("wrong_book"),
                {"enabled", "review_batch_size", "review_all_correct_points"})
    if isinstance(new.get("app"), dict):
        _merge_flat(doc, "app", new["app"], {"name", "subtitle", "logo"})

    import io

    buf = io.StringIO()
    _rt.dump(doc, buf)
    RULES_PATH.write_text(buf.getvalue(), encoding="utf-8")
    return load_rules(force=True)


def _as_compact_maps(rows: list):
    """等级表保持 rules.yaml 里原本的紧凑写法 `- {level: 1, title: 启程星, ...}`。"""
    try:
        from ruamel.yaml.comments import CommentedMap as _CM

        out = []
        for row in rows:
            cm = _CM(row)
            cm.fa.set_flow_style()
            out.append(cm)
        return out
    except Exception:
        return rows


def _merge_flat(doc, key: str, payload, allowed: set) -> None:
    """按白名单合并一个平铺配置段 —— 白名单外的字段保持文件原样。"""
    if not isinstance(payload, dict):
        return
    node = doc.setdefault(key, {})
    for k, v in payload.items():
        if k in allowed:
            node[k] = v


def _dedup_exp(seq: list) -> list:
    """等级门槛必须严格递增，否则会出现同一时刻同时满足多级的歧义。"""
    last = -1
    for row in seq:
        if row["exp"] <= last:
            row["exp"] = last + 1
        last = row["exp"]
    return seq


def _merge_games(doc, games: list) -> None:
    """按 code 合并游戏配置，保留文件里已有的其它游戏项。"""
    old = {g.get("code"): g for g in (doc.get("games") or [])}
    merged = []
    for g in games:
        base = old.get(g.get("code"))
        if base is None:
            merged.append(g)
        else:
            for k, v in g.items():
                base[k] = v
            merged.append(base)
    doc["games"] = merged
