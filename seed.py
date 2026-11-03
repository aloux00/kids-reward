# -*- coding: utf-8 -*-
"""
初始化演示数据
    python seed.py          首次写入（已有数据则跳过）
    python seed.py --reset  清空后重建
"""
from __future__ import annotations

import datetime as dt
import random
import sys

from sqlalchemy import func, select

from app.config import DB_PATH, load_rules
from app.db import SessionLocal, init_db
from app.models import Achievement, Family, User, Wish
from app.security import hash_pin
from app.services import PointService
from app.services.level import recommended_ui_mode

random.seed(7)

CATEGORY_ICON = {"study": "📚", "exercise": "🏃", "chore": "🧹", "habit": "⏰"}
ZONE = {"study": "today", "exercise": "today", "chore": "today", "habit": "today"}


def _wipe_all(db) -> None:
    """
    删不掉数据文件时（Windows 上服务还开着，文件被占用）退一步：清空所有表。

    效果与删库重建一致，好处是不用先停服务。
    """
    from app.db import Base

    for table in reversed(Base.metadata.sorted_tables):
        db.execute(table.delete())
    db.commit()


def main() -> None:
    reset = "--reset" in sys.argv
    if reset and DB_PATH.exists():
        try:
            DB_PATH.unlink(missing_ok=True)
            for suffix in ("-wal", "-shm"):
                p = DB_PATH.with_name(DB_PATH.name + suffix)
                p.unlink(missing_ok=True)
        except OSError as e:      # 服务占用 / 权限不足
            print(f"（数据文件删不掉：{e} —— 改为清空所有表）")
            init_db()
            _wipe = SessionLocal()
            try:
                _wipe_all(_wipe)
            finally:
                _wipe.close()

    init_db()
    rules = load_rules()
    db = SessionLocal()
    ps = PointService(db)

    if db.scalar(select(func.count()).select_from(Family)):
        print("已有数据，跳过初始化。如需重建请运行： python seed.py --reset")
        db.close()
        return

    from app.models import TaskTemplate

    fam = Family(name="陈家", invite_code="HOME")
    db.add(fam)
    db.flush()

    # 昵称刻意写成「豆豆爸爸」这种带娃名的形式：家长在「我的资料」里能自己改，
    # 这里只是给出默认值的样子，顺带演示左上角品牌名也是可以改的。
    dad = User(family_id=fam.id, name="豆豆爸爸", avatar="🦸", role="owner",
               username="dad", pin_hash=hash_pin("1234"), ui_mode="normal")
    mom = User(family_id=fam.id, name="豆豆妈妈", avatar="👩", role="parent",
               username="mom", pin_hash=hash_pin("1234"), ui_mode="normal")
    kid = User(family_id=fam.id, name="豆豆", avatar="🐣", role="child",
               birth_year=dt.date.today().year - 7,
               pin_hash=hash_pin("1234"),
               ui_mode=recommended_ui_mode(dt.date.today().year - 7, rules))
    db.add_all([dad, mom, kid])
    db.flush()

    # ---- 初始任务库（家长是发布者）
    tpls = []
    for item in rules.get("task_defaults", []):
        if random.random() < 0.75:      # 演示库里保留大部分，留几类让家长自己加
            t = TaskTemplate(
                family_id=fam.id,
                name=item["name"],
                category=item["category"],
                points=item["points"],
                icon=CATEGORY_ICON.get(item["category"], "✅"),
                repeat_type="daily" if item.get("freq") == "daily" else "none",
                need_approval=bool(item.get("need_approval", True)),
                need_photo=bool(item.get("need_photo", False)),
                display_zone=ZONE.get(item["category"], "today"),
                created_by=dad.id,
            )
            tpls.append(t)
            db.add(t)
    db.flush()

    # ---- 一个随机任务（一次性惊喜任务）
    extra = TaskTemplate(
        family_id=fam.id, name="帮妈妈洗车", category="chore", points=8, icon="🚗",
        repeat_type="none", display_zone="extra", need_approval=True,
        need_photo=True, assignee_ids=f"[{( kid.id )}]", created_by=mom.id,
    )
    db.add(extra)
    db.flush()

    # ---- 愿望：许愿先行，一个大目标一个小目标
    w1 = Wish(family_id=fam.id, child_id=kid.id, title="乐高城市消防局",
              note="要和爸爸一起拼", cover_image="", cost_coin=300,
              priority=1, status="active")
    w2 = Wish(family_id=fam.id, child_id=kid.id, title="周末去游乐场",
              note="坐一次过山车", cover_image="", cost_coin=120,
              priority=0, status="active")
    db.add_all([w1, w2])
    db.flush()

    # ---- 成就
    for code, name, icon, ctype, val, desc in [
        ("first_hundred", "百分小星", "💯", "coin_total", 100, "累计获得 100 颗星星币"),
        ("keep7", "七日不倒", "🔥", "streak_days", 7, "连续打卡 7 天"),
        ("wish1", "愿望达成家", "🎁", "wish_completed", 1, "实现第 1 个愿望"),
        ("game10", "速算小达人", "🧠", "game_cleared", 5, "小游戏通关 5 次"),
    ]:
        db.add(Achievement(family_id=fam.id, code=code, name=name, icon=icon,
                           condition_type=ctype, condition_value=val, desc=desc))
    db.flush()

    # ---- 历史打卡：造出连续记录与等级
    from app.models import PointLedger, TaskRecord

    for back in range(6, 0, -1):
        day = (dt.date.today() - dt.timedelta(days=back)).isoformat()
        picked = random.sample(tpls, k=random.randint(2, 4))
        for t in picked:
            rec = TaskRecord(
                family_id=fam.id, child_id=kid.id, template_id=t.id, biz_date=day,
                status="approved", awarded_coin=t.points,
                submitted_at=dt.datetime.now(), reviewer_id=dad.id,
                reviewed_at=dt.datetime.now(),
            )
            db.add(rec)
            db.flush()
            res = ps.grant(kid, t.points, source_type="task", category=t.category,
                           source_id=rec.id, note=t.name, operator_id=dad.id,
                           biz_date=day)
            rec.awarded_coin = res["granted"]
        ps.update_streak(kid, day)

    # 今天：留两条已打卡、其余待做，方便演示待办审批
    today = dt.date.today().isoformat()
    for t in [tpls[0], tpls[3] if len(tpls) > 3 else tpls[-1]]:
        rec = TaskRecord(
            family_id=fam.id, child_id=kid.id, template_id=t.id, biz_date=today,
            status="pending", submitted_at=dt.datetime.now(),
            evidence_text="已经完成啦，请爸爸妈妈检查" if not t.need_photo else "",
        )
        db.add(rec)
    db.flush()

    ps.check_achievements(kid)
    db.commit()

    print("=" * 46)
    print("  演示数据已写入")
    print(f"  家长登录： dad / 1234      妈妈： mom / 1234")
    print(f"  孩子登录： 选头像「豆豆」 口令 1234")
    print(f"  当前等级： Lv{kid.level}   可用星星币：{ps.available_coin(kid.id)}"
          f"   连续打卡：{kid.streak_days} 天")
    print("=" * 46)
    db.close()


if __name__ == "__main__":
    main()
