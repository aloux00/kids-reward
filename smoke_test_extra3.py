# -*- coding: utf-8 -*-
"""
教材功能的冒烟测试：书架 / 内置目录 / 上传 / 远程地址 / 阅读进度 / 阅读作业闭环。

    python smoke_test_extra3.py

前置：服务已在 8777 运行；data/textbooks 里至少有一本教材
（先用 python tools/fetch_textbooks.py --preset primary-ym 拉一批）。
"""
from __future__ import annotations

import datetime as dt
import json
import urllib.error
import urllib.request
import urllib.parse
import uuid

BASE = "http://127.0.0.1:8777"
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

PASS, FAIL = 0, 0


def call(method, path, body=None, token=None, headers=None):
    url = BASE + path
    data = None
    h = {}
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    if token:
        h["Authorization"] = "Bearer " + token
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with opener.open(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode()
        try:
            detail = json.loads(detail)["detail"]
        except Exception:
            pass
        return e.code, {"detail": detail}


def raw(method, path, token=None, headers=None):
    """要拿响应头和字节流的时候用这个（测 Range）。"""
    h = {}
    if token:
        h["Authorization"] = "Bearer " + token
    if headers:
        h.update(headers)
    req = urllib.request.Request(BASE + path, headers=h, method=method)
    try:
        with opener.open(req, timeout=30) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()[:120]


def upload(path, token, filename, blob, fields):
    """手写 multipart：不引 requests，保持测零依赖。"""
    boundary = "----kr" + uuid.uuid4().hex
    parts = []
    for k, v in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    parts.append(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f'Content-Type: application/pdf\r\n\r\n'.encode()
    )
    parts.append(blob)
    parts.append(f"\r\n--{boundary}--\r\n".encode())
    body = b"".join(parts)

    req = urllib.request.Request(
        BASE + path, data=body, method="POST",
        headers={"Authorization": "Bearer " + token,
                 "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with opener.open(req, timeout=60) as r:
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


def qs(**kw):
    return "?" + urllib.parse.urlencode({k: v for k, v in kw.items() if v != ""})


# 一个结构合法的最小 PDF，用来测上传。
# 末尾补一大段注释撑到 1KB 以上 —— 服务端有"小于 1KB 肯定不是真教材"的保护，
# 而真实课本都在 10MB 量级，这里只是让测试样本符合这个前提。
TINY_PDF = (b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj
trailer<</Root 1 0 R>>
"""
    + b"%" + b"p" * 1400 + b"\n%%EOF\n")

print("\n=== 1. 登录 ===")
s, r = call("POST", "/api/auth/parent-login", {"username": "dad", "pin": "1234"})
check("家长登录", s == 200, r)
ptok = r.get("token", "")

s, roster = call("GET", "/api/auth/roster")
kid_id = roster[0]["kids"][0]["id"]
check("读取花名册", s == 200 and kid_id > 0, roster)

s, r = call("POST", "/api/auth/child-login", {"child_id": kid_id, "pin": "1234"})
check("孩子登录", s == 200, r)
ctok = r.get("token", "")

print("\n=== 2. 书架（下载好的教材自动上架）===")
s, shelf = call("GET", "/api/parent/textbooks", token=ptok)
check("家长能读教材书架", s == 200, shelf)
books = shelf.get("books", []) if s == 200 else []
check("书架里有教材", len(books) > 0, f"共 {len(books)} 本")
ready = [b for b in books if b.get("ready")]
check("至少一本处于可读状态", len(ready) > 0, f"可读 {len(ready)} 本")

if not ready:
    print()
    print("=" * 46)
    print("  还没有任何已下载的教材，后面的用例全部依赖真实 PDF，先跳过。")
    print("  跑这个下载一批再测：")
    print("    python tools/fetch_textbooks.py --preset primary-ym")
    print("=" * 46)
    raise SystemExit(0)

first = ready[0]
print(f"      样例：{first['title']} · {first.get('size_mb')} MB · {first.get('subject_name')}")

s, cshelf = call("GET", "/api/child/textbooks", token=ctok)
check("孩子能读自己的书架", s == 200 and cshelf.get("total", 0) > 0, cshelf)
check("孩子书架按学科分组", len(cshelf.get("groups", [])) > 0)

print("\n=== 3. 内置教材目录（纯本地，不联网）===")
s, cat = call("GET", "/api/parent/textbooks/catalog" + qs(limit=5), token=ptok)
check("能浏览内置目录", s == 200, cat)
check("目录总量可观", cat.get("total_available", 0) > 1000, cat.get("total_available"))

s, cat2 = call("GET", "/api/parent/textbooks/catalog" + qs(subject="math", grade="一年级"), token=ptok)
check("按学科+年级筛选", s == 200 and cat2.get("count", 0) > 0, cat2.get("count"))
if cat2.get("books"):
    b0 = cat2["books"][0]
    check("筛选结果确实是数学一年级", b0["subject_code"] == "math" and b0["grade"] == "一年级", b0)

s, cat3 = call("GET", "/api/parent/textbooks/catalog" + qs(q="语文"), token=ptok)
check("关键字搜索可用", s == 200 and cat3.get("count", 0) > 0, cat3.get("count"))

s, r = call("GET", "/api/parent/textbooks/catalog", token=ctok)
check("孩子不能逛家长教材库", s in (403, 401), s)

print("\n=== 4. 本地文件服务 ===")
s, h, blob = raw("GET", f"/api/textbook/{first['id']}/file", token=ptok,
                 headers={"Range": "bytes=0-2047"})
check("Range 请求返回 206", s == 206, s)
check("Content-Range 正确", str(h.get("content-range", "")).startswith("bytes 0-2047/"), h.get("content-range"))
check("拿到的是 PDF", blob[:4] == b"%PDF", blob[:4])

s, h, blob = raw("GET", f"/api/textbook/{first['id']}/file", token=ptok)
check("整本可取且长度一致", s == 200 and len(blob) > 1024, s)
check("声明支持分片", h.get("accept-ranges") == "bytes", h.get("accept-ranges"))

s, _, _ = raw("GET", f"/api/textbook/{first['id']}/file")
check("未登录取教材被拒", s == 401, s)

print("\n=== 5. 家长上传 PDF ===")
s, up = upload("/api/parent/textbooks/upload", ptok, "小测试教材.pdf", TINY_PDF,
               {"title": "测试用教材", "subject": "math", "grade": "一年级", "term": "上册"})
check("上传合法 PDF 成功", s == 200, up)
new_id = (up.get("book") or {}).get("id", 0)
check("返回了教材 id", new_id > 0, up)

s, r = upload("/api/parent/textbooks/upload", ptok, "假的.pdf", b"not a pdf at all", {"title": "x"})
check("非 PDF 内容被拒", s == 400, r)

s, r = upload("/api/parent/textbooks/upload", ptok, "图.png", b"\x89PNG\r\n", {"title": "x"})
check("非 PDF 扩展名被拒", s == 400, r)

s, r = upload("/api/parent/textbooks/upload", ctok, "孩子传.pdf", TINY_PDF, {"title": "x"})
check("孩子不能上传教材", s in (403, 401), s)

print("\n=== 6. 远程地址 ===")
s, r = call("POST", "/api/parent/textbooks/link", {"url": "ftp://x/y.pdf"}, token=ptok)
check("非 http 地址被拒", s == 400, r)

s, r = call("POST", "/api/parent/textbooks/link",
            {"url": "https://example.com/none.pdf", "title": "远程示例",
             "subject": "english", "download": False}, token=ptok)
check("远程地址可只存链接", s == 200 and (r.get("book") or {}).get("status") == "link", r)
link_id = (r.get("book") or {}).get("id", 0)

print("\n=== 7. 编辑与「当前在用」 ===")
s, r = call("PATCH", f"/api/parent/textbook/{new_id}",
            {"title": "改过的名字", "note": "备一本"}, token=ptok)
check("能改书名和备注", s == 200 and (r.get("book") or {}).get("title") == "改过的名字", r)

s, r = call("PATCH", f"/api/parent/textbook/{new_id}", {"is_current": True}, token=ptok)
check("设为当前在用", s == 200 and (r.get("book") or {}).get("is_current") is True, r)

s, r = call("PATCH", f"/api/parent/textbook/{first['id']}", {"is_current": True}, token=ptok)
s, shelf = call("GET", "/api/parent/textbooks", token=ptok)
cur = [b for b in shelf.get("books", []) if b.get("is_current") and b.get("subject") == "math"]
check("同学科只留一本在用", len(cur) == 1, f"实际 {len(cur)} 本")

print("\n=== 8. 阅读进度 ===")
s, r = call("PUT", f"/api/child/textbook/{new_id}/progress",
            {"last_page": 7, "page_count": 40, "seconds": 90}, token=ctok)
check("孩子能存阅读进度", s == 200 and r.get("last_page") == 7, r)

s, cshelf = call("GET", "/api/child/textbooks", token=ctok)
mine = [b for b in cshelf.get("books", []) if b["id"] == new_id]
check("进度能读回来", mine and mine[0]["last_page"] == 7, mine[:1])
check("总页数被记住", mine and mine[0]["page_count"] == 40, mine[:1])

s, r = call("PUT", f"/api/child/textbook/{new_id}/progress", {"last_page": 1}, token=ptok)
check("家长不能替孩子存进度（需孩子身份）", s in (403, 401), s)

print("\n=== 9. 阅读作业闭环 ===")
today = dt.date.today().isoformat()
s, r = call("POST", "/api/parent/reading",
            {"kid_id": kid_id, "textbook_id": new_id, "page_from": 1, "page_to": 5,
             "points": 3, "note": "读完说说看到了什么"}, token=ptok)
check("家长能布置阅读作业", s == 200, r)
rid = (r.get("reading") or {}).get("id", 0)

s, r = call("POST", "/api/parent/reading",
            {"kid_id": kid_id, "textbook_id": new_id, "page_from": 1, "page_to": 90}, token=ptok)
check("超出总页数被拒", s == 400, r)

s, r = call("POST", "/api/parent/reading",
            {"kid_id": kid_id, "textbook_id": new_id, "page_from": 1, "page_to": 61}, token=ptok)
check("一次布置超过 60 页被拒", s == 400, r)

s, r = call("POST", "/api/parent/reading",
            {"kid_id": kid_id, "textbook_id": link_id, "page_from": 1, "page_to": 2}, token=ptok)
check("只存链接的教材不能布置作业", s == 400, r)

s, r = call("GET", "/api/child/readings", token=ctok)
check("孩子能看到这份作业", s == 200 and any(x["id"] == rid for x in r.get("items", [])), r.get("items"))

s, before = call("GET", "/api/child/home", token=ctok)
coin_before = before["coin"]["available"]

s, r = call("POST", f"/api/child/reading/{rid}/done", {"evidence_text": "看到小蝌蚪"}, token=ctok)
check("孩子能标记读完", s == 200 and r.get("status") == "done", r)

s, r = call("POST", f"/api/child/reading/{rid}/done", {"evidence_text": "再来一次"}, token=ctok)
check("同一份不能重复交", s == 400, r)

s, r = call("POST", "/api/parent/reading/review", {"id": rid, "action": "approve"}, token=ptok)
awarded = r.get("awarded", 0)
check("家长确认后加分", s == 200 and awarded > 0, r)

s, after = call("GET", "/api/child/home", token=ctok)
# 用 >= 而不是 ==：审批同一次操作里还可能解锁成就、续上连续打卡，
# 那些也会入账。这里要验证的是"阅读作业这笔钱确实到了"，不是总账恰好等于多少。
check("星星币确实增加", after["coin"]["available"] >= coin_before + awarded,
      f"{coin_before} → {after['coin']['available']}，至少应 +{awarded}")

s, r = call("POST", "/api/parent/reading/review", {"id": rid, "action": "approve"}, token=ptok)
check("重复审批被拦截", s == 400, r)

s, r = call("GET", "/api/parent/readings", token=ptok)
check("家长能看到作业列表", s == 200 and len(r.get("items", [])) > 0)

print("\n=== 10. 越权与删除保护 ===")
s, r = call("POST", "/api/parent/reading",
            {"kid_id": 999999, "textbook_id": new_id, "page_from": 1, "page_to": 2}, token=ptok)
check("不存在的孩子被拒", s == 404, r)

s, r = call("DELETE", f"/api/parent/textbook/{new_id}", token=ptok)
check("挂着作业的教材不能删", s == 400, r)

s, r = call("DELETE", f"/api/parent/reading/{rid}", token=ptok)
check("能删除阅读作业", s == 200, r)

s, r = call("DELETE", f"/api/parent/textbook/{link_id}", token=ptok)
check("能删除教材", s == 200, r)

s, r = call("DELETE", f"/api/parent/textbook/{new_id}", token=ptok)
check("作业删掉后教材可删", s == 200, r)

s, r = call("GET", f"/api/parent/textbook/{new_id}/status", token=ptok)
check("删掉的书状态查不到", s == 404, r)

print()
print("=" * 46)
print(f"  通过 {PASS} 项，失败 {FAIL} 项")
print("=" * 46)
