# -*- coding: utf-8 -*-
"""
过期扫描。

rules.yaml 里配置了 application.expire_days，但一直没有对应的扫描逻辑，
结果就是：几个月前提交、家长早就忘了处理的申请会一直挂在待办列表里。
待办一旦堆积，家长就不再看它，整个审批闭环就断了。
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from ..config import load_rules
from ..models import PointApplication


def expire_applications(db, family_id: int | None = None) -> int:
    """把超过 expire_days 天仍未处理的加分申请标记为 expired。

    返回本次作废的条数。在读取申请列表 / 家长待办时顺手调用，
    不需要额外的定时任务 —— 单文件数据库就该这样轻量。
    """
    cfg = load_rules().get("application") or {}
    days = int(cfg.get("expire_days") or 0)
    if days <= 0:
        return 0

    cutoff = (dt.date.today() - dt.timedelta(days=days)).isoformat()
    q = select(PointApplication).where(
        PointApplication.status == "pending",
        PointApplication.biz_date < cutoff,
    )
    if family_id:
        q = q.where(PointApplication.family_id == family_id)

    rows = db.scalars(q).all()
    for r in rows:
        r.status = "expired"
        r.reviewed_at = dt.datetime.now()
        r.reject_reason = f"超过 {days} 天没有处理，已自动作废"
    if rows:
        db.commit()
    return len(rows)
