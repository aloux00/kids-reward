# -*- coding: utf-8 -*-
"""图片上传：愿望封面与任务佐证。本地存储，不依赖任何外部 OSS。"""
from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from ..config import UPLOAD_DIR
from ..db import get_db
from ..deps import current_user
from ..models import User

router = APIRouter(prefix="/api", tags=["misc"])

ALLOW = {"image/jpeg", "image/png", "image/webp", "image/gif"}
MAX_MB = 6


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if file.content_type not in ALLOW:
        raise HTTPException(400, "只支持 jpg / png / webp / gif 图片")

    data = await file.read()
    if len(data) > MAX_MB * 1024 * 1024:
        raise HTTPException(400, f"图片不能超过 {MAX_MB}MB")

    ext = (file.filename or "img.jpg").rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "webp", "gif"):
        ext = "jpg"
    name = f"{dt.date.today().isoformat().replace('-', '')}_{uuid.uuid4().hex[:10]}.{ext}"
    (UPLOAD_DIR / name).write_bytes(data)
    return {"url": f"/uploads/{name}"}
