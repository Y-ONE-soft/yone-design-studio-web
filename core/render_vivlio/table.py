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

## 칸 합치기

인디자인의 "셀 병합" 이다. 합친 칸은 **몇 칸을 먹는지**를 들고 있고, 먹힌
자리는 `null` 로 비워 둔다 — 자리를 지워 버리면 뒤 칸이 앞으로 밀려 표가
어긋난다(행마다 칸 수가 달라진다).

    "rows": [[{"v": "합친 칸", "c": 2, "r": 2}, null],
             [null,                              null]]

`{"v": …}` 인 dict 만 합친 칸이다. 서식 조각(`{"t": …}`)과 헷갈리지 않는다.

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
/* 표 — 작업대가 넣은 표(공용). 계열 테마가 덮어써도 된다.
   모양은 표마다 다를 수 있어 **변수**로 받는다 — 안 주면 아래 기본값이라,
   모양을 안 정한 표는 예전과 한 글자도 다르지 않다. */
table.viv-tbl { border-collapse: collapse; width: 100%; margin: 2mm 0; }
table.viv-tbl th, table.viv-tbl td {
  border: var(--tb-line, 0.4pt solid currentColor);
  padding: var(--tb-pad, 1mm 1.5mm);
  vertical-align: var(--tb-valign, top);
}
table.viv-tbl thead { display: table-header-group; }  /* 면 넘어가면 머리 반복 */
table.viv-tbl th {
  font-weight: 700;
  background: var(--tb-headbg, transparent);
  color: var(--tb-headfg, inherit);
}
table.viv-tbl tr { height: var(--tb-rowh, auto); }
"""

# 표 모양으로 받는 것 — 그 밖의 것은 무시한다(아무 CSS 나 받으면 안 된다)
STYLE = {
    "line": "--tb-line",        # 괘선 (`0.4pt solid #333`)
    "pad": "--tb-pad",          # 칸 안 여백 (`1mm 1.5mm`)
    "rowh": "--tb-rowh",        # 줄 높이 (`8mm`)
    "headbg": "--tb-headbg",    # 머리줄 바탕
    "headfg": "--tb-headfg",    # 머리줄 글자색
    "valign": "--tb-valign",    # 칸 안 세로 맞춤 (top·middle·bottom)
    "font-size": "font-size",   # 표 전체 글자 크기
    "line-height": "line-height",
}


def html(block, ref="", inl=None, esc=None):
    """표 블록 → HTML.

    `inl` 은 계열의 rich→HTML 함수다(빈칸·서식 처리가 계열마다 달라서).
    안 주면 공용 것을 쓴다.
    """
    inl = inl or (lambda x: _rt.to_html(x, blanks=False))
    # ⚠ 표 **자신**에도 자리표를 단다. 예전에는 칸에만 있어서, 표에 이름 붙인
    #   스타일(`ts-…`)을 걸어도 **얹힐 자리가 없었다**.
    o = ['<table%s%s>' % (_refs.mark(ref, "viv-tbl") if ref
                          else ' class="viv-tbl"', _style_attr(block))]
    widths = block.get("widths") or []
    if widths:
        o.append("<colgroup>")
        for w in widths:
            o.append('<col style="width:%s">' % w)
        o.append("</colgroup>")
    align = block.get("align") or []

    def cell(tag, v, i, cref):
        c, r, val = span(v)
        # 칸 모양(셀 스타일)이 **열 정렬보다 뒤**다 — 칸에 준 것이 이긴다.
        parts = []
        if i < len(align):
            parts.append("text-align:%s" % align[i])
        cs = cell_style(v)
        if cs:
            parts.append(cs)
        st = (' style="%s"' % ";".join(parts)) if parts else ""
        sp = (' colspan="%d"' % c if c > 1 else "") + (' rowspan="%d"' % r
                                                        if r > 1 else "")
        mark = _refs.mark(cref) if cref else ""
        return "<%s%s%s%s>%s</%s>" % (tag, mark, sp, st, inl(val), tag)

    head = block.get("head")
    if head:
        o.append("<thead><tr>")
        for i, v in enumerate(head):
            if v is None:              # 옆 칸에 먹힌 자리 — 그리지 않는다
                continue
            o.append(cell("th", v, i, f"{ref}.head.{i}" if ref else ""))
        o.append("</tr></thead>")
    o.append("<tbody>")
    for r, row in enumerate(block.get("rows") or []):
        o.append("<tr>")
        for i, v in enumerate(row):
            if v is None:
                continue
            o.append(cell("td", v, i, f"{ref}.rows.{r}.{i}" if ref else ""))
        o.append("</tr>")
    o.append("</tbody></table>")
    return "".join(o)


def _style_attr(block):
    """표 모양 → `style="…"`. **정한 것이 없으면 빈 문자열**이다.

    ⚠ 빈 `style=""` 도 남기면 안 된다 — 모양을 안 정한 표까지 HTML 이 달라져
      회귀 대조가 시끄러워진다.
    """
    st = block.get("style") or {}
    out = []
    for k, css in STYLE.items():
        v = str(st.get(k) or "").strip()
        if not v or any(c in v for c in "{};<>\"'"):
            continue
        out.append("%s:%s" % (css, v))
    return (' style="%s"' % ";".join(out)) if out else ""


# 칸 하나에 줄 수 있는 모양 — 인디자인의 **셀 스타일**에 해당한다.
# ⚠ 아무 CSS 나 받으면 안 된다(표가 통째로 흔들린다).
CELL_STYLE = ("background", "color", "text-align", "vertical-align",
              "font-weight", "font-size", "border", "padding")


def cell_style(v):
    """그 칸에 걸린 모양 → `style="…"`. 없으면 빈 문자열."""
    if not (isinstance(v, dict) and "v" in v and "t" not in v):
        return ""
    st = v.get("st") or {}
    out = []
    for k in CELL_STYLE:
        val = str(st.get(k) or "").strip()
        if val and not any(c in val for c in "{};<>\"'"):
            out.append("%s:%s" % (k, val))
    return (";".join(out)) if out else ""


def span(v):
    """칸 하나 → (가로로 먹는 칸 수, 세로로 먹는 줄 수, 글).

    ⚠ 서식 조각(`{"t": "글", "b": 1}`)과 헷갈리면 안 된다. 합친 칸은 `v` 를
      가진 dict 뿐이다 — **모양만 준 칸**(`{"v": …, "st": …}`)도 여기 든다.
    """
    if isinstance(v, dict) and "v" in v and "t" not in v:
        try:
            c = max(1, int(v.get("c") or 1))
            r = max(1, int(v.get("r") or 1))
        except (TypeError, ValueError):
            c = r = 1
        return c, r, v.get("v")
    return 1, 1, v


def _grid(block):
    """머리줄까지 한 판으로 — 합치기는 머리줄도 넘어갈 수 있어야 한다."""
    rows = block.get("rows") or []
    head = block.get("head")
    return ([head] if head is not None else []) + rows, (head is not None)


def _put(block, r, c, v, has_head):
    if has_head:
        if r == 0:
            block["head"][c] = v
            return
        r -= 1
    block["rows"][r][c] = v


def set_cell_style(block, r, c, props):
    """칸 하나에 모양을 준다(머리줄이 0행). 빈 값은 **뗀다**.

    ⚠ 글을 잃지 않는다 — 모양만 주는 칸도 `{"v": 글}` 그릇에 담는다.
    """
    grid, has_head = _grid(block)
    r, c = int(r), int(c)
    if r < 0 or r >= len(grid) or c < 0 or c >= len(grid[r]):
        raise ValueError("표 밖입니다")
    cur = grid[r][c]
    if cur is None:
        raise ValueError("옆 칸에 먹힌 자리입니다 — 합친 칸을 고르세요")
    cc, rr, val = span(cur)
    st = dict((cur.get("st") or {}) if isinstance(cur, dict) and "v" in cur
              else {})
    for k, v in (props or {}).items():
        if k not in CELL_STYLE:
            raise ValueError("모르는 항목: %s" % k)
        v = str(v or "").strip()
        if v:
            st[k] = v
        else:
            st.pop(k, None)
    if not st and cc == 1 and rr == 1:
        _put(block, r, c, val, has_head)          # 모양도 합침도 없으면 민 글로
        return block
    cell = {"v": val}
    if cc > 1:
        cell["c"] = cc
    if rr > 1:
        cell["r"] = rr
    if st:
        cell["st"] = st
    _put(block, r, c, cell, has_head)
    return block


def merge(block, r0, c0, r1, c1):
    """네모난 자리를 한 칸으로 합친다(인디자인의 셀 병합).

    ⚠ 이미 합쳐진 칸이 걸치면 **거절한다.** 겹친 채로 두면 브라우저가
      제멋대로 자리를 밀어 표가 통째로 어긋난다 — 되돌리기도 어렵다.
    ⚠ 글은 **버리지 않는다.** 먹히는 칸에 글이 있으면 이어 붙인다.
    """
    grid, has_head = _grid(block)
    r0, r1 = sorted((int(r0), int(r1)))
    c0, c1 = sorted((int(c0), int(c1)))
    if r0 < 0 or c0 < 0 or r1 >= len(grid) or c1 >= max(len(x) for x in grid):
        raise ValueError("표 밖입니다")
    if r0 == r1 and c0 == c1:
        raise ValueError("한 칸은 합칠 수 없습니다 — 두 칸 이상 고르세요")
    texts = []
    for r in range(r0, r1 + 1):
        for c in range(c0, c1 + 1):
            v = grid[r][c] if c < len(grid[r]) else None
            cc, rr, val = span(v)
            if (cc > 1 or rr > 1) and not (r == r0 and c == c0):
                raise ValueError("이미 합쳐진 칸이 걸립니다 — 먼저 나누세요")
            if v is None and not (r == r0 and c == c0):
                raise ValueError("이미 합쳐진 칸이 걸립니다 — 먼저 나누세요")
            from core.render_vivlio import richtext as _r
            t = _r.plain(val).strip()
            if t:
                texts.append(t)
    for r in range(r0, r1 + 1):
        for c in range(c0, c1 + 1):
            _put(block, r, c, None, has_head)
    _put(block, r0, c0,
         {"v": " ".join(texts), "c": c1 - c0 + 1, "r": r1 - r0 + 1}, has_head)
    return block


def unmerge(block, r, c):
    """합친 칸을 도로 나눈다. 먹혔던 자리는 빈 칸으로 돌아온다."""
    grid, has_head = _grid(block)
    r, c = int(r), int(c)
    if r >= len(grid) or c >= len(grid[r]):
        raise ValueError("표 밖입니다")
    cc, rr, val = span(grid[r][c])
    if cc == 1 and rr == 1:
        raise ValueError("합쳐진 칸이 아닙니다")
    for i in range(r, r + rr):
        for j in range(c, c + cc):
            _put(block, i, j, "", has_head)
    _put(block, r, c, val, has_head)
    return block


def _cols(block):
    head = block.get("head")
    rows = block.get("rows") or []
    return len(head or (rows[0] if rows else [])) or 1


def _spans_row(block, r):
    """`r` 번째 줄(머리줄이 0)을 **가로지르는 합친 칸**이 있나."""
    grid, _ = _grid(block)
    for i in range(0, min(r, len(grid))):
        for v in grid[i]:
            _c, rr, _v = span(v)
            if rr > 1 and i + rr > r:
                return True
    return False


def _spans_col(block, c):
    grid, _ = _grid(block)
    for row in grid:
        for j in range(0, min(c, len(row))):
            cc, _r, _v = span(row[j])
            if cc > 1 and j + cc > c:
                return True
    return False


def add_row(block, at=None):
    """줄 하나를 **그 자리에** 넣는다(끝이면 맨 뒤).

    ⚠ 합친 칸이 그 자리를 가로지르면 거절한다 — 넣으면 칸 수가 어긋나 표가
      통째로 밀린다(되돌리기도 어렵다).
    """
    rows = block.setdefault("rows", [])
    n = len(rows)
    at = n if at is None else max(0, min(int(at), n))
    if _spans_row(block, at + (1 if block.get("head") is not None else 0)):
        raise ValueError("합친 칸이 걸립니다 — 먼저 나누세요")
    rows.insert(at, ["" for _ in range(_cols(block))])
    return block


def del_row(block, at=None):
    rows = block.get("rows") or []
    if len(rows) <= 1:
        raise ValueError("마지막 줄은 지울 수 없습니다")
    at = len(rows) - 1 if at is None else max(0, min(int(at), len(rows) - 1))
    off = 1 if block.get("head") is not None else 0
    if _spans_row(block, at + off) or any(
            span(v)[1] > 1 for v in rows[at]):
        raise ValueError("합친 칸이 걸립니다 — 먼저 나누세요")
    rows.pop(at)
    return block


def add_col(block, at=None):
    n = _cols(block)
    at = n if at is None else max(0, min(int(at), n))
    if _spans_col(block, at):
        raise ValueError("합친 칸이 걸립니다 — 먼저 나누세요")
    if block.get("head") is not None:
        block["head"].insert(at, "")
    for r in block.get("rows") or []:
        r.insert(at, "")
    for key in ("align", "widths"):
        if isinstance(block.get(key), list) and len(block[key]) >= at:
            block[key].insert(at, block[key][min(at, len(block[key]) - 1)]
                              if block[key] else "")
    return block


def del_col(block, at=None):
    n = _cols(block)
    if n <= 1:
        raise ValueError("마지막 칸은 지울 수 없습니다")
    at = n - 1 if at is None else max(0, min(int(at), n - 1))
    grid, _ = _grid(block)
    if _spans_col(block, at) or any(
            len(row) > at and span(row[at])[0] > 1 for row in grid):
        raise ValueError("합친 칸이 걸립니다 — 먼저 나누세요")
    if block.get("head"):
        block["head"].pop(at)
    for r in block.get("rows") or []:
        if len(r) > at:
            r.pop(at)
    for key in ("align", "widths"):
        if isinstance(block.get(key), list) and len(block[key]) > at:
            block[key].pop(at)
    return block


def new(cols=2, rows=2, head=True):
    """빈 표 하나. 작업대의 '표 넣기' 가 쓴다."""
    b = {"t": "table", "rows": [["" for _ in range(cols)] for _ in range(rows)]}
    if head:
        b["head"] = ["" for _ in range(cols)]
    return b


def plain(block):
    """검수·대조용 민글 — 표도 글이라 전수 대조에 들어가야 한다.

    ⚠ 합친 칸도 글이다. `{"v": …}` 를 그냥 넘기면 **검수에서 글이 사라진다.**
    """
    out = []
    for row in [block.get("head") or []] + list(block.get("rows") or []):
        for v in row:
            if v is None:
                continue
            out.append(_rt.plain(span(v)[2]))
    return " ".join(x for x in out if x)
