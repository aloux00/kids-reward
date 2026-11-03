# -*- coding: utf-8 -*-
"""登录。孩子用头像 + 4 位 PIN，家长用账号 + 口令；多名家长共享同一个家庭。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Family, User
from ..security import make_token, verify_pin
from ..services import PointService
from ..services.ratelimit import client_ip, guard, record_fail, reset_many
from ..deps import current_user
from ..serializers import kid_brief

router = APIRouter(prefix="/api/auth", tags=["auth"])


class ChildLoginIn(BaseModel):
    child_id: int
    pin: str


class ParentLoginIn(BaseModel):
    username: str
    pin: str


class PinIn(BaseModel):
    pin: str


@router.get("/roster")
def roster(db: Session = Depends(get_db)):
    """登录页用的花名册：家庭 + 孩子头像。本地自用场景，接口只读。"""
    families = db.scalars(select(Family).order_by(Family.id)).all()
    out = []
    for f in families:
        kids = db.scalars(
            select(User).where(
                User.family_id == f.id, User.role == "child", User.active.is_(True)
            )
        ).all()
        out.append(
            {
                "id": f.id,
                "name": f.name,
                "kids": [
                    {"id": k.id, "name": k.name, "avatar": k.avatar} for k in kids
                ],
            }
        )
    return out


@router.post("/child-login")
def child_login(body: ChildLoginIn, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    account = f"child:{body.child_id}"
    blocked, keys = guard(account, ip)
    if blocked:
        raise HTTPException(
            429, f"尝试次数太多了，请 {blocked} 秒后再试试")

    kid = db.get(User, body.child_id)
    ok = bool(kid and kid.role == "child" and kid.active
              and verify_pin(body.pin, kid.pin_hash))
    if not kid or kid.role != "child" or not kid.active:
        for k in keys:
            record_fail(k)
        raise HTTPException(404, "没有找到这个小朋友")
    if not ok:
        for k in keys:
            record_fail(k)
        raise HTTPException(401, "口令不对哦，再试一次")

    reset_many(keys)
    return {
        "token": make_token(kid.id, kid.family_id, kid.role),
        "user": {
            "id": kid.id,
            "name": kid.name,
            "avatar": kid.avatar,
            "role": kid.role,
            "family_id": kid.family_id,
            "ui_mode": kid.ui_mode,
        },
    }


@router.post("/parent-login")
def parent_login(body: ParentLoginIn, request: Request, db: Session = Depends(get_db)):
    ip = client_ip(request)
    account = f"user:{body.username.strip().lower()}"
    blocked, keys = guard(account, ip)
    if blocked:
        raise HTTPException(
            429, f"尝试次数太多，请 {blocked} 秒后再试（防止被暴力破解）")

    user = db.scalar(
        select(User).where(
            User.username == body.username.strip(),
            User.role.in_(["owner", "parent"]),
            User.active.is_(True),
        )
    )
    if not user or not verify_pin(body.pin, user.pin_hash):
        for k in keys:
            record_fail(k)
        raise HTTPException(401, "用户名或口令不正确")

    reset_many(keys)
    return {
        "token": make_token(user.id, user.family_id, user.role),
        "user": {
            "id": user.id,
            "name": user.name,
            "avatar": user.avatar,
            "role": user.role,
            "family_id": user.family_id,
        },
    }


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    ps = PointService(db)
    is_child = user.role == "child"
    data = {
        "id": user.id,
        "name": user.name,
        "avatar": user.avatar,
        "role": user.role,
        "family_id": user.family_id,
        "ui_mode": user.ui_mode,
    }
    if is_child:
        info = kid_brief(db, user, ps)
        data.update(
            {
                "level": info["level"],
                "level_title": info["title"],
                "level_perk": info["perk"],
                "coin_available": info["coin_available"],
            }
        )
    return data


@router.post("/switch-ui-mode")
def switch_ui_mode(body: PinIn, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    mode = (body.pin or "").strip()
    if mode not in ("childish", "normal", "plain"):
        raise HTTPException(400, "界面模式不正确")
    user.ui_mode = mode
    db.commit()
    return {"ui_mode": mode}
