# -*- coding: utf-8 -*-
"""
扩展模块冒烟测试：星星花园 / 番茄钟 / 每日识字+闯关 / 宠物 / 家长学堂

    python smoke_test.py          # 主流程
    python smoke_test_extra.py    # 后加的五个模块（须先启动服务）

这里除了「能用」，重点验证三件容易做错的事：
1. 所有加分依旧只有 PointService 一条通道 —— 花园收成不得超过种子价的 1.3 倍。
2. 时间不由前端说了算 —— 刚点开始就点完成，番茄钟必须判无效。
3. 孩子的接口家长进不去，家长的接口孩子进不去。
"""
from __future__ import annotations

import json
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

BASE = "http://127.0.0.1:8777"
DB = Path(__file__).resolve().parent / "data" / "kids.db"
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

PASS, FAIL = 0, 0


def call(method, path, body=None, token=None):
    url = BASE + path
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with opener.open(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode()
        try:
            detail = json.loads(detail)["detail"]
        except Exception:
            pass
        return e.code, {"detail": detail}


def check(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {extra}")


def sql(query, args=(), fetch=True):
    con = sqlite3.connect(str(DB), timeout=10)
    try:
        cur = con.execute(query, args)
        out = cur.fetchall() if fetch else []
        con.commit()
        return out
    finally:
        con.close()


def reset_today(kid):
    """
    仅测试用：清掉孩子今天已经用掉的当日额度（闯关次数、宠物喂食、番茄钟）。

    这些额度本来就是按天重置的；脚本要能一天跑很多次，
    所以先把它们拨回「今天第一次」的状态，否则第二次跑必然被限额挡住。
    """
    today = datetime.now().strftime("%Y-%m-%d")
    sql("DELETE FROM game_session WHERE child_id=? AND biz_date=? AND game_code='words'",
        (kid, today), fetch=False)
    sql("DELETE FROM focus_session WHERE child_id=? AND biz_date=?", (kid, today), fetch=False)
    # 花园走独立的 daily_cap.garden，反复跑测试会把它吃满，这里一并拨回
    sql("DELETE FROM point_ledger WHERE child_id=? AND biz_date=? AND category='garden'",
        (kid, today), fetch=False)
    sql("UPDATE pet SET feed_count=0, play_count=0, last_date=? WHERE child_id=?",
        (today, kid), fetch=False)


print("\n=== 1. 登录 ===")
s, r = call("POST", "/api/auth/parent-login", {"username": "dad", "pin": "1234"})
check("家长登录", s == 200, r)
ptok = r.get("token", "")

s, kids = call("GET", "/api/auth/roster")
kid_id = kids[0]["kids"][0]["id"]

s, r = call("POST", "/api/auth/child-login", {"child_id": kid_id, "pin": "1234"})
check("孩子登录", s == 200, r)
ctok = r.get("token", "")

# 保证孩子有星星币可以买种子
call("POST", "/api/parent/grant",
     {"kid_id": kid_id, "points": 60, "note": "测试前置：给点本金", "category": "chore"},
     token=ptok)

print("\n=== 2. 家长学堂 ===")
s, sc = call("GET", "/api/parent/school", token=ptok)
check("学堂首页可读", s == 200, sc)
check("含今日推荐与主题入口", s == 200 and "recommend" in sc and "topics" in sc, sc)
check("含共学登记所需的孩子列表", s == 200 and len(sc.get("kids", [])) > 0, sc)

s, r = call("GET", "/api/parent/school", token=ctok)
check("孩子进不了家长学堂", s == 403, r)

s, r = call("GET", "/api/parent/school/articles", token=ptok)
check("文章列表可读", s == 200 and len(r.get("articles", [])) > 0, r)
first_code = (r.get("articles") or [{}])[0].get("code")

s, full = call("GET", "/api/parent/school/articles?depth=1", token=ptok)
has_bullets = any(a.get("bullets") for a in full.get("articles", []))
check("depth=1 返回全文要点", s == 200 and has_bullets, full)

s, r = call("POST", "/api/parent/school/read", {"code": first_code}, token=ptok)
check("标记已读", s == 200 and r.get("read_count", 0) >= 1, r)
n1 = r.get("read_count", 0)

s, r = call("POST", "/api/parent/school/read", {"code": first_code}, token=ptok)
check("重复标记不会重复计数", s == 200 and r.get("read_count") == n1, r)

s, r = call("POST", "/api/parent/school/read", {"code": "no-such-article"}, token=ptok)
check("不存在的文章被拒绝", s == 400, r)

s, r = call("POST", "/api/parent/school/family-learn",
            {"child_id": kid_id, "kind": "read", "minutes": 25,
             "note": "冒烟测试：一起读了一本书"}, token=ptok)
check("登记一次家庭共学", s == 200 and r.get("minutes") == 25, r)

s, fam = call("GET", "/api/child/family", token=ctok)
check("孩子端能看到共学记录", s == 200 and fam.get("count", 0) >= 1, fam)

print("\n=== 3. 星星花园 ===")
reset_today(kid_id)
s, gd = call("GET", "/api/child/garden", token=ctok)
check("花园可读", s == 200 and len(gd.get("plots", [])) > 0, gd)

s, r = call("GET", "/api/child/garden", token=ptok)
check("家长进不了孩子花园", s == 403, r)

s, r = call("POST", "/api/child/garden/plant", {"slot": 0, "code": "不存在的种子"}, token=ctok)
check("无效种子被拒绝", s == 400, r)

before = call("GET", "/api/child/home", token=ctok)[1]["coin"]["available"]
s, r = call("POST", "/api/child/garden/plant", {"slot": 0, "code": "sunflower"}, token=ctok)
check("种下向日葵", s == 200, r)
cost = r.get("cost", 0)
after = call("GET", "/api/child/home", token=ctok)[1]["coin"]["available"]
check("买种子确实扣了星星币", after == before - cost, f"{before} → {after}，种子 {cost}")

s, r = call("POST", "/api/child/garden/plant", {"slot": 0, "code": "tomato"}, token=ctok)
check("同一块地不能重复种植", s == 400, r)

s, r = call("POST", "/api/child/garden/water", {"slot": 0}, token=ctok)
check("刚种下立刻浇水被冷却挡住", s == 400, r)

s, r = call("POST", "/api/child/garden/harvest", {"slot": 0}, token=ctok)
check("没成熟不能收获", s == 400, r)

# 把时间拨回两小时、浇水次数补到差一次 —— 只为验证成熟与收成，不绕过任何加分逻辑
back = (datetime.now() - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
sql("UPDATE garden_plot SET last_water_at=?, water_count=water_needed-1 WHERE child_id=? AND slot=0",
    (back, kid_id), fetch=False)
s, r = call("POST", "/api/child/garden/water", {"slot": 0}, token=ctok)
check("冷却结束后可以浇水", s == 200, r)
check("浇够次数后成熟", s == 200 and r.get("ripe") is True, r)

s, r = call("POST", "/api/child/garden/harvest", {"slot": 0}, token=ctok)
check("成熟后可以收获", s == 200 and r.get("gain", 0) > 0, r)
gain, yield_cap = r.get("gain", 0), int(cost * 1.3) + 1
check("收成不超过种子价的 1.3 倍（花园不是提款机）", gain <= yield_cap, f"收成 {gain}，种子 {cost}")

print("\n=== 4. 番茄钟 ===")
reset_today(kid_id)
s, fs = call("GET", "/api/child/focus", token=ctok)
check("番茄钟可读", s == 200 and "limit" in fs, fs)

# 若上一次测试留下了没收尾的番茄，先收掉，保证本节从干净状态开始
if fs.get("running"):
    call("POST", "/api/child/focus/end",
         {"session_id": fs["running"]["id"], "mode": "abort"}, token=ctok)

s, r = call("POST", "/api/child/focus/start",
            {"minutes": 15, "topic": "口算练习"}, token=ctok)
check("开始专注", s == 200 and r.get("session", {}).get("status") == "running", r)
sid = r.get("session", {}).get("id")

s, r = call("POST", "/api/child/focus/start", {"minutes": 15}, token=ctok)
check("不能同时开两个番茄", s == 400, r)

s, r = call("POST", "/api/child/focus/end", {"session_id": sid}, token=ctok)
check("立刻点完成：时间不够判无效", s == 200 and r.get("valid") is False, r)
check("无效的番茄不给分", s == 200 and int(r.get("points", 0)) == 0, r)

s, r = call("POST", "/api/child/focus/start", {"minutes": 15, "topic": "练字"}, token=ctok)
sid2 = r.get("session", {}).get("id")
s, r = call("POST", "/api/child/focus/end",
            {"session_id": sid2, "mode": "abort"}, token=ctok)
check("中途放弃可以收场", s == 200 and r.get("status") in ("aborted", "invalid", None), r)

s, r = call("GET", "/api/child/focus", token=ptok)
check("家长进不了孩子番茄钟", s == 403, r)

# 关掉网页 / 手机没电留下的「永远进行中」必须能自动收场，否则孩子再也开不了新番茄
s, r = call("POST", "/api/child/focus/start", {"minutes": 10, "topic": "忘记收尾"}, token=ctok)
stale_id = r.get("session", {}).get("id")
if stale_id:
    back = (datetime.now() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
    sql("UPDATE focus_session SET started_at=? WHERE id=?", (back, stale_id), fetch=False)
    s, fs2 = call("GET", "/api/child/focus", token=ctok)
    check("超时的番茄自动收场，不会卡住孩子", s == 200 and fs2.get("running") is None, fs2)
else:
    check("超时的番茄自动收场，不会卡住孩子", False, r)

print("\n=== 5. 每日识字与识字闯关 ===")
reset_today(kid_id)
s, wd = call("GET", "/api/child/word/today", token=ctok)
check("今日识字可读", s == 200 and len(wd.get("new", [])) > 0, wd)
first_char = (wd.get("new") or [{}])[0].get("char")

s, r = call("POST", "/api/child/word/mark", {"key": first_char, "known": True}, token=ctok)
check("标记认识一个字", s == 200 and r.get("known_count", 0) >= 1, r)

s, rd = call("GET", "/api/child/word/round", token=ctok)
check("识字闯关可以出题", s == 200 and rd.get("round_token"), rd)
qs = rd.get("questions", [])

if qs:
    s, r = call("POST", "/api/child/word/submit",
                {"round_token": rd["round_token"], "answers": [""] * len(qs),
                 "used_seconds": 40}, token=ctok)
    check("交白卷不给分", s == 200 and int(r.get("points", 0)) == 0, r)
    check("答错的字进错题本", s == 200 and int(r.get("new_wrong", 0)) >= 1, r)

    s, r = call("POST", "/api/child/word/submit",
                {"round_token": rd["round_token"], "answers": [""] * len(qs),
                 "used_seconds": 40}, token=ctok)
    check("同一局的 token 不能重复使用", s == 400, r)

# 当天次数用完：把剩下的两次用掉，第四次应被拒绝
for _ in range(3):
    s, rd2 = call("GET", "/api/child/word/round", token=ctok)
    if s != 200:
        break
    call("POST", "/api/child/word/submit",
         {"round_token": rd2["round_token"],
          "answers": [""] * len(rd2.get("questions", [])), "used_seconds": 40}, token=ctok)
s, r = call("GET", "/api/child/word/round", token=ctok)
check("闯关次数用完后被拦住", s == 400, r)

print("\n=== 6. 宠物 ===")
reset_today(kid_id)
s, pt = call("GET", "/api/child/pet", token=ctok)
check("宠物页可读", s == 200 and len(pt.get("species", [])) > 0, pt)

if not pt.get("has_pet"):
    s, r = call("POST", "/api/child/pet/adopt",
                {"species": "dragon", "name": "小火"}, token=ctok)
    check("领养成功", s == 200, r)
else:
    print(f"      （已有宠物 {pt.get('name')}，跳过领养）")

s, r = call("POST", "/api/child/pet/feed", token=ctok)
check("喂食一次", s == 200, r)
mood_after_feed = r.get("mood")

s, r = call("POST", "/api/child/pet/play", token=ctok)
check("陪它玩一次", s == 200, r)

for _ in range(5):
    s, r = call("POST", "/api/child/pet/feed", token=ctok)
    if s == 400:
        break
check("喂食次数用完后被拦住", s == 400, r)

s, pt2 = call("GET", "/api/child/pet", token=ctok)
check("宠物状态可回读", s == 200 and pt2.get("has_pet"), pt2)
check("宠物等级跟着成长值走", s == 200 and "stage_name" in pt2 and "exp" in pt2, pt2)

print("\n=== 7. 越权与未登录 ===")
check("未登录访问学堂被拒绝", call("GET", "/api/parent/school")[0] in (401, 403))
check("未登录访问花园被拒绝", call("GET", "/api/child/garden")[0] in (401, 403))

print(f"\n{'=' * 46}\n  通过 {PASS} 项，失败 {FAIL} 项\n{'=' * 46}\n")
raise SystemExit(1 if FAIL else 0)
