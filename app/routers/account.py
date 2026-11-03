# -*- coding: utf-8 -*-
"""
账号资料：改昵称、改头像、改口令。

家长能改自己的（需要验证旧口令），也能改孩子的（PIN 是 4 位，孩子忘了很正常，
要求先知道旧 PIN 反而会逼着家长重置，所以这里不校验旧的）。
孩子端也能改自己的头像与昵称 —— 这是他唯一能"装饰自己"的地方。
改名改名这件事本身没有积分，纯粹是归属感。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import app_info, save_app_info
from ..db import get_db
from ..deps import current_user, require_parent
from ..models import Family, User
from ..security import hash_pin, verify_pin
from ..services import add_audit

router = APIRouter(prefix="/api", tags=["account"])

AVATAR_MAX = 30


def kid_from_path(kid_id: int, parent: User = Depends(require_parent),
                  db: Session = Depends(get_db)) -> User:
    """
    路径里的 /kid/{kid_id} 版租户校验。

    deps.child_in_family 只能读 query 参数（这是既有约定），
    这里跟着路径走，校验逻辑保持一致：同家庭 + 必须是孩子。
    """
    kid = db.get(User, kid_id)
    if not kid or kid.family_id != parent.family_id or kid.role != "child":
        raise HTTPException(404, "孩子不存在")
    return kid


def _clean_avatar(v: str | None) -> str | None:
    """头像可以是 emoji，也可以是 /uploads/xxx 的图片地址。"""
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    if len(s) > AVATAR_MAX and not s.startswith("/uploads/"):
        raise HTTPException(400, "头像太长了，用 emoji 或者上传一张小图就好")
    return s[:240]


def _clean_name(v: str | None) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    if len(s) > 10:
        raise HTTPException(400, "名字最多 10 个字")
    return s


# ------------------------------------------------------------------ 当前用户
class ProfileIn(BaseModel):
    name: str | None = None
    avatar: str | None = None
    username: str | None = None      # 仅家长；孩子的登录靠头像点击，不需要
    old_pin: str | None = None
    new_pin: str | None = None


@router.get("/account/profile")
def my_profile(user: User = Depends(current_user), db: Session = Depends(get_db)):
    fam = db.get(Family, user.family_id)
    return {
        "id": user.id,
        "name": user.name,
        "avatar": user.avatar,
        "role": user.role,
        "username": user.username,
        "ui_mode": user.ui_mode,
        "birth_year": user.birth_year,
        "family_name": fam.name if fam else "",
        "family_id": user.family_id,
    }


@router.patch("/account/profile")
def update_profile(body: ProfileIn, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    is_parent = user.role in ("owner", "parent")

    if body.name is not None:
        user.name = _clean_name(body.name) or user.name
    if body.avatar is not None:
        user.avatar = _clean_avatar(body.avatar) or user.avatar

    changed = []

    if is_parent and body.username is not None:
        uname = str(body.username).strip().lower()
        if uname and uname != user.username:
            clash = db.scalar(
                select(User).where(User.username == uname, User.id != user.id)
            )
            if clash:
                raise HTTPException(400, "这个用户名已经被占用了")
            user.username = uname
            changed.append("用户名")

    # 改口令：家长必须验证旧口令；孩子用旧 PIN 验证（他知道，就在登录时用）
    if body.new_pin:
        npin = str(body.new_pin)
        if len(npin) < 4:
            raise HTTPException(400, "口令至少 4 位")
        if not verify_pin(str(body.old_pin or ""), user.pin_hash):
            raise HTTPException(403, "旧口令不对，改不了新口令")
        user.pin_hash = hash_pin(npin)
        changed.append("口令")

    add_audit(db, user.family_id, user.id, "update_profile",
              "user", user.id, user.name + ("（改了" + "、".join(changed) + "）" if changed else ""))
    db.commit()
    return {
        "ok": True,
        "name": user.name,
        "avatar": user.avatar,
        "username": user.username,
        "changed": changed,
    }


# ------------------------------------------------------------------ 孩子资料（家长）
class KidProfileIn(BaseModel):
    name: str | None = None
    avatar: str | None = None
    birth_year: int | None = None
    ui_mode: str | None = None
    pin: str | None = None


@router.put("/parent/kid/{kid_id}")
def update_kid(kid_id: int, body: KidProfileIn,
               kid: User = Depends(kid_from_path),
               parent: User = Depends(require_parent),
               db: Session = Depends(get_db)):
    if body.name is not None:
        kid.name = _clean_name(body.name) or kid.name
    if body.avatar is not None:
        kid.avatar = _clean_avatar(body.avatar) or kid.avatar
    if body.birth_year is not None:
        if body.birth_year != 0:
            kid.birth_year = int(body.birth_year)
    if body.ui_mode is not None:
        if body.ui_mode in ("childish", "normal", "plain"):
            kid.ui_mode = body.ui_mode
    if body.pin:
        if len(str(body.pin)) < 4:
            raise HTTPException(400, "孩子的登录口令至少 4 位")
        kid.pin_hash = hash_pin(str(body.pin))

    add_audit(db, parent.family_id, parent.id, "update_kid",
              "user", kid.id, kid.name)
    db.commit()
    return {
        "ok": True,
        "id": kid.id,
        "name": kid.name,
        "avatar": kid.avatar,
        "birth_year": kid.birth_year,
        "ui_mode": kid.ui_mode,
    }


# ------------------------------------------------------------------ 品牌
class AppInfoIn(BaseModel):
    name: str | None = None
    subtitle: str | None = None
    logo: str | None = None


@router.get("/app-info")
def get_app_info():
    """公开接口：还没登录也要能显示标题，所以不放鉴权。"""
    return app_info()


@router.put("/parent/app-info")
def update_app_info(body: AppInfoIn, parent: User = Depends(require_parent),
                    db: Session = Depends(get_db)):
    payload = {}
    for k in ("name", "subtitle", "logo"):
        v = getattr(body, k)
        if v is not None:
            payload[k] = str(v).strip()
    if payload.get("name") and len(payload["name"]) > 20:
        raise HTTPException(400, "名字最多 20 个字")
    try:
        save_app_info(payload)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    add_audit(db, parent.family_id, parent.id, "update_app_info",
              "family", parent.family_id, payload.get("name", ""))
    db.commit()
    return app_info()
