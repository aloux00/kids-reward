# -*- coding: utf-8 -*-
"""
资料 / 品牌 / 错题本增强 的自检脚本。

跑法：先启动服务（python run.py），再执行 python smoke_test_extra2.py
"""
from __future__ import annotations

import datetime as dt
import io
import json
import sqlite3
import sys
import urllib.error
import urllib.request
import zipfile

BASE = "http://127.0.0.1:8777"
DB = "data/kids.db"
PASS = FAIL = 0


def do(method, path, body=None, token=None, raw=False):
    req = urllib.request.Request(BASE + path, method=method)
    if token:
        req.add_header("Authorization", "Bearer " + token)
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode()
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data) as r:
            out = r.read()
            if raw:
                return r.status, out
            txt = out.decode("utf-8", "ignore")
            return r.status, (json.loads(txt) if txt.startswith(("{", "[")) else txt)
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", "ignore")
        try:
            return e.code, json.loads(txt)
        except Exception:
            return e.code, txt


def check(name, ok, extra=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}  {extra}")


def sql(q, args=(), fetch=True):
    con = sqlite3.connect(DB)
    try:
        cur = con.execute(q, args)
        rows = cur.fetchall() if fetch else None
        con.commit()
        return rows
    finally:
        con.close()


print("\n=== 1. 登录 ===")
s, r = do("POST", "/api/auth/parent-login", {"username": "dad", "pin": "1234"})
ptok = r.get("token", "") if isinstance(r, dict) else ""
check("家长登录", s == 200 and bool(ptok), str(r)[:120])

s, r = do("POST", "/api/auth/child-login", {"child_id": 3, "pin": "1234"})
ctok = r.get("token", "") if isinstance(r, dict) else ""
check("孩子登录", s == 200 and bool(ctok), str(r)[:120])
if not (ptok and ctok):
    sys.exit(1)

print("\n=== 2. 品牌自定义 ===")
s, r = do("GET", "/api/app-info")
check("未登录也能读品牌", s == 200 and isinstance(r, dict) and r.get("name"), str(r)[:100])

s, r = do("PUT", "/api/parent/app-info",
          {"name": "豆豆的成长乐园", "subtitle": "每天进步一点点", "logo": "🌈"}, ptok)
check("保存品牌", s == 200 and r.get("name") == "豆豆的成长乐园", f"{s} {str(r)[:120]}")

s, r = do("GET", "/api/app-info")
check("品牌立刻生效", s == 200 and r.get("logo") == "🌈", str(r)[:100])

s, r = do("PUT", "/api/parent/app-info", {"name": ""}, ptok)
check("空名字不覆盖", s == 200 and r.get("name") == "豆豆的成长乐园", str(r)[:100])

print("\n=== 3. 我的资料 / 孩子资料 ===")
s, me = do("GET", "/api/account/profile", token=ptok)
check("读取我的资料", s == 200 and me.get("name"), str(me)[:120])

s, r = do("PATCH", "/api/account/profile", {"name": "豆豆爸爸", "avatar": "🦸"}, ptok)
check("改昵称与头像", s == 200 and r.get("name") == "豆豆爸爸", f"{s} {str(r)[:120]}")

s, r = do("PATCH", "/api/account/profile",
          {"old_pin": "0000", "new_pin": "8888"}, ptok)
check("旧口令不对时拒绝改口令", s == 403, f"status={s}")

s, r = do("PATCH", "/api/account/profile",
          {"old_pin": "1234", "new_pin": "8888"}, ptok)
check("旧口令正确可改口令", s == 200 and "口令" in "".join(r.get("changed", [])), str(r)[:120])

s, r = do("PATCH", "/api/account/profile",
          {"old_pin": "8888", "new_pin": "1234"}, ptok)
check("口令可以改回来", s == 200, f"{s}")

row = sql("SELECT username FROM user WHERE id = (SELECT id FROM user WHERE role IN "
          "('owner','parent') LIMIT 1)")[0]
s, r = do("PATCH", "/api/account/profile", {"username": "nobody"}, ptok)
check("用户名可以改", s == 200 and r.get("username") == "nobody", str(r)[:120])
do("PATCH", "/api/account/profile", {"username": row[0]}, ptok)

s, r = do("PUT", "/api/parent/kid/3", {"name": "豆豆", "avatar": "🐯", "pin": "1234"}, ptok)
check("家长改孩子资料并重置口令", s == 200 and r.get("avatar") == "🐯", str(r)[:120])

s, _ = do("POST", "/api/auth/child-login", {"child_id": 3, "pin": "1234"})
check("孩子口令仍可登录", s == 200, str(s))

s, r = do("PUT", "/api/parent/kid/3", {"avatar": "😀"}, ptok)
do("PUT", "/api/parent/kid/3", {"avatar": "🐯"}, ptok)   # 还原演示头像

print("\n=== 4. 错题科目维护 ===")
s, r = do("GET", "/api/parent/wrong/subjects", token=ptok)
check("读科目", s == 200 and len(r["subjects"]) >= 3, str(r)[:120])

new_subs = [{"code": "math", "name": "数学", "icon": "🔢"},
            {"code": "chinese", "name": "语文", "icon": "📖"},
            {"code": "english", "name": "英语", "icon": "🔤"},
            {"code": "science", "name": "科学", "icon": "🔬"},
            {"code": "other", "name": "其它", "icon": "📌"}]
s, r = do("PUT", "/api/parent/wrong/subjects", {"subjects": new_subs}, ptok)
check("保存科目（含新增科学）", s == 200 and any(x["code"] == "science" for x in r["subjects"]),
      str(r)[:120])

s, r = do("GET", "/api/child/wrong/subjects", token=ctok)
check("孩子端读到同样的科目", s == 200 and any(x["code"] == "science" for x in r["subjects"]),
      str(r)[:120])

s, r = do("PUT", "/api/parent/wrong/subjects", {"subjects": []}, ptok)
check("不允许清空科目", s == 400, f"status={s}")

print("\n=== 5. 错题：筛选 / 排序 / 编辑 / 移动 ===")
today = dt.date.today().isoformat()
sql("UPDATE wrong_question SET mastered=0, mastered_at=NULL, review_stage=0, "
    "due_date=?, sort_order=0 WHERE child_id=3", (today,), fetch=False)

s, d = do("GET", "/api/child/wrong", token=ctok)
check("孩子端错题列表", s == 200 and isinstance(d.get("list"), list), str(d)[:140])
check("列表带 filtered / subjects / filter",
      all(k in d for k in ("filtered", "subjects", "filter")), str(list(d))[:140])

if not d.get("list"):
    print("  ⚠️ 演示库里没有错题，直接插入几道用于本轮自检")
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    seed_rows = [
        (3, "game", "math", "mental-math", "7 ＋ 8 = ?", "15", "13", 2),
        (3, "game", "math", "mental-math", "16 － 9 = ?", "7", "6", 1),
        (3, "word_game", "chinese", "hanzi-pinyin", "拼音 tiān 是哪个字？", "天", "大", 1),
    ]
    fam = sql("SELECT family_id FROM user WHERE id=3")[0][0]
    for sub, kind, q, ans, wrong, tw in [(r[2], r[3], r[4], r[5], r[6], r[7]) for r in seed_rows]:
        sql(
            "INSERT INTO wrong_question (family_id, child_id, source, subject, kind, "
            "question, correct_answer, wrong_answer, explain, times_wrong, times_reviewed, "
            "mastered, last_wrong_at, due_date, review_stage, sort_order, updated_at, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,'',?  ,0,0,?,?,0,0,?,?)",
            (fam, 3, "smoke", sub, kind, q, ans, wrong, tw, now, today, now, now),
            fetch=False,
        )
    s, d = do("GET", "/api/child/wrong", token=ctok)

lst_all = d["list"]
s, sub = do("GET", "/api/child/wrong?subject=math", token=ctok)
math_n = len(sub["filtered"])
check("按科目筛选生效", s == 200 and math_n <= len(lst_all), f"math={math_n}/all={len(lst_all)}")

s, ordered = do("GET", "/api/child/wrong?order=times", token=ctok)
seq = [x["times_wrong"] for x in ordered["filtered"]]
check("按错次排序单调不增", s == 200 and all(seq[i] >= seq[i + 1] for i in range(len(seq) - 1)),
      str(seq)[:80])

first = ordered["filtered"][0]
s, r = do("PATCH", f"/api/child/wrong/{first['id']}",
          {"tag": "进位加法", "cause": "careless"}, ctok)
check("孩子可以补填知识点与错因",
      s == 200 and r["item"]["tag"] == "进位加法" and r["item"]["cause_name"] == "粗心大意",
      str(r)[:160])

s, r = do("PATCH", f"/api/parent/wrong/{first['id']}",
          {"subject": "math", "explain": "先凑十再相加"}, ptok)
check("家长可以编辑孩子的错题", s == 200 and r["item"]["explain"] == "先凑十再相加", str(r)[:140])

s, r = do("POST", f"/api/parent/wrong/{first['id']}/move?dir=down", {}, ptok)
check("家长可调整打印顺序", s == 200 and isinstance(r.get("order"), list), str(r)[:100])

s, r = do("GET", "/api/parent/wrong/list?kid_id=3&status=all", token=ptok)
check("家长列表接口可读", s == 200 and isinstance(r.get("items"), list), str(r)[:120])

s, r = do("GET", f"/api/child/wrong/{first['id']}/variants", token=ctok)
vs = r.get("variants", []) if isinstance(r, dict) else []
is_math = "=" in str(first.get("question"))
check("举一反三：计算题能派生同类题", s == 200 and (len(vs) > 0 or not is_math),
      f"q={first.get('question')} n={len(vs)}")
if vs:
    ok = True
    for v in vs:
        try:
            parts = v["question"].replace("?", "").split()
            a, op, b = parts[0], parts[1], parts[2]
            left, right = int(a), int(b)
            want = {"＋": left + right, "－": left - right, "×": left * right}[op]
            ok = ok and str(want) == v["correct_answer"]
        except Exception:
            ok = False
    check("同类题答案算得对", ok, str([(v["question"], v["correct_answer"]) for v in vs])[:300])

print("\n=== 6. 间隔复习 ===")
sql("UPDATE wrong_question SET mastered=0, mastered_at=NULL, review_stage=0, "
    "due_date=?, times_reviewed=0 WHERE child_id=3", (today,), fetch=False)
s, d = do("GET", "/api/child/wrong", token=ctok)
due_items = d["review"]
due_before = {x["id"] for x in due_items}
check("今天到期的题会被挑出来", s == 200 and len(due_items) > 0, f"due={len(due_items)}")

s, r = do("POST", "/api/child/wrong/review",
          {"answers": [x["correct_answer"] for x in due_items],
           "ratings": ["easy"] * len(due_items)}, ctok)
check("全部答对能提交", s == 200 and r["right"] == len(due_items), str(r)[:160])
check("自评太简单会跳档", s == 200 and r["results"][0]["next_gap"] >= 4,
      str(r["results"][0])[:160])

row = sql("SELECT due_date > date('now') FROM wrong_question WHERE id=?", (due_items[0]["id"],))[0]
check("下次复习排到了未来", bool(row[0]), str(row))

s, d2 = do("GET", "/api/child/wrong", token=ctok)
after = {x["id"] for x in d2["review"]}
check("复习过的题今天不再出现", due_before.isdisjoint(after),
      f"still={sorted(due_before & after)}")

one = due_items[0]["id"]
s, r = do("POST", f"/api/child/wrong/{one}/rate?rating=forgot&adjust=1", {}, ctok)
check("补评「忘了」会退回未掌握", s == 200 and r["mastered"] is False, str(r)[:140])
tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
check("自评忘了 → 明天再见它", r.get("due_date") == tomorrow, str(r)[:140])
s, d3 = do("GET", "/api/child/wrong", token=ctok)
check("今天不再重复出现（避免一次堆太多）", one not in [x["id"] for x in d3["review"]],
      str([x["id"] for x in d3["review"]])[:80])

print("\n=== 7. 汇总 · 统计 · Word 导出 ===")
s, summ = do("GET", "/api/parent/wrong/summary?kid_id=3&status=all", token=ptok)
check("分科目汇总", s == 200 and isinstance(summ.get("groups"), list), str(summ)[:160])
check("每组都有科目名与题数",
      s == 200 and all(g.get("name") and g.get("count") is not None for g in summ["groups"]),
      str([(g["name"], g["count"]) for g in summ["groups"]])[:120])
seqs = [g["items"][0]["seq"] for g in summ["groups"] if g["items"]]
check("每题带来源编号", all(x.startswith("#") for x in seqs), str(seqs)[:80])

s, st = do("GET", "/api/parent/wrong/stats?kid_id=3", token=ptok)
check("学情统计可读", s == 200 and "master_rate" in st, str(st)[:160])
check("统计含错因分布", isinstance(st.get("by_cause"), list), str(st.get("by_cause"))[:120])

s, blob = do("GET", "/api/parent/wrong/export?kid_id=3&status=all&variants=1",
             token=ptok, raw=True)
check("导出接口返回 200", s == 200, str(blob[:120]) if isinstance(blob, bytes) else str(blob)[:120])
if s == 200 and isinstance(blob, (bytes, bytearray)):
    buf = io.BytesIO(blob)
    check("导出的是合法 docx 包", zipfile.is_zipfile(buf), "")
    try:
        z = zipfile.ZipFile(buf)
        names = z.namelist()
        check("docx 结构完整",
              "word/document.xml" in names and "[Content_Types].xml" in names, str(names)[:140])
        xml = z.read("word/document.xml").decode("utf-8", "ignore")
        check("卷面是练习格式（留横线）", "＿＿" in xml, "")
        check("附有参考答案与解析", "参考答案" in xml, "")
        check("标了来源编号", "#" in xml and any(c.isdigit() for c in xml), "")
    except Exception as e:  # noqa: BLE001
        check("docx 可读", False, str(e))

# 还原：品牌、示范家长的昵称与头像，让自检可以反复跑
do("PUT", "/api/parent/app-info",
   {"name": "星星成长记", "subtitle": "让好习惯看得见", "logo": "⭐"}, ptok)
do("PATCH", "/api/account/profile", {"name": me.get("name") or "爸爸", "avatar": me.get("avatar") or "😀"}, ptok)

print("\n" + "=" * 46)
print(f"通过 {PASS} 项，失败 {FAIL} 项")
print("=" * 46)
sys.exit(1 if FAIL else 0)
