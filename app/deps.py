# -*- coding: utf-8 -*-
"""认证与租户隔离。每个接口在这里声明所需角色，family_id 由令牌注入，不能由前端传。"""
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Query
from sqlalchemy.orm import Session

from .config import load_rules
from .db import get_db
from .models import User
from .security import parse_token


def _extract(token: str | None, authorization: str | None) -> dict | None:
    raw = token
    if not raw and authorization:
        raw = authorization.replace("Bearer ", "").strip()
    return parse_token(raw or "")


def current_user(
    token: str | None = Query(None),
    authorization: str | None = Header(None),
    db: Session = Depends(get_db),
) -> User:
    payload = _extract(token, authorization)
    if not payload:
        raise HTTPException(401, "登录已过期，请重新登录")
    user = db.get(User, payload["uid"])
    if not user or not user.active or user.family_id != payload["fid"]:
        raise HTTPException(401, "账号不可用")
    return user


def require_parent(user: User = Depends(current_user)) -> User:
    if user.role not in ("owner", "parent"):
        raise HTTPException(403, "只有家长可以操作")
    return user


def require_child(user: User = Depends(current_user)) -> User:
    if user.role != "child":
        raise HTTPException(403, "这是孩子端接口")
    return user


def child_in_family(
    child_id: int,
    user: User = Depends(require_parent),
    db: Session = Depends(get_db),
) -> User:
    """家长操作某个孩子时，必须确认这个孩子属于同一个家庭 —— 防止跨家庭越权。"""
    kid = db.get(User, child_id)
    if not kid or kid.family_id != user.family_id or kid.role != "child":
        raise HTTPException(404, "孩子不存在")
    return kid


def rules_dep() -> dict:
    return load_rules()
