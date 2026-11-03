# -*- coding: utf-8 -*-
"""儿童成长激励系统 · FastAPI 入口。"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import STATIC_DIR, UPLOAD_DIR
from .db import init_db
from .routers import (
    account_router,
    auth_router,
    book_child_router,
    book_common_router,
    book_parent_router,
    child_router,
    extra_child_router,
    extra_parent_router,
    misc_router,
    parent_router,
    wrong_child_router,
    wrong_parent_router,
)


def create_app() -> FastAPI:
    app = FastAPI(title="儿童成长激励系统", version="0.1.0")

    @app.on_event("startup")
    def _startup():
        init_db()

    app.include_router(auth_router)
    app.include_router(child_router)
    app.include_router(parent_router)
    app.include_router(extra_child_router)
    app.include_router(extra_parent_router)
    app.include_router(misc_router)
    app.include_router(account_router)
    app.include_router(wrong_child_router)
    app.include_router(wrong_parent_router)
    app.include_router(book_common_router)
    app.include_router(book_child_router)
    app.include_router(book_parent_router)

    app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    def index():
        return FileResponse(Path(STATIC_DIR) / "index.html")

    @app.get("/health")
    def health():
        return {"ok": True}

    return app


app = create_app()
