# -*- coding: utf-8 -*-
"""数据库连接。SQLite + WAL，多家长同时操作不会互相阻塞。"""
from __future__ import annotations

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import DB_PATH

DB_URL = f"sqlite:///{DB_PATH.as_posix()}"

engine = create_engine(DB_URL, connect_args={"check_same_thread": False}, future=True)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _record):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 老库补列的清单。create_all 只会建新表，不会给已存在的表加字段，
# 所以每次启动都要检查一次 —— 否则升级后第一次访问必然报错。
_MISSING_COLUMNS = [
    ("wrong_question", "sort_order", "INTEGER DEFAULT 0"),
    ("wrong_question", "updated_at", "DATETIME"),
    ("wrong_question", "cause", "VARCHAR(20) DEFAULT ''"),
    ("wrong_question", "tag", "VARCHAR(30) DEFAULT ''"),
    ("wrong_question", "due_date", "VARCHAR(10)"),
    ("wrong_question", "review_stage", "INTEGER DEFAULT 0"),
]


def ensure_columns() -> None:
    with engine.begin() as conn:
        for table, col, ddl in _MISSING_COLUMNS:
            try:
                has = [
                    r[1]
                    for r in conn.execute(text(f"PRAGMA table_info({table})"))
                ]
            except Exception:
                continue
            if has and col not in has:
                conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
                )
        # 新列要有可用值，否则排序时 NULL 会排在最前面，看起来很怪
        if "wrong_question" in [t for t, _, _ in _MISSING_COLUMNS]:
            try:
                conn.execute(
                    text(
                        "UPDATE wrong_question SET updated_at = "
                        "COALESCE(created_at, CURRENT_TIMESTAMP) "
                        "WHERE updated_at IS NULL"
                    )
                )
            except Exception:
                pass


def init_db():
    from . import models  # noqa: F401

    Base.metadata.create_all(engine)
    ensure_columns()
