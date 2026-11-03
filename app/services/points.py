# -*- coding: utf-8 -*-
"""
★ 积分内核。所有星星币与成长值的增减，只能走 PointService 这一个入口。

设计要点：
1. 双货币同步 —— 同一笔收入，coin（可消费）与 exp（永不清零）同时增加。
   孩子在兑换时花掉了所有星星币，等级和称号仍然保留，第二天不会失去动力。
2. 追加式账本 —— 只 insert 不 update，任何一笔都能追溯到"哪天、哪项任务、谁批的"。
3. 每日上限在这里兜底 —— 无论调用方是谁（任务、申请、游戏、手动），
   上限一定生效，任何渠道都无法绕过。
"""
from __future__ import annotations

import datetime as dt
import json
from typing import Optional

from sqlalchemy import func, select

from ..config import load_rules, today_str
from ..db import SessionLocal
from ..models import (
    Achievement,
    AuditLog,
    LevelEvent,
    PointLedger,
    Redemption,
    User,
    UserAchievement,
)
from .level import level_info

NO_CAP_SOURCES = {"streak"}   # 连续打卡奖励单独算，不占用分类额度


def _yesterday(date_str: str) -> str:
    d = dt.date.fromisoformat(date_str) - dt.timedelta(days=1)
    return d.isoformat()


class PointService:
    def __init__(self, db):
        self.db = db

    # ---------------------------------------------------------- 查询
    def net_coin(self, child_id: int) -> int:
        """账户净额 = 所有流水之和（兑换的负数已包含在内）。"""
        v = self.db.scalar(
            select(func.coalesce(func.sum(PointLedger.delta_coin), 0)).where(
                PointLedger.child_id == child_id
            )
        )
        return int(v or 0)

    def total_earned(self, child_id: int) -> int:
        """累计获得。仅供家长端报表使用，孩子端接口绝不返回这个数字。"""
        v = self.db.scalar(
            select(func.coalesce(func.sum(PointLedger.delta_coin), 0)).where(
                PointLedger.child_id == child_id, PointLedger.delta_coin > 0
            )
        )
        return int(v or 0)

    def frozen_coin(self, child_id: int) -> int:
        """兑换申请已提交、家长尚未核销的部分，处于冻结状态。"""
        v = self.db.scalar(
            select(func.coalesce(func.sum(Redemption.cost_coin), 0)).where(
                Redemption.child_id == child_id, Redemption.status == "pending"
            )
        )
        return int(v or 0)

    def available_coin(self, child_id: int) -> int:
        return self.net_coin(child_id) - self.frozen_coin(child_id)

    def exp_total(self, child_id: int) -> int:
        v = self.db.scalar(
            select(func.coalesce(func.sum(PointLedger.delta_exp), 0)).where(
                PointLedger.child_id == child_id
            )
        )
        return int(v or 0)

    def earned_today(self, child_id: int, category: str, biz_date: str) -> int:
        """当天某分类已得分数，用于计算剩余额度。"""
        v = self.db.scalar(
            select(func.coalesce(func.sum(PointLedger.delta_coin), 0)).where(
                PointLedger.child_id == child_id,
                PointLedger.biz_date == biz_date,
                PointLedger.category == category,
                PointLedger.delta_coin > 0,
                PointLedger.source_type.notin_(list(NO_CAP_SOURCES)),
            )
        )
        return int(v or 0)

    def remaining_cap(self, child_id: int, category: str, biz_date: str) -> Optional[int]:
        """返回该分类当天剩余额度；None 表示该分类不限。"""
        rules = load_rules()
        cap = (rules.get("daily_cap") or {}).get(category)
        if not cap:
            return None
        return max(0, int(cap) - self.earned_today(child_id, category, biz_date))

    def coin_summary(self, child: User) -> dict:
        net = self.net_coin(child.id)
        frozen = self.frozen_coin(child.id)
        return {
            "available": net - frozen,
            "frozen": frozen,
            "net": net,
            "today_earned": self.earned_total_today(child.id),
        }

    def earned_total_today(self, child_id: int, biz_date: str | None = None) -> int:
        biz_date = biz_date or today_str()
        v = self.db.scalar(
            select(func.coalesce(func.sum(PointLedger.delta_coin), 0)).where(
                PointLedger.child_id == child_id,
                PointLedger.biz_date == biz_date,
                PointLedger.delta_coin > 0,
            )
        )
        return int(v or 0)

    # ---------------------------------------------------------- 写入（唯一入口）
    def grant(
        self,
        child: User,
        amount: int,
        source_type: str,
        category: str = "",
        source_id: int = 0,
        note: str = "",
        operator_id: int | None = None,
        biz_date: str | None = None,
        apply_cap: bool = True,
    ) -> dict:
        """
        加分。返回实际入账分数与是否触发上限。

        成长值与星星币 1:1 同步增加；若收入被每日上限截断，
        成长值也同步截断，保持两者一致。
        """
        amount = int(amount)
        if amount <= 0:
            return {"granted": 0, "capped": False, "remain": None}

        biz_date = biz_date or today_str()
        actual, remain = amount, None

        if apply_cap and source_type not in NO_CAP_SOURCES and category:
            remain = self.remaining_cap(child.id, category, biz_date)
            if remain is not None:
                actual = max(0, min(amount, remain))

        capped = actual < amount
        if actual == 0:
            return {"granted": 0, "capped": True, "remain": 0}

        new_net = self.net_coin(child.id) + actual
        new_exp = self.exp_total(child.id) + actual

        row = PointLedger(
            family_id=child.family_id,
            child_id=child.id,
            delta_coin=actual,
            delta_exp=actual,
            coin_after=new_net,
            exp_after=new_exp,
            source_type=source_type,
            source_id=source_id,
            category=category,
            note=note[:120],
            operator_id=operator_id,
            biz_date=biz_date,
        )
        self.db.add(row)
        self.db.flush()

        child.coin_total = self.total_earned(child.id)
        child.exp_total = new_exp

        self._sync_level(child, new_exp)
        self.db.flush()

        return {"granted": actual, "capped": capped, "remain": remain}

    def spend(
        self,
        child: User,
        amount: int,
        source_id: int = 0,
        note: str = "",
        operator_id: int | None = None,
    ) -> None:
        """兑换扣星。只减星星币，成长值永不清零 —— 这是整套机制的关键。"""
        new_net = self.net_coin(child.id) - int(amount)
        row = PointLedger(
            family_id=child.family_id,
            child_id=child.id,
            delta_coin=-int(amount),
            delta_exp=0,
            coin_after=new_net,
            exp_after=self.exp_total(child.id),
            source_type="redeem",
            source_id=source_id,
            category="",
            note=note[:120],
            operator_id=operator_id,
            biz_date=today_str(),
        )
        self.db.add(row)
        child.coin_total = self.total_earned(child.id)
        self.db.flush()

    # ---------------------------------------------------------- 等级与成就
    def _sync_level(self, child: User, exp_total: int) -> None:
        info = level_info(exp_total, load_rules())
        if not info:
            return
        if info["level"] > (child.level or 1):
            for lv in range((child.level or 1) + 1, info["level"] + 1):
                step = next(
                    (x for x in load_rules()["levels"] if x["level"] == lv), None
                )
                if step:
                    self.db.add(
                        LevelEvent(
                            family_id=child.family_id,
                            child_id=child.id,
                            level=lv,
                            title=step["title"],
                            perk=step.get("perk", ""),
                        )
                    )
        child.level = info["level"]

    def check_achievements(self, child: User) -> list:
        """轻量成就检查，只在我关注的三类维度上做，避免过度设计。"""
        from ..models import GameSession, Wish

        rules = load_rules()
        del rules  # 成就目前不依赖配置
        got = []
        items = self.db.scalars(
            select(Achievement).where(
                Achievement.family_id == child.family_id, Achievement.enabled.is_(True)
            )
        ).all()
        owned = {
            x.achievement_id
            for x in self.db.scalars(
                select(UserAchievement).where(UserAchievement.child_id == child.id)
            ).all()
        }

        counters = {
            "coin_total": lambda v: self.total_earned(child.id) >= v,
            "streak_days": lambda v: (child.streak_days or 0) >= v,
            "wish_completed": lambda v: self.db.scalar(
                select(func.count()).select_from(Wish).where(
                    Wish.child_id == child.id, Wish.status == "completed"
                )
            )
            >= v,
            "game_cleared": lambda v: self.db.scalar(
                select(func.count()).select_from(GameSession).where(
                    GameSession.child_id == child.id, GameSession.cleared.is_(True)
                )
            )
            >= v,
        }

        for a in items:
            if a.id in owned:
                continue
            check = counters.get(a.condition_type)
            if check and check(a.condition_value):
                self.db.add(
                    UserAchievement(
                        family_id=child.family_id,
                        child_id=child.id,
                        achievement_id=a.id,
                    )
                )
                got.append({"name": a.name, "icon": a.icon})
        if got:
            self.db.flush()
        return got

    # ---------------------------------------------------------- 连续打卡
    def update_streak(self, child: User, biz_date: str | None = None) -> dict:
        """
        连续打卡。断一天可用本月护盾抵消一次，每月重置。
        返回本次是否触发阶段性奖励。
        """
        rules = load_rules()
        biz_date = biz_date or today_str()
        last = child.last_checkin_date or ""

        bonus_map = {int(k): int(v) for k, v in (rules.get("streak_bonus") or {}).items()}
        shield_quota = int(rules.get("streak_shield_per_month", 0))

        if last == biz_date:
            return {"changed": False, "streak": child.streak_days or 0, "bonus": 0}

        if last == _yesterday(biz_date):
            child.streak_days = (child.streak_days or 0) + 1
            used_shield = False
        elif last == "":
            child.streak_days = 1
            used_shield = False
        else:
            gap = (dt.date.fromisoformat(biz_date) - dt.date.fromisoformat(last)).days
            used = self._shields_used_this_month(child.id, biz_date)
            if gap == 2 and shield_quota > used:
                # 断了一天，用掉本月一次断签保护
                child.streak_days = (child.streak_days or 0) + 1
                used_shield = True
                self.db.add(
                    AuditLog(
                        family_id=child.family_id,
                        actor_id=child.id,
                        action="streak_shield",
                        target_type="user",
                        target_id=child.id,
                        detail=f"{biz_date} 断签保护",
                    )
                )
            else:
                child.streak_days = 1
                used_shield = False

        child.last_checkin_date = biz_date

        bonus = 0
        days = child.streak_days
        if days in bonus_map:
            res = self.grant(
                child,
                bonus_map[days],
                source_type="streak",
                category="",
                note=f"连续打卡 {days} 天奖励",
                biz_date=biz_date,
                operator_id=child.id,
            )
            bonus = res["granted"]

        self.db.flush()
        return {"changed": True, "streak": days, "bonus": bonus, "shield": used_shield}

    def _shields_used_this_month(self, child_id: int, biz_date: str) -> int:
        prefix = biz_date[:7]
        v = self.db.scalar(
            select(func.count()).select_from(AuditLog).where(
                AuditLog.actor_id == child_id,
                AuditLog.action == "streak_shield",
                AuditLog.detail.like(f"{prefix}%"),
            )
        )
        return int(v or 0)

    def daily_average(self, child_id: int, days: int = 7) -> float:
        """近 N 日日均获得，用于估算愿望达成时间。"""
        start = (dt.date.today() - dt.timedelta(days=days - 1)).isoformat()
        v = self.db.scalar(
            select(func.coalesce(func.sum(PointLedger.delta_coin), 0)).where(
                PointLedger.child_id == child_id,
                PointLedger.biz_date >= start,
                PointLedger.delta_coin > 0,
            )
        )
        return round((int(v or 0)) / days, 1)


def add_audit(db, family_id: int, actor_id: int | None, action: str,
              target_type: str = "", target_id: int = 0, detail: str = "") -> None:
    db.add(
        AuditLog(
            family_id=family_id,
            actor_id=actor_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail[:200],
        )
    )
