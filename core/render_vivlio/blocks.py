"""단락 목록 안에 끼어드는 **덩어리** — 표·상자·목차를 한 곳에서 가른다.

계열마다 `if p.get('t') in ('table', 'box')` 를 적어 두면, 덩어리를 하나
늘릴 때마다 계열을 전부 찾아 고쳐야 한다 — 그러다 한 곳을 빠뜨리면 그 책에서만
**괘선 없이 글자만** 나온다(표에서 실제로 겪었다).

그래서 가르는 자리를 한 곳에 둔다:

    if blocks.is_block(p):
        out.append(blocks.html(p, ref=r, inl=inl))

⚠ 새 덩어리를 더할 때는 `KINDS` 에 한 줄, CSS 는 `knobs.py` 에 한 줄이다.
"""
from core.render_vivlio import box as _box
from core.render_vivlio import table as _tbl
from core.render_vivlio import toc as _toc

KINDS = {
    "table": _tbl,
    "box": _box,
    "toc": _toc,
}


def is_block(p):
    return isinstance(p, dict) and p.get("t") in KINDS


def html(p, ref="", inl=None, esc=None):
    """덩어리 하나 → HTML. 모르는 것은 **빈 문자열**(조용히 넘기지는 않는다)."""
    mod = KINDS.get(p.get("t")) if isinstance(p, dict) else None
    if mod is None:
        return ""
    try:
        return mod.html(p, ref=ref, inl=inl, esc=esc)
    except TypeError:
        # 상자는 `esc` 를 안 받는다 — 받는 것만 준다
        return mod.html(p, ref=ref, inl=inl)


def plain(p):
    """검수 전수 대조용 — 덩어리 안의 글도 글이다."""
    mod = KINDS.get(p.get("t")) if isinstance(p, dict) else None
    fn = getattr(mod, "plain", None) if mod else None
    return fn(p) if fn else ""
