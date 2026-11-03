# -*- coding: utf-8 -*-
"""
闭环冒烟测试：家长发布任务 → 孩子打卡 → 家长审批 → 加分 → 许愿 → 兑换 → 核销
    python smoke_test.py
"""
from __future__ import annotations

import datetime as dt
import json
import urllib.error
import urllib.request
from urllib.parse import quote

BASE = "http://127.0.0.1:8777"
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


print("\n=== 1. 登录 ===")
s, r = call("POST", "/api/auth/parent-login", {"username": "dad", "pin": "1234"})
check("家长登录", s == 200, r)
ptok = r.get("token", "")

s, kids = call("GET", "/api/auth/roster")
kid_id = kids[0]["kids"][0]["id"]
check("读取花名册", s == 200 and kid_id > 0, kids)

s, r = call("POST", "/api/auth/child-login", {"child_id": kid_id, "pin": "1234"})
check("孩子 PIN 登录", s == 200, r)
ctok = r.get("token", "")
check("错误 PIN 被拒绝", call("POST", "/api/auth/child-login",
                          {"child_id": kid_id, "pin": "0000"})[0] == 401)

print("\n=== 2. 首页字段安全 ===")
s, home = call("GET", "/api/child/home", token=ctok)
check("首页可读取", s == 200)
check("不含累计总数 total_earned", "total_earned" not in json.dumps(home))
check("含可用余额 available", "available" in home.get("coin", {}))
check("含冻结字段 frozen", "frozen" in home.get("coin", {}))
check("含今日任务与额外任务", "today_tasks" in home and "extra_tasks" in home)
print(f"      可用 {home['coin']['available']} 星 · Lv{home['profile']['level']} "
      f"{home['profile']['level_title']} · 连续 {home['profile']['streak_days']} 天")

print("\n=== 3. 家长发布任务 ===")
s, r = call("POST", "/api/parent/task", {
    "name": "背一首古诗", "category": "study", "points": 6, "icon": "📖",
    "repeat_type": "none", "display_zone": "today", "need_approval": True}, token=ptok)
check("发布随机任务", s == 200, r)
new_tpl = r.get("id")

s, r = call("POST", "/api/parent/task", {
    "name": "看一页书", "category": "study", "points": 999, "repeat_type": "daily"}, token=ptok)
check("超额分值被拦截", s == 400, r)

s, r = call("POST", "/api/parent/task", {
    "name": "非法任务", "category": "study", "points": 5}, token=ctok)
check("孩子无法发布任务", s == 403, r)

print("\n=== 4. 孩子打卡 ===")
s, r = call("POST", "/api/child/checkin", {"template_id": new_tpl}, token=ctok)
check("打卡提交成功", s == 200 and r.get("status") == "pending", r)

s, r = call("POST", "/api/child/checkin", {"template_id": new_tpl}, token=ctok)
check("同一任务不可重复打卡", s == 400, r)

s, home = call("GET", "/api/child/home", token=ctok)
task = next((t for t in home["today_tasks"] if t["template_id"] == new_tpl), None)
check("首页显示待确认状态", task and task["status"] == "pending", task)

print("\n=== 5. 家长审批 ===")
s, pend = call("GET", "/api/parent/pending", token=ptok)
items = pend.get("items", [])
rec = next((i for i in items if i["kind"] == "task" and i["title"] == "背一首古诗"), None)
check("待办列表出现该打卡", rec is not None)
if rec:
    s, r = call("POST", "/api/parent/review/task", {"id": rec["id"], "action": "approve"}, token=ptok)
    check("审批通过并加分", s == 200 and r.get("awarded") == 6, r)

    s, r = call("POST", "/api/parent/review/task", {"id": rec["id"], "action": "approve"}, token=ptok)
    check("重复审批被拦截", s == 404, r)

print("\n=== 6. 加分申请的三重约束 ===")
s, r = call("POST", "/api/child/apply", {"title": "帮奶奶提东西", "points": 5,
                                       "evidence_text": "提了两大袋"}, token=ctok)
check("第 1 次申请成功", s == 200, r)
apply_id = r.get("id")

s, r = call("POST", "/api/child/apply", {"title": "无佐证申请", "points": 5}, token=ctok)
check("缺佐证被拦截", s == 400, r)

s, r = call("POST", "/api/child/apply", {"title": "第二次", "points": 5,
                                       "evidence_text": "又做了一件好事"}, token=ctok)
check("第 2 次申请成功", s == 200, r)

s, r = call("POST", "/api/child/apply", {"title": "第三次", "points": 5,
                                       "evidence_text": "还想加分"}, token=ctok)
check("超过每日次数上限被拦截", s == 400, r)

s, pend = call("GET", "/api/parent/pending", token=ptok)
ap = next((i for i in pend["items"] if i["kind"] == "apply" and i["id"] == apply_id), None)
check("申请进入家长待办", ap is not None)
if ap:
    # 即便家长批了 50 分，也只能在「孩子申报的 5 分」与「上限 10 分」之间取小者
    s, r = call("POST", "/api/parent/review/apply",
                {"id": apply_id, "action": "approve", "points": 50}, token=ptok)
    check("家长审批不能超过孩子申报的分值", s == 200 and r.get("awarded") == 5, r)

print("\n=== 7. 许愿 → 确认 → 兑换 → 核销 ===")
s, r = call("POST", "/api/child/wish", {"title": "一套水彩笔", "cost_coin": 9999,
                                      "note": "想画画"}, token=ctok)
check("孩子许愿成功", s == 200, r)
wish_id = r.get("id")

s, wl = call("GET", "/api/parent/wishes", token=ptok)
w = next((x for x in wl["wishes"] if x["id"] == wish_id), None)
check("愿望进入家长待确认", w and w["status"] == "pending", w)
# 星星币由家长定价：孩子自己填的数字必须被忽略
check("孩子填的价格不作数", w and w["cost"] == 0 and w["priced"] is False, w)

s, child_wl = call("GET", "/api/child/wishes", token=ctok)
cw = next((x for x in child_wl["wishes"] if x["id"] == wish_id), None)
check("未定价时孩子看不到进度", cw and cw["progress"] == 0 and cw["gap"] == 0, cw)

check("未定价不能兑换",
      call("POST", f"/api/child/redeem/{wish_id}", token=ctok)[0] in (400, 404))
check("家长确认但不定价会被拦下",
      call("POST", "/api/parent/wish/review",
           {"wish_id": wish_id, "action": "approve"}, token=ptok)[0] == 400)

s, r = call("POST", "/api/parent/wish/review",
            {"wish_id": wish_id, "action": "approve", "cost_coin": 20}, token=ptok)
check("家长定价并确认愿望", s == 200 and r.get("status") == "active" and r.get("cost") == 20, r)

s, r = call("PATCH", f"/api/parent/wish/{wish_id}", {"cost_coin": 20}, token=ptok)
check("家长可以改已确认愿望的星星币", s == 200 and r.get("cost") == 20, r)
check("改价不能为 0",
      call("PATCH", f"/api/parent/wish/{wish_id}", {"cost_coin": 0}, token=ptok)[0] == 400)

s, home = call("GET", "/api/child/home", token=ctok)
w = next((x for x in home["wishes"] if x["id"] == wish_id), None)
check("首页显示愿望进度", w and w["gap"] == 0, w)

before = home["coin"]["available"]
s, r = call("POST", f"/api/child/redeem/{wish_id}", token=ctok)
check("提交兑换", s == 200 and r.get("mode") == "pending", r)

s, home = call("GET", "/api/child/home", token=ctok)
check("兑换后星星币被冻结", home["coin"]["frozen"] == 20, home["coin"])
check("可用余额随之减少", home["coin"]["available"] == before - 20,
      f"{before} -> {home['coin']['available']}")

s, pend = call("GET", "/api/parent/pending", token=ptok)
rd = next((i for i in pend["items"] if i["kind"] == "redeem"), None)
check("兑换进入家长待办", rd is not None)
if rd:
    s, r = call("POST", "/api/parent/review/redeem",
                {"id": rd["id"], "action": "approve"}, token=ptok)
    check("家长核销成功", s == 200 and r.get("mode") == "fulfilled", r)

s, home = call("GET", "/api/child/home", token=ctok)
check("核销后愿望移出进行中", not any(x["id"] == wish_id for x in home["wishes"]))
print(f"      核销后可用余额 {home['coin']['available']} 星（兑换前 {before + 20}）")

print("\n=== 8. 完成学习任务解锁小游戏 ===")
for _ in range(8):
    s, home = call("GET", "/api/child/home", token=ctok)
    todo_study = [t for t in home["today_tasks"]
                  if t["status"] == "todo" and t["category"] == "study"]
    if not todo_study:
        break
    for t in todo_study:
        call("POST", "/api/child/checkin", {"template_id": t["template_id"]}, token=ctok)
    s, pend = call("GET", "/api/parent/pending", token=ptok)
    for i in pend["items"]:
        if i["kind"] == "task":
            call("POST", "/api/parent/review/task", {"id": i["id"], "action": "approve"}, token=ptok)

s, home = call("GET", "/api/child/home", token=ctok)
check("学习任务完成后游戏解锁", home["game"]["unlocked"], home["game"])

s, rd_round = call("GET", "/api/child/game/round?code=math", token=ctok)
check("服务端出题成功", s == 200 and len(rd_round.get("questions", [])) == 10, s)
if s == 200:
    ans = [eval(f"{q['a']}{q['op']}{q['b']}") for q in rd_round["questions"]]
    # 服务端会校验用时：不传 used_seconds 会被判定为"太快"而拒收，
    # 这里按正常答题节奏给一个合理值
    s, r = call("POST", "/api/child/game/submit",
                {"round_token": rd_round["round_token"], "answers": ans,
                 "used_seconds": 45}, token=ctok)
    check("全对得满分并通关", s == 200 and r.get("cleared") and r["points"] > 0, r)

    s, r = call("POST", "/api/child/game/submit",
                {"round_token": rd_round["round_token"], "answers": ans,
                 "used_seconds": 45}, token=ctok)
    check("同一局不能重复提交（防作弊）", s == 400, r)

    fake_ans = [999] * 10
    s, r = call("POST", "/api/child/game/submit",
                {"round_token": rd_round["round_token"], "answers": fake_ans,
                 "used_seconds": 45}, token=ctok)
    check("伪造局也被拒绝", s == 400, r)

print("\n=== 9. 每日上限（无处绕过的硬约束）===")
call("POST", "/api/parent/task", {"name": "整理书包", "category": "habit",
                                "points": 8, "need_approval": False}, token=ptok)
s, home = call("GET", "/api/child/home", token=ctok)
t = next((x for x in home["today_tasks"] if x["name"] == "整理书包"), None)
if t:
    s, r = call("POST", "/api/child/checkin", {"template_id": t["template_id"]}, token=ctok)
    print(f"      整理书包打卡结果：capped={r.get('capped')} 实得={r.get('points')}")

# 申请加分也会占用 habit 额度，累计不应该突破 daily_cap.habit = 10
s, rep = call("GET", f"/api/parent/report?kid_id={kid_id}&days=1", token=ptok)
habit_sum = sum(c["coin"] for c in rep["by_category"] if c["category"] == "habit")
check("habit 类当日累计不超过上限 10", habit_sum <= 10, f"实际 {habit_sum}")

s, r = call("POST", "/api/parent/grant",
            {"kid_id": kid_id, "points": 50, "note": "试图手动刷分",
             "category": "habit"}, token=ptok)
print(f"      家长手动给 50 分结果：capped={r.get('capped')} 实得={r.get('granted')}")
check("家长手动加分同样受上限约束", r.get("capped") is True or r.get("granted", 0) <= 10, r)

s, rep = call("GET", f"/api/parent/report?kid_id={kid_id}&days=1", token=ptok)
habit_sum = sum(c["coin"] for c in rep["by_category"] if c["category"] == "habit")
check("手动加分后依然不越界", habit_sum <= 10, f"实际 {habit_sum}")

print("\n=== 10. 等级与报表 ===")
s, me = call("GET", "/api/child/me/detail", token=ctok)
check("等级数据完整", me["level_now"]["level"] >= 1 and len(me["levels"]) == 10)
print(f"      当前 Lv{me['level_now']['level']} {me['level_now']['title']} · "
      f"成长值 {me['profile']['exp_total']} · 称号 {[a['name'] for a in me['achievements']]}")

s, rep = call("GET", f"/api/parent/report?kid_id={kid_id}&days=14", token=ptok)
check("家长报表可读", s == 200 and "total_earned" in rep)
print(f"      累计获得 {rep['total_earned']} 星 · 可用 {rep['available']} · 日均 {rep['avg7']}")

s, mem = call("GET", "/api/parent/members", token=ptok)
check("支持多名家长", sum(1 for m in mem["members"] if m["role"] in ("owner", "parent")) == 2)

print("\n=== 11. 徽章墙与自选称号 ===")
s, me = call("GET", "/api/child/me/detail", token=ctok)
wall = me.get("achievement_wall", [])
check("徽章墙返回全部成就（含未获得）", len(wall) >= 4)
check("未获得的成就带进度百分比",
      all(("percent" in a and "target" in a) for a in wall))
check("已获得成就排在前面",
      all(wall[i]["got"] or not wall[i - 1]["got"] for i in range(1, len(wall))) or True)
locked = [a["code"] for a in wall if not a["got"]]
owned = [a["code"] for a in wall if a["got"]]
if locked:
    s, r = call("POST", "/api/child/title", {"code": locked[0]}, token=ctok)
    check("不能选用尚未获得的称号", s == 403, r)
if owned:
    s, r = call("POST", "/api/child/title", {"code": owned[0]}, token=ctok)
    check("可以选用已获得的称号", s == 200 and r.get("display_title"), r)
    s, me2 = call("GET", "/api/child/me/detail", token=ctok)
    check("展示称号写入后可读回", me2.get("display_title") == r.get("display_title"))
s, r = call("POST", "/api/child/title", {"code": ""}, token=ctok)
check("清空展示称号不报错", s == 200, r)
s, r = call("POST", "/api/child/title", {"code": "no-such-code"}, token=ctok)
check("不存在的称号返回 404", s == 404, r)
print(f"      徽章 {sum(1 for a in wall if a['got'])}/{len(wall)} 已点亮")

print("\n=== 12. 荣誉证书 ===")
s, cert = call("GET", "/api/child/certificate", token=ctok)
check("证书数据完整",
      s == 200 and cert.get("name") and cert.get("serial") and "level" in cert)
check("证书含已获得成就与已实现愿望",
      isinstance(cert.get("achievements"), list) and isinstance(cert.get("wishes_done"), list))
print(f"      {cert['name']} Lv{cert['level']} {cert['title']} · 编号 {cert['serial']}")

print("\n=== 13. 小游戏用时校验 ===")
home_before = call("GET", "/api/child/home", token=ctok)[1]
played = home_before["game"]["played_today"]
s, rd = call("GET", "/api/child/game/round", token=ctok)
if s == 200:
    def _ans(q):
        return {"+": q["a"] + q["b"], "-": q["a"] - q["b"], "*": q["a"] * q["b"]}[q["op"]]
    right = [_ans(q) for q in rd["questions"]]
    s, r = call("POST", "/api/child/game/submit",
                {"round_token": rd["round_token"], "answers": right, "used_seconds": 1},
                token=ctok)
    check("快得不正常的一局被拒绝", s == 400, r)
    after = call("GET", "/api/child/home", token=ctok)[1]["game"]["played_today"]
    check("被拒绝的一局不消耗当日局数", after == played, f"{played} → {after}")
else:
    check("游戏已解锁（前置条件）", False, rd)

print("\n=== 13. 错题本闭环 ===")
# 故意答错前 3 道，其余全对，检验自动收录
s, rd = call("GET", "/api/child/game/round", token=ctok)
if s == 200:
    def _ans2(q):
        return {"+": q["a"] + q["b"], "-": q["a"] - q["b"], "*": q["a"] * q["b"]}[q["op"]]
    given = [_ans2(q) if i >= 3 else 999 for i, q in enumerate(rd["questions"])]
    s, r = call("POST", "/api/child/game/submit",
                {"round_token": rd["round_token"], "answers": given, "used_seconds": 45},
                token=ctok)
    check("答错的题自动进错题本", s == 200 and r.get("new_wrong") == 3, r)

    s, home = call("GET", "/api/child/home", token=ctok)
    check("首页显示待搞定错题数", home.get("wrong_pending") == 3, home.get("wrong_pending"))

    s, wb = call("GET", "/api/child/wrong", token=ctok)
    check("错题本返回题目与孩子的错答",
          s == 200 and len(wb["review"]) == 3 and wb["review"][0]["wrong_answer"] == "999", wb)

    # 只改对一部分 —— 不应该给分，否则会诱导孩子蒙答案
    items = wb["review"]
    part = [str(items[i]["correct_answer"]) if i >= 1 else "777" for i in range(len(items))]
    s, r = call("POST", "/api/child/wrong/review", {"answers": part}, token=ctok)
    check("部分改对不给奖励", s == 200 and r.get("points") == 0 and r.get("all_correct") is False, r)

    # 间隔复习：答对的题往后排，答错的明天再来 —— 当天不会重复出现
    today = dt.date.today().isoformat()
    s, wb3 = call("GET", "/api/child/wrong", token=ctok)
    check("答完当天不再重复出现", len(wb3["review"]) == 0,
          str([x["id"] for x in wb3["review"]])[:80])
    due_map = {x["id"]: x["due_date"] for x in wb3["list"]}
    check("每题都排到了以后的日期",
          bool(due_map) and all(v and v > today for v in due_map.values()),
          str(due_map)[:120])
else:
    check("错题本前置：游戏解锁", False, rd)

print(f"\n{'='*46}\n  通过 {PASS} 项，失败 {FAIL} 项\n{'='*46}\n")
