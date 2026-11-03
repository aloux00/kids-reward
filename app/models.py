# -*- coding: utf-8 -*-
"""
数据模型。三条硬约定：

1. 每张业务表都有 family_id —— 现在是自家使用，将来开放多家庭不用重写。
2. point_ledger 只追加，不允许 update / delete —— 每笔分数都可追溯。
3. 注释里带【租户】的字段，查询时必须按 family_id 过滤。
"""
from __future__ import annotations

from datetime import datetime, date

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _now():
    return datetime.now()


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# --------------------------------------------------------------- 租户
class Family(Base):
    """家庭 = 租户单位。将来对外服务时，每个注册家庭就是一条记录。"""

    __tablename__ = "family"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), default="我的家")
    invite_code: Mapped[str] = mapped_column(String(16), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class User(Base):
    """家长与孩子共用一张表，用 role 区分。【租户】family_id"""

    __tablename__ = "user"
    __table_args__ = (Index("ix_user_family", "family_id", "role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("family.id"))
    name: Mapped[str] = mapped_column(String(30))
    avatar: Mapped[str] = mapped_column(String(80), default="\U0001F600")
    role: Mapped[str] = mapped_column(String(10))  # owner / parent / child
    pin_hash: Mapped[str] = mapped_column(String(200))
    username: Mapped[str] = mapped_column(String(40), default="")  # 家长登录名（可选）
    birth_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ui_mode: Mapped[str] = mapped_column(String(10), default="childish")
    display_title_code: Mapped[str] = mapped_column(String(30), default="")

    # 余额快照：真实来源永远是 point_ledger，这两个字段只为查询加速
    coin_total: Mapped[int] = mapped_column(Integer, default=0)      # 累计获得
    exp_total: Mapped[int] = mapped_column(Integer, default=0)       # 成长值，永不清零
    level: Mapped[int] = mapped_column(Integer, default=1)
    streak_days: Mapped[int] = mapped_column(Integer, default=0)
    last_checkin_date: Mapped[str] = mapped_column(String(10), default="")

    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Wish(Base):
    """愿望。许愿免费且无门槛 —— 先有目标，再攒星星币。【租户】family_id"""

    __tablename__ = "wish"
    __table_args__ = (Index("ix_wish_family_child", "family_id", "child_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("family.id"))
    child_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    title: Mapped[str] = mapped_column(String(60))
    note: Mapped[str] = mapped_column(Text, default="")
    cover_image: Mapped[str] = mapped_column(String(200), default="")
    cost_coin: Mapped[int] = mapped_column(Integer, default=100)
    priority: Mapped[int] = mapped_column(Integer, default=0)   # 1 = 当前主目标
    status: Mapped[str] = mapped_column(String(12), default="pending")
    # pending 待家长确认 / active 进行中 / completed 已实现 / abandoned 已放弃
    reject_reason: Mapped[str] = mapped_column(String(200), default="")
    target_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TaskTemplate(Base):
    """任务模板，家长是唯一发布者。【租户】family_id"""

    __tablename__ = "task_template"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("family.id"))
    name: Mapped[str] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(12), default="study")
    # study / exercise / chore / habit
    points: Mapped[int] = mapped_column(Integer, default=5)
    icon: Mapped[str] = mapped_column(String(16), default="✅")

    repeat_type: Mapped[str] = mapped_column(String(8), default="daily")
    # daily / weekly / none（none = 随机任务，一次性）
    repeat_rule: Mapped[str] = mapped_column(String(60), default="")
    # weekly 时为周几列表 JSON，如 "[1,3,5]"
    effective_from: Mapped[str | None] = mapped_column(String(10), nullable=True)
    effective_to: Mapped[str | None] = mapped_column(String(10), nullable=True)

    assignee_ids: Mapped[str] = mapped_column(String(120), default="[]")  # 指定孩子 JSON
    display_zone: Mapped[str] = mapped_column(String(8), default="today")
    # today 今日任务区 / extra 额外任务区；由家长决定，不按类型写死
    daily_limit: Mapped[int] = mapped_column(Integer, default=1)   # 每天可打卡次数
    need_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    need_photo: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class TaskRecord(Base):
    """一次打卡。唯一索引保证同一任务同一天不会重复得分。【租户】family_id"""

    __tablename__ = "task_record"
    __table_args__ = (
        UniqueConstraint("child_id", "template_id", "biz_date", name="uq_task_once"),
        Index("ix_record_family_status", "family_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("family.id"))
    child_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    template_id: Mapped[int] = mapped_column(ForeignKey("task_template.id"))
    biz_date: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10), default="pending")
    # pending 待家长确认 / approved 已通过 / rejected 已驳回
    awarded_coin: Mapped[int] = mapped_column(Integer, default=0)
    evidence_text: Mapped[str] = mapped_column(Text, default="")
    evidence_image: Mapped[str] = mapped_column(String(200), default="")
    reject_reason: Mapped[str] = mapped_column(String(200), default="")
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PointApplication(Base):
    """孩子主动申报加分 —— '我今天还想加分'。受三重约束。【租户】family_id"""

    __tablename__ = "point_application"
    __table_args__ = (Index("ix_apply_family_status", "family_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("family.id"))
    child_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    title: Mapped[str] = mapped_column(String(60))
    points: Mapped[int] = mapped_column(Integer, default=5)   # 孩子申报的分值
    awarded_coin: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[str] = mapped_column(String(12), default="habit")
    biz_date: Mapped[str] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10), default="pending")
    evidence_text: Mapped[str] = mapped_column(Text, default="")
    evidence_image: Mapped[str] = mapped_column(String(200), default="")
    reject_reason: Mapped[str] = mapped_column(String(200), default="")
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PointLedger(Base):
    """★ 系统核心：追加式账本。只允许 insert，永远不许 update / delete。"""

    __tablename__ = "point_ledger"
    __table_args__ = (Index("ix_ledger_child_date", "child_id", "biz_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("family.id"))
    child_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    delta_coin: Mapped[int] = mapped_column(Integer, default=0)
    delta_exp: Mapped[int] = mapped_column(Integer, default=0)
    coin_after: Mapped[int] = mapped_column(Integer, default=0)
    exp_after: Mapped[int] = mapped_column(Integer, default=0)
    source_type: Mapped[str] = mapped_column(String(12))
    # task / application / game / streak / manual / redeem / bonus
    source_id: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[str] = mapped_column(String(12), default="")
    note: Mapped[str] = mapped_column(String(120), default="")
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    biz_date: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class GameSession(Base):
    """每局游戏明细，用于限额判断与统计。分数由服务端判定后记入。"""

    __tablename__ = "game_session"
    __table_args__ = (Index("ix_game_child_date", "child_id", "biz_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("family.id"))
    child_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    game_code: Mapped[str] = mapped_column(String(20))
    correct_count: Mapped[int] = mapped_column(Integer, default=0)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    cleared: Mapped[bool] = mapped_column(Boolean, default=False)
    used_seconds: Mapped[int] = mapped_column(Integer, default=0)
    points: Mapped[int] = mapped_column(Integer, default=0)
    biz_date: Mapped[str] = mapped_column(String(10))
    played_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Redemption(Base):
    """兑换申请。提交即冻结星星币，家长核销时才真正扣除。【租户】family_id"""

    __tablename__ = "redemption"
    __table_args__ = (Index("ix_redeem_family_status", "family_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("family.id"))
    child_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    wish_id: Mapped[int] = mapped_column(ForeignKey("wish.id"))
    cost_coin: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(10), default="pending")
    # pending 冻结中 / fulfilled 已实现 / cancelled 已取消
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    handled_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class LevelEvent(Base):
    """升级留痕：哪天升到哪一级、解锁了什么特权，荣誉墙直接读这里。"""

    __tablename__ = "level_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("family.id"))
    child_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    level: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String(20))
    perk: Mapped[str] = mapped_column(String(60))
    reached_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Achievement(Base):
    __tablename__ = "achievement"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("family.id"))
    code: Mapped[str] = mapped_column(String(30))
    name: Mapped[str] = mapped_column(String(20))
    desc: Mapped[str] = mapped_column(String(80), default="")
    icon: Mapped[str] = mapped_column(String(16), default="🏅")
    condition_type: Mapped[str] = mapped_column(String(20))
    # coin_total / streak_days / wish_completed / game_cleared
    condition_value: Mapped[int] = mapped_column(Integer, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class UserAchievement(Base):
    __tablename__ = "user_achievement"
    __table_args__ = (
        UniqueConstraint("child_id", "achievement_id", name="uq_user_achv"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("family.id"))
    child_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    achievement_id: Mapped[int] = mapped_column(ForeignKey("achievement.id"))
    got_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class WrongQuestion(Base):
    """
    错题本。

    游戏 / 练习答错时自动收录，孩子可以重做，答对后标记「已掌握」。
    收录走专门的 Service，保证同一道题重复错只累加次数，不会污染列表。
    【租户】family_id 隔离。
    """

    __tablename__ = "wrong_question"
    __table_args__ = (
        Index("ix_wq_child_mastered", "child_id", "mastered"),
        Index("ix_wq_child_last", "child_id", "last_wrong_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("family.id"))
    child_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    source: Mapped[str] = mapped_column(String(20), default="game")   # game / practice
    subject: Mapped[str] = mapped_column(String(20), default="math")  # 数学 / 语文 / 英语
    kind: Mapped[str] = mapped_column(String(20), default="mental-math")
    question: Mapped[str] = mapped_column(String(200))          # 题面，如 "7 + 8 = ?"
    correct_answer: Mapped[str] = mapped_column(String(100))
    wrong_answer: Mapped[str] = mapped_column(String(100), default="", server_default="")
    explain: Mapped[str] = mapped_column(
        String(300), default="", server_default="")  # 解析/提示
    times_wrong: Mapped[int] = mapped_column(Integer, default=1)
    times_reviewed: Mapped[int] = mapped_column(Integer, default=0)
    mastered: Mapped[bool] = mapped_column(Boolean, default=False)
    mastered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_wrong_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    # 错因：粗心 / 没懂 / 看错题 / 算错 / 没做完。写下来才知道该怎么改。
    # 这两列必须带 server_default：只写 default="" 时，SQLAlchemy 只在 Python 侧填值，
    # 建出来的列是裸 NOT NULL。老库是后来 ALTER 加的列（带默认值），新库是 create_all
    # 直接建的（不带），于是"全新部署"和"升级上来的库"行为不一致——
    # 任何绕过 ORM 的写入（比如直接用 sqlite3 插数据）在新库上会报
    # IntegrityError: NOT NULL constraint failed。加上 server_default 让两边一致。
    cause: Mapped[str] = mapped_column(String(20), default="", server_default="")
    tag: Mapped[str] = mapped_column(
        String(30), default="", server_default="")   # 知识点，如「进位加法」
    # 间隔复习：下次该复习的日期 + 当前在第几档间隔
    due_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    review_stage: Mapped[int] = mapped_column(Integer, default=0)
    # 手动排序：家长整理的打印顺序。0 表示没排过，统一排在最后。
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_now, onupdate=_now)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# --------------------------------------------------------------- 家长学堂
class SchoolRead(Base):
    """家长读过哪篇微课。读过只是留痕，不与孩子的星星币发生任何关系。"""

    __tablename__ = "school_read"
    __table_args__ = (UniqueConstraint("parent_id", "article_code", name="uq_school_read"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("family.id"))
    parent_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    article_code: Mapped[str] = mapped_column(String(30))
    read_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class FamilyLearn(Base):
    """
    家庭共学记录 —— 陪伴这件事要被看见，但不换算成孩子的星星币。

    孩子在系统里被考核，家长如果完全置身事外，这套机制很容易被孩子理解成
    「大人只负责打分」。共学记录让爸爸妈妈的付出出现在同一块屏幕上。
    """

    __tablename__ = "family_learn"
    __table_args__ = (Index("ix_familylearn_family_date", "family_id", "biz_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("family.id"))
    parent_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    child_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    kind: Mapped[str] = mapped_column(String(16), default="read")
    # read 亲子阅读 / sport 一起运动 / cook 一起做饭 / talk 聊天谈心 / game 一起玩
    minutes: Mapped[int] = mapped_column(Integer, default=15)
    note: Mapped[str] = mapped_column(String(200), default="")
    biz_date: Mapped[str] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# --------------------------------------------------------------- 星星花园
class GardenPlot(Base):
    """
    花园里的一块地。

    一块地一个 slot，收获后回到空地可以再种 —— 不新建行，
    免得玩两周就攒出几百条垃圾数据。
    """

    __tablename__ = "garden_plot"
    __table_args__ = (UniqueConstraint("child_id", "slot", name="uq_plot_slot"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("family.id"))
    child_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    slot: Mapped[int] = mapped_column(Integer, default=0)
    plant_code: Mapped[str] = mapped_column(String(20), default="")   # 空 = 空地
    status: Mapped[str] = mapped_column(String(10), default="empty")
    # empty / growing / ripe / dead
    seed_cost: Mapped[int] = mapped_column(Integer, default=0)
    yield_coin: Mapped[int] = mapped_column(Integer, default=0)
    water_count: Mapped[int] = mapped_column(Integer, default=0)
    water_needed: Mapped[int] = mapped_column(Integer, default=4)
    planted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_water_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    harvested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    times_withered: Mapped[int] = mapped_column(Integer, default=0)


# --------------------------------------------------------------- 番茄钟
class FocusSession(Base):
    """一次专注。开始与结束时间由服务端记录，前端报的时长一律不采信。"""

    __tablename__ = "focus_session"
    __table_args__ = (Index("ix_focus_child_date", "child_id", "biz_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("family.id"))
    child_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    topic: Mapped[str] = mapped_column(String(40), default="专注学习")
    plan_minutes: Mapped[int] = mapped_column(Integer, default=15)
    actual_minutes: Mapped[int] = mapped_column(Integer, default=0)
    points: Mapped[int] = mapped_column(Integer, default=0)
    valid: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(10), default="running")
    # running 进行中 / done 已完成 / aborted 放弃了
    started_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    biz_date: Mapped[str] = mapped_column(String(10))


# --------------------------------------------------------------- 识字与单词进度
class ItemProgress(Base):
    """通用学习项进度（识字、单词）。bucket 区分用途，一行一个学习项。"""

    __tablename__ = "item_progress"
    __table_args__ = (
        UniqueConstraint("child_id", "bucket", "item_key", name="uq_item_progress"),
        Index("ix_progress_bucket", "child_id", "bucket"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("family.id"))
    child_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    bucket: Mapped[str] = mapped_column(String(16), default="literacy")
    item_key: Mapped[str] = mapped_column(String(60))
    known: Mapped[bool] = mapped_column(Boolean, default=False)
    seen: Mapped[int] = mapped_column(Integer, default=1)
    last_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# --------------------------------------------------------------- 宠物
class Pet(Base):
    """
    伙伴宠物。一个孩子一只。

    宠物的等级不强加 mirror 孩子的成长值（exp_total），不靠单独投喂升级 ——
    它长得快不快，取决于孩子这一周是不是真的在努力，而不是花了多少星星币。
    没有死亡、没有惩罚：心情低只是表情不一样，不扣任何分。
    """

    __tablename__ = "pet"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("family.id"))
    child_id: Mapped[int] = mapped_column(ForeignKey("user.id"), unique=True)
    name: Mapped[str] = mapped_column(String(20), default="小星")
    species: Mapped[str] = mapped_column(String(16), default="dragon")
    bond: Mapped[int] = mapped_column(Integer, default=0)      # 亲密度，喂食/玩耍累积
    mood: Mapped[int] = mapped_column(Integer, default=70)
    feed_count: Mapped[int] = mapped_column(Integer, default=0)
    play_count: Mapped[int] = mapped_column(Integer, default=0)
    last_date: Mapped[str] = mapped_column(String(10), default="")
    adopted_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("family.id"))
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    action: Mapped[str] = mapped_column(String(30))
    target_type: Mapped[str] = mapped_column(String(20), default="")
    target_id: Mapped[int] = mapped_column(Integer, default=0)
    detail: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


# --------------------------------------------------------------- 教材
class Textbook(Base):
    """
    书架上的一本教材。【租户】family_id

    三种来源都能进书架：
      upload  —— 家长上传 PDF
      url     —— 家长填一个远程地址，后台拉回本地
      catalog —— 从内置的 ChinaTextbook 索引里挑，点一下就下载

    关键设计：**下载完才进书架**。运行时只认 file_name 指向的本地文件，
    绝不现场去 GitHub 取 —— 那正是"别的系统用起来容易报错"的根源。
    """

    __tablename__ = "textbook"
    __table_args__ = (Index("ix_textbook_family_subject", "family_id", "subject"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("family.id"))

    title: Mapped[str] = mapped_column(String(80))
    subject: Mapped[str] = mapped_column(String(12), default="other")
    # chinese / math / english / science / morality / music / art / pe / other
    stage: Mapped[str] = mapped_column(String(12), default="小学")
    grade: Mapped[str] = mapped_column(String(12), default="")     # 一年级
    term: Mapped[str] = mapped_column(String(12), default="")      # 上册
    version: Mapped[str] = mapped_column(String(20), default="")   # 统编版

    source: Mapped[str] = mapped_column(String(10), default="upload")  # upload/url/catalog
    file_name: Mapped[str] = mapped_column(String(64), default="")     # data/textbooks 下的文件名
    remote_url: Mapped[str] = mapped_column(String(500), default="")
    catalog_path: Mapped[str] = mapped_column(String(300), default="")

    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    page_count: Mapped[int] = mapped_column(Integer, default=0)   # 由前端 pdf.js 首次打开时回写
    cover: Mapped[str] = mapped_column(String(200), default="")   # 封面图（可上传）

    status: Mapped[str] = mapped_column(String(12), default="ready")
    # ready 可读 / download 下载中 / failed 失败 / link 只存链接不下载
    error_msg: Mapped[str] = mapped_column(String(200), default="")

    is_current: Mapped[bool] = mapped_column(Boolean, default=False)  # 该学科当前在用
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    note: Mapped[str] = mapped_column(String(120), default="")

    created_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class TextbookProgress(Base):
    """
    孩子读到第几页。【租户】family_id

    单独一张表而不是塞进 Textbook：同一本书两个孩子读，进度必须各算各的。
    """

    __tablename__ = "textbook_progress"
    __table_args__ = (UniqueConstraint("textbook_id", "child_id", name="uq_progress_book"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("family.id"))
    textbook_id: Mapped[int] = mapped_column(ForeignKey("textbook.id"))
    child_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    last_page: Mapped[int] = mapped_column(Integer, default=1)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    seconds: Mapped[int] = mapped_column(Integer, default=0)      # 累计阅读秒数
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ReadingAssignment(Base):
    """
    家长布置的阅读作业：读某本教材的第 a–b 页。【租户】family_id

    状态机刻意和 task_record 保持一致（pending → done → approved / rejected），
    孩子端的交互习惯不用重新学一遍；加分走 PointService，自然受每日上限约束。
    """

    __tablename__ = "reading_assignment"
    __table_args__ = (Index("ix_reading_child_status", "child_id", "status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    family_id: Mapped[int] = mapped_column(ForeignKey("family.id"))
    child_id: Mapped[int] = mapped_column(ForeignKey("user.id"))
    textbook_id: Mapped[int] = mapped_column(ForeignKey("textbook.id"))

    page_from: Mapped[int] = mapped_column(Integer, default=1)
    page_to: Mapped[int] = mapped_column(Integer, default=1)
    points: Mapped[int] = mapped_column(Integer, default=5)
    biz_date: Mapped[str] = mapped_column(String(10), default="")
    due_date: Mapped[str] = mapped_column(String(10), default="")

    status: Mapped[str] = mapped_column(String(10), default="pending")
    # pending 待读 / done 已读完待确认 / approved 已通过 / rejected 已驳回
    note: Mapped[str] = mapped_column(String(120), default="")
    evidence_text: Mapped[str] = mapped_column(String(200), default="")
    reject_reason: Mapped[str] = mapped_column(String(200), default="")
    awarded: Mapped[int] = mapped_column(Integer, default=0)

    created_by: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    done_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("user.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
