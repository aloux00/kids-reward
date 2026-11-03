# -*- coding: utf-8 -*-
"""
把 ChinaTextbook 仓库的目录树抓下来，生成一份**离线索引** 。

为什么要这一步：手机 App 里如果要"浏览有哪些教材"，就得调 GitHub 列目录，
而 GitHub 在国内随时会被重置（这正是森灵那套"多源代理"方案用起来报错的原因）。
索引生成一次存本地，之后 App 只读本地 JSON，只有**真正要点下载时**才碰网络。

    python tools/build_textbook_catalog.py
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ghfetch import fetch  # noqa: E402

REPO = "TapXWorld/ChinaTextbook"
BRANCH = "master"
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "textbook-catalog.json"

# 学科 → 短代码，和 app 里的 category / subject 对齐
SUBJECT_CODE = {
    "语文": "chinese",
    "语文·书法练习指导": "calligraphy",
    "数学": "math",
    "英语": "english",
    "科学": "science",
    "道德与法治": "morality",
    "音乐": "music",
    "美术": "art",
    "艺术": "art",
    "体育与健康": "pe",
    "物理": "physics",
    "化学": "chemistry",
    "生物": "biology",
    "历史": "history",
    "地理": "geography",
    "思想政治": "politics",
    "日语": "japanese",
    "俄语": "russian",
    "信息技术": "it",
    "通用技术": "tech",
}

GRADES = ["一年级", "二年级", "三年级", "四年级", "五年级", "六年级",
          "七年级", "八年级", "九年级", "高一", "高二", "高三"]
TERMS = ["上册", "下册", "全一册", "必修上册", "必修下册"]


def parse_path(path: str) -> dict | None:
    """把 `小学/语文/统编版/义务教育教科书·语文一年级上册.pdf` 拆成结构化字段。

    仓库里的路径层级并不严格一致（有的三层，有的四层，大学目录又不一样），
    所以这里按"能认出来就认，认不出来就留空"处理，绝不因为一本怪名字的书让整批失败。
    """
    parts = path.split("/")
    if len(parts) < 2 or not path.lower().endswith(".pdf"):
        return None

    stage = parts[0]
    subject_raw = parts[1] if len(parts) > 2 else ""
    version = parts[2] if len(parts) > 3 else ""
    filename = parts[-1]
    stem = filename[:-4]

    grade = next((g for g in GRADES if g in stem), "")
    term = next((t for t in TERMS if t in stem), "")
    if not term and "全一册" in stem:
        term = "全一册"

    # 标题去掉"义务教育教科书""普通高中教科书"这类前缀，留着反而占地方
    title = re.sub(r"^(义务教育教科书|普通高中教科书|普通高中课程标准实验教科书)\s*[·・•]?\s*", "", stem)
    title = title.strip(" ··")

    return {
        "path": path,
        "stage": stage,
        "subject": subject_raw,
        "subject_code": SUBJECT_CODE.get(subject_raw, "other"),
        "version": version,
        "grade": grade,
        "term": term,
        "title": title or stem,
    }


def main() -> None:
    url = f"https://api.github.com/repos/{REPO}/git/trees/{BRANCH}?recursive=1"
    print("拉取目录树 …")
    tree = json.loads(fetch([url]))
    if tree.get("truncated"):
        print("⚠ 目录树被截断，结果可能不全")

    books = []
    skipped = 0
    for node in tree.get("tree", []):
        if node.get("type") != "blob":
            continue
        info = parse_path(node["path"])
        if not info:
            skipped += 1
            continue
        info["size"] = int(node.get("size") or 0)
        books.append(info)

    books.sort(key=lambda b: (b["stage"], b["subject_code"], b["grade"], b["term"], b["title"]))

    payload = {
        "repo": REPO,
        "branch": BRANCH,
        "built_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "count": len(books),
        "total_bytes": sum(b["size"] for b in books),
        "books": books,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print(f"✅ {len(books)} 本教材 → {OUT}")
    print(f"   合计 {payload['total_bytes'] / 1048576:.0f} MB，索引体积 {OUT.stat().st_size / 1024:.0f} KB")
    if skipped:
        print(f"   跳过非教材文件 {skipped} 个")


if __name__ == "__main__":
    main()
