# -*- coding: utf-8 -*-
"""표 — 원고에 없던 표를 작업대에서 넣는다.

## 왜 공용인가

표는 어느 계열에나 필요하고 모양도 같다(머리줄·칸·괘선). 계열마다 따로 만들면
계열이 늘 때마다 또 만들어야 하고, 고칠 때마다 다 고쳐야 한다. 그래서 자료
모양과 HTML 을 여기 한 곳에 둔다.

    {"t": "table",
     "head": ["머리1", "머리2"],          # 없어도 된다
     "rows": [["가", "나"], ["다", "라"]],
     "align": ["left", "center"],          # 칸별 정렬(없으면 왼쪽)
     "widths": ["40%", "60%"]}             # 칸 너비(없으면 고르게)

칸 하나하나는 **rich** 라 굵게·밑줄·글자 서식이 그대로 들어간다.

## ⚠ 면을 넘어갈 때

표가 길면 조판이 면을 넘긴다. 그때 **머리줄이 다음 면에도 나와야** 읽을 수
있다 — `thead {display: table-header-group}` 이 그 일을 한다(실측으로 확인했다).

## ⚠ 자리표

칸마다 자리표를 심어야 작업대에서 **그 칸만** 고칠 수 있다.
`…blocks.3.rows.1.0` 처럼 행·열 번호가 그대로 경로가 된다.
"""
from core.render_vivlio import refs as _refs
from core.render_vivlio import richtext as _rt

CSS = """
/* 표 — 작업대가 넣은 표(공용). 계열 테마가 덮어써도 된다. */
table.viv-tbl { border-collapse: collapse; width: 100%; margin: 2mm 0; }
table.viv-tbl th, table.viv-tbl td {
  border: 0.4pt solid currentColor; padding: 1mm 1.5mm; vertical-align: top;
}
table.viv-tbl thead { display: table-header-group; }  /* 면 넘어가면 머리 반복 */
table.viv-tbl th { font-weight: 700; }
"""


def html(block, ref="", inl=None, esc=None):
    """표 블록 → HTML.

    `inl` 은 계열의 rich→HTML 함수다(빈칸·서식 처리가 계열마다 달라서).
    안 주면 공용 것을 쓴다.
    """
    inl = inl or (lambda x: _rt.to_html(x, blanks=False))
    o = ['<table class="viv-tbl">']
    widths = block.get("widths") or []
    if widths:
        o.append("<colgroup>")
        for w in widths:
            o.append('<col style="width:%s">' % w)
        o.append("</colgroup>")
    align = block.get("align") or []

    def cell(tag, v, i, cref):
        st = (' style="text-align:%s"' % align[i]) if i < len(align) else ""
        mark = _refs.mark(cref) if cref else ""
        return "<%s%s%s>%s</%s>" % (tag, mark, st, inl(v), tag)

    head = block.get("head")
    if head:
        o.append("<thead><tr>")
        for i, v in enumerate(head):
            o.append(cell("th", v, i, f"{ref}.head.{i}" if ref else ""))
        o.append("</tr></thead>")
    o.append("<tbody>")
    for r, row in enumerate(block.get("rows") or []):
        o.append("<tr>")
        for i, v in enumerate(row):
            o.append(cell("td", v, i, f"{ref}.rows.{r}.{i}" if ref else ""))
        o.append("</tr>")
    o.append("</tbody></table>")
    return "".join(o)


def new(cols=2, rows=2, head=True):
    """빈 표 하나. 작업대의 '표 넣기' 가 쓴다."""
    b = {"t": "table", "rows": [["" for _ in range(cols)] for _ in range(rows)]}
    if head:
        b["head"] = ["" for _ in range(cols)]
    return b


def plain(block):
    """검수·대조용 민글 — 표도 글이라 전수 대조에 들어가야 한다."""
    out = []
    for v in (block.get("head") or []):
        out.append(_rt.plain(v))
    for row in (block.get("rows") or []):
        for v in row:
            out.append(_rt.plain(v))
    return " ".join(x for x in out if x)
