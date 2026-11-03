# -*- coding: utf-8 -*-
"""
错题本导出：手写 OOXML，不引入 python-docx 之类第三方包。

为什么自己拼：整个项目坚持零第三方依赖（内网机器也能跑），
而要把 7 岁孩子的错题排成一份能直接打印 A4 的卷子，只需要 Word 里很小的一个子集。

排版原则：
  第一部分是「重做卷」—— 只有题面和留空的横线，孩子不看答案重做一遍；
  第二部分是「参考答案与解析」—— 家长对答案用，或者第二天再讲。
  两份放在同一个文件里，打印时挑页码就行，不用导出两次。
"""
from __future__ import annotations

import zipfile
from datetime import date
from io import BytesIO

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'

# A4 纵向，页边距留够（左边更宽一点，方便装订打孔）
SECT = (
    '<w:sectPr>'
    '<w:pgSz w:w="11906" w:h="16838"/>'
    '<w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1531" '
    'w:header="851" w:footer="992" w:gutter="0"/>'
    '</w:sectPr>'
)

_CN_NUM = "一二三四五六七八九十"


def esc(s) -> str:
    t = str(s if s is not None else "")
    t = "".join(ch for ch in t if ch >= " " or ch in "\n\t")
    return (
        t.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _rpr(bold=False, size=None, color=None, italic=False, mono=False) -> str:
    parts = []
    if italic:
        parts.append("<w:i/>")
    if bold:
        parts.append("<w:b/>")
    if color:
        parts.append(f'<w:color w:val="{color}"/>')
    if size:
        parts.append(f'<w:sz w:val="{size}"/><w:szCs w:val="{size}"/>')
    if mono:
        parts.append('<w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/>')
    return f"<w:rPr>{''.join(parts)}</w:rPr>" if parts else ""


def run(text, **kw) -> str:
    return f'<w:r>{_rpr(**kw)}<w:t xml:space="preserve">{esc(text)}</w:t></w:r>'


def para(runs="", align=None, indent=None, space_after=None,
         space_before=None, keep_next=False) -> str:
    """runs 可以是字符串（单一格式），也可以是已经拼好的 <w:r> 片段。"""
    if isinstance(runs, str):
        runs = run(runs) if runs else ""

    ppr = []
    if align:
        ppr.append(f'<w:jc w:val="{align}"/>')
    if indent:
        ppr.append(f'<w:ind w:left="{indent}"/>')

    bits = []
    if space_before is not None:
        bits.append(f'w:before="{space_before}"')
    if space_after is not None:
        bits.append(f'w:after="{space_after}"')
    if bits:  # 行距统一 1.5 倍，字大一点孩子写着不累
        bits.append('w:line="320" w:lineRule="auto"')
        ppr.append(f"<w:spacing {' '.join(bits)}/>")
    if keep_next:
        ppr.append("<w:keepNext/>")

    head = f"<w:pPr>{''.join(ppr)}</w:pPr>" if ppr else ""
    return f"<w:p>{head}{runs}</w:p>"


def heading(text: str, level: int = 1) -> str:
    if level == 1:
        return f'<w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>{run(text)}</w:p>'
    return f'<w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr>{run(text)}</w:p>'


def blank_line(n: int = 1) -> str:
    return para("") * n


# ------------------------------------------------------------------ 组装
def build_docx(payload: dict, *, with_answers: bool = True,
               with_variants: bool = False) -> bytes:
    """
    payload 直接来自 services.wrong.summary()：
      child / generated_at / total / groups[{name, icon, count, items[dto]}]
    """
    kid = payload.get("child") or {}
    name = kid.get("name") or "小朋友"
    groups = payload.get("groups") or []
    today = payload.get("generated_at") or date.today().isoformat()

    body: list[str] = []

    # ---- 卷头
    body.append(
        para(run(f"《{name}》错题重做练习", bold=True, size="40"), align="center")
    )
    body.append(blank_line())
    stat = " · ".join(f"{g['name']} {g['count']} 题" for g in groups) or "暂无错题"
    body.append(
        para(
            run(f"姓名：＿＿＿＿＿＿　日期：＿＿＿＿＿＿　用时：＿＿＿＿＿＿",
                size="22"),
            align="center",
        )
    )
    body.append(
        para(run(f"{today} 生成 · 共 {payload.get('total', 0)} 题（{stat}）",
                 size="18", color="808080"), align="center")
    )
    body.append(blank_line())
    body.append(
        para(run("先做完所有的题，再翻到最后的参考答案。不会的做个记号，"
                 "讲完之后把这一题重新抄一遍。", size="20", color="595959"),
             align="center")
    )
    body.append(blank_line(2))

    if not groups:
        body.append(para(run("太棒了，这段时间没有需要重做的错题 🎉", size="28"),
                         align="center"))
        return _pack(_doc(body))

    # ---- 第一部分：重做卷
    body.append(heading("第一部分 · 重做", 1))
    for gi, g in enumerate(groups):
        idx = _CN_NUM[gi] if gi < len(_CN_NUM) else str(gi + 1)
        body.append(heading(f"{idx}、{g['name']}（{g['count']} 题）", 2))
        for n, it in enumerate(g["items"], start=1):
            prompt = it.get("prompt") or it.get("question") or ""
            bits = [run(f"{n}. {prompt} ", size="26")]
            tag = it.get("tag") or ""
            cause = it.get("cause_name") or ""
            meta = " · ".join(x for x in (tag, cause) if x)
            if int(it.get("times_wrong") or 0) > 1:
                meta = (meta + " · " if meta else "") + \
                    f"之前错 {it['times_wrong']} 次"
            if meta:
                bits.append(run(f"（{meta}）", size="18", color="A0A0A0"))
            bits.append(run(f"  {it.get('seq') or ''}", size="14", color="C0C0C0"))
            body.append(
                para("".join(bits), indent="360", space_after="180")
            )
            # 手写卷留有作答空间：两条空白线
            if _needs_lines(it):
                body.append(
                    para(run("＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿＿", size="22"),
                         indent="1080", space_after="120")
                )
            if with_variants and it.get("variants"):
                for v in it["variants"]:
                    body.append(
                        para(run(f"　同类练一练：{v.get('prompt') or v.get('question')}",
                                 size="20", color="7B6CF6"),
                             indent="720", space_after="100")
                    )
        body.append(blank_line())

    # ---- 第二部分：答案与解析
    if with_answers:
        body.append(f'<w:p><w:pPr><w:pageBreakBefore/></w:pPr></w:p>')
        body.append(heading("第二部分 · 参考答案与解析", 1))
        for gi, g in enumerate(groups):
            idx = _CN_NUM[gi] if gi < len(_CN_NUM) else str(gi + 1)
            body.append(heading(f"{idx}、{g['name']}", 2))
            for n, it in enumerate(g["items"], start=1):
                line = [run(f"{n}. ", size="22"),
                        run(f"{it.get('question') or ''} ", size="22"),
                        run(f"{it.get('correct_answer') or ''} ", size="22", bold=True)]
                wrong = it.get("wrong_answer") or ""
                if wrong:
                    line.append(run(f"（错写成 {wrong}）", size="18", color="C00000"))
                if it.get("cause_name"):
                    line.append(run(f" ｜{it['cause_name']}", size="18",
                                    color="B06000"))
                line.append(run(f"  {it.get('seq') or ''}", size="14",
                                color="C0C0C0"))
                body.append(para("".join(line), indent="360", space_after="120"))
                for v in (it.get("variants") or []):
                    body.append(
                        para(run(f"　同类题：{v.get('question')} "
                                 f"{v.get('correct_answer')}", size="18",
                                 color="7B6CF6"),
                             indent="720", space_after="100")
                    )
                if it.get("explain"):
                    body.append(
                        para(run(f"　解析：{it['explain']}", size="18", color="595959"),
                             indent="360", space_after="160")
                    )
            body.append(blank_line())

    return _pack(_doc(body))


def _needs_lines(it: dict) -> bool:
    """识字/填空类题本来就有作答位置，只有计算题才需要额外横线。"""
    q = str(it.get("question") or "")
    return True if "＿＿＿" not in q else False


def _doc(body: list) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f"<w:document {W}><w:body>{''.join(body)}{SECT}</w:body></w:document>"
    )


_STYLES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f"<w:styles {W}>"
    "<w:docDefaults>"
    "<w:rPrDefault><w:rPr>"
    '<w:rFonts w:ascii="SimSun" w:eastAsia="SimSun" w:hAnsi="SimSun" w:cs="SimSun"/>'
    '<w:sz w:val="24"/><w:szCs w:val="24"/>'
    "</w:rPr></w:rPrDefault>"
    '<w:pPrDefault><w:pPr><w:spacing w:line="320" w:lineRule="auto"/></w:pPr></w:pPrDefault>'
    "</w:docDefaults>"
    '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
    '<w:name w:val="Normal"/></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/>'
    '<w:basedOn w:val="Normal"/><w:qFormat/>'
    '<w:pPr><w:keepNext/><w:spacing w:before="240" w:after="160"/>'
    '<w:outlineLvl w:val="0"/></w:pPr>'
    '<w:rPr><w:b/><w:sz w:val="34"/><w:szCs w:val="34"/>'
    '<w:color w:val="2B3A8F"/></w:rPr></w:style>'
    '<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/>'
    '<w:basedOn w:val="Normal"/><w:qFormat/>'
    '<w:pPr><w:keepNext/><w:spacing w:before="200" w:after="120"/>'
    '<w:outlineLvl w:val="1"/></w:pPr>'
    '<w:rPr><w:b/><w:sz w:val="28"/><w:szCs w:val="28"/>'
    '<w:color w:val="B06000"/></w:rPr></w:style>'
    "</w:styles>"
)

_CT = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.'
    'openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" ContentType="application/vnd.'
    'openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
    "</Types>"
)

_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
    'relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.'
    'org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/></Relationships>'
)

_DOC_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/'
    'relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.'
    'org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    "</Relationships>"
)


def _pack(document: str) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("_rels/.rels", _ROOT_RELS)
        z.writestr("word/document.xml", document)
        z.writestr("word/styles.xml", _STYLES)
        z.writestr("word/_rels/document.xml.rels", _DOC_RELS)
    return buf.getvalue()
