"""목차 — 제목을 모아 **면 번호와 함께** 세운다(인디자인의 목차).

## 면 번호를 사람이 적으면 안 된다

흐르는 조판에서 면 번호는 조판이 끝나야 정해진다. 그래서 목차 항목은 가리킬
자리만 들고 있고, 번호는 **조판 엔진이 채운다**(`target-counter`).

    {"t": "toc", "title": "차례",
     "items": [{"ref": "lessons.0.problems.0", "label": "1과 본문1"}, …]}

실측(148×210, 4면 문서): 항목마다 점선(`leader`)과 면 번호 2·3·4 가 찍혔고,
PDF 에는 **누를 수 있는 링크 주석**까지 들어갔다.

⚠ 가리키는 자리에는 `id="vrefN"` 이 있어야 한다 — 자리표를 붙인 자리만 된다.
  `refs.num()` 이 그 번호를 준다(아직 안 그린 자리도 미리 번호를 잡아 둔다).
"""
import html as _h

from core.render_vivlio import refs as _refs

KIND = "toc"


def new(title="차례", items=None):
    return {"t": KIND, "title": title, "items": list(items or [])}


def html(block, ref="", inl=None, esc=None):
    """목차 블록 → HTML. `inl` 은 서식 있는 글을 그리는 함수(계열이 준다)."""
    if not isinstance(block, dict):
        return ""
    esc = esc or (lambda x: _h.escape(str(x)))
    ink = inl or esc
    o = ['<nav%s>' % (_refs.mark(ref, "viv-toc") if ref
                      else ' class="viv-toc"')]
    title = block.get("title")
    if title:
        o.append('<p class="viv-toc-t">%s</p>' % ink(title))
    for i, it in enumerate(block.get("items") or []):
        if not isinstance(it, dict):
            continue
        label = it.get("label", "")
        tgt = _refs.num(it.get("ref", ""))
        r = ("%s.items.%d" % (ref, i)) if ref else ""
        lvl = " lv%d" % int(it.get("level") or 1)
        many = [x for x in (it.get("refs") or []) if x]
        if many:
            # 색인 — 한 낱말이 여러 면에 나온다. 면마다 번호를 하나씩 단다.
            nums = [_refs.num(x) for x in many]
            body = ink(label) + '<span class="viv-toc-pp">' + ", ".join(
                '<a href="#vref%d"></a>' % n for n in nums if n) + '</span>'
        elif tgt:
            body = '<a href="#vref%d">%s</a>' % (tgt, ink(label))
        else:
            # 가리킬 자리가 없으면 **번호 없이** 글만 — 조용히 빠뜨리지 않는다
            body = ink(label)
        o.append('<p%s>%s</p>'
                 % (_refs.mark(r, "viv-toc-i" + lvl) if r
                    else ' class="viv-toc-i%s"' % lvl, body))
    o.append('</nav>')
    return "".join(o)


def plain(block):
    """검수 전수 대조용 — 목차도 글이다."""
    if not isinstance(block, dict):
        return ""
    out = [str(block.get("title") or "")]
    for it in block.get("items") or []:
        if isinstance(it, dict):
            out.append(str(it.get("label") or ""))
    return "\n".join(x for x in out if x)


# 점선과 면 번호는 **조판 엔진**이 채운다. 계열 테마가 덮어써도 된다.
CSS = """
/* 목차 — 면 번호는 `target-counter` 가 채운다(사람이 적으면 어긋난다). */
.viv-toc { break-inside: auto; }
.viv-toc-t { font-size: 13pt; font-weight: 700; margin: 0 0 3mm; }
.viv-toc-i { margin: 0 0 1.2mm; }
.viv-toc-i.lv2 { padding-left: 5mm; }
.viv-toc-i.lv3 { padding-left: 10mm; }
.viv-toc-i a { text-decoration: none; color: inherit; }
.viv-toc-i a::after { content: leader('.') target-counter(attr(href url), page); }

/* 색인 — 한 낱말에 면 번호가 여럿. 점선 없이 번호만 늘어놓는다. */
.viv-toc-pp { margin-left: 2mm; }
.viv-toc-pp a::after { content: target-counter(attr(href url), page); }
"""
