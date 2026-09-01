# -*- coding: utf-8 -*-
"""자유 배치 상자 — 좌표로 놓는 글상자·그림상자.

## 되는 줄 몰랐다

인디자인의 "프레임을 좌표로 놓기" 는 흐르는 조판에는 없는 개념이라 **못 한다**
고 적어 두었는데, 실측해 보니 된다. 흐름 한가운데 둔 `position:absolute` 상자가
**그 상자가 놓인 면을 기준으로** 정확히 앉는다(둘째 면 top 20mm·right 6mm 확인).

    {"t":"box",
     "at": {"top":"20mm", "right":"6mm", "width":"44mm"},   # 네 변 중 둘 + 크기
     "style": {"border":"0.4pt solid", "padding":"1mm"},    # 모양(선택)
     "paras": ["글", {"t":"굵게","b":1}],                    # 글
     "img": "assets/그림.png"}                               # 또는 그림

## ⚠ 어느 면에 앉는가

**그 상자를 어느 자리에 넣었느냐**가 면을 정한다. 앞 문단이 다음 면으로 밀리면
상자도 따라간다 — 좌표는 면 안에서의 자리일 뿐이다. 인디자인처럼 "3면 여기"
로 못 박으려면 그 면에 앉는 자리에 넣어야 한다.

## ⚠ 글 감싸기는 다른 것이다

상자를 피해 본문이 흐르게 하려면 `position:absolute` 가 아니라 `float` 다
(`wrap: "left"|"right"`). 절대 배치한 상자는 본문 **위에 얹힌다** — 겹치면
글이 가려진다. 그래서 감싸기를 쓸 수 있게 둘 다 둔다.
"""
import html as _html

from core.render_vivlio import refs as _refs
from core.render_vivlio import richtext as _rt

CSS = """
/* 자유 배치 상자 — 작업대가 좌표로 놓은 것(공용) */
.viv-box { box-sizing: border-box; }
.viv-box.abs { position: absolute; z-index: 5; }
.viv-box.wrapL { float: left; margin: 0 3mm 2mm 0; }
.viv-box.wrapR { float: right; margin: 0 0 2mm 3mm; }
.viv-box img { display: block; width: 100%; height: auto; }
"""

# 좌표·크기로 받는 것 — 그 밖의 것은 `style` 로 받는다
AT_KEYS = ("top", "right", "bottom", "left", "width", "height")
_OK = "0123456789.-mmcmptinemrex% "


def _len(v):
    """길이 값만 통과시킨다(`4mm` · `10%`). 이상한 것은 버린다."""
    t = str(v or "").strip()
    if not t or len(t) > 20:
        return ""
    return t if all(c in _OK for c in t.lower()) else ""


def html(block, ref="", inl=None):
    inl = inl or (lambda x: _rt.to_html(x, blanks=False))
    at = block.get("at") or {}
    wrap = block.get("wrap")
    cls = "viv-box " + ({"left": "wrapL", "right": "wrapR"}.get(wrap) or "abs")
    st = []
    for k in AT_KEYS:
        v = _len(at.get(k))
        if v:
            st.append("%s:%s" % (k, v))
    for k, v in (block.get("style") or {}).items():
        if any(c in str(k) + str(v) for c in "{};<>"):
            continue
        st.append("%s:%s" % (k, v))
    style = (' style="%s"' % ";".join(st)) if st else ""
    o = ["<div%s%s>" % (_refs.mark(ref, cls), style)]
    img = block.get("img")
    if img:
        o.append('<img src="%s" alt="">' % _html.escape(str(img)))
    for i, p in enumerate(block.get("paras") or []):
        r = ("%s.paras.%d" % (ref, i)) if ref else ""
        o.append("<p%s>%s</p>" % (_refs.mark(r), inl(p)))
    o.append("</div>")
    return "".join(o)


def new(kind="text"):
    b = {"t": "box", "at": {"top": "20mm", "left": "20mm", "width": "50mm"},
         "style": {"border": "0.4pt solid", "padding": "1.5mm"}}
    if kind == "image":
        b["img"] = ""
    else:
        b["paras"] = [""]
    return b


def plain(block):
    """검수·대조용 민글 — 상자 안 글도 글이다."""
    return " ".join(_rt.plain(p) for p in (block.get("paras") or []))
