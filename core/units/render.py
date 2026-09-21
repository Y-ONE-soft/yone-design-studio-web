"""원자 JSON → SVG. 부품·블록·지면·틀을 **같은 코드**로 그린다.

    단위    mm 가 SVG 사용자 단위다(viewBox 가 mm). 글자 크기·선 굵기는 pt 로 받아 mm 로 바꾼다.
    글      <foreignObject> 안의 HTML — 브라우저가 줄을 바꾼다. 높이는 글자 수로 어림해 아래 원자를 민다.
    토큰    `$이름` → 옷(skin).tokens.color / .font. 없으면 자홍색으로 그리고 경고에 적는다(조용히 넘기지 않는다).
    콘텐츠  세트의 blocks[].fields 가 부품 원자의 bind 로 들어간다. 없는 필드는 견본(sample)으로.
    시스템  bind 가 `sys.*` 면 책이 채운다 — page_no · section · title · tag.

넘침: 칸(zone) 의 flow 가 continue 면 다음 면 같은 칸으로, fixed 면 세트 하나 놓고 칸을 닫는다.
어느 칸에도 안 들어가는 항목은 경고에 적고 건너뛴다(무한 루프 금지).
"""
import json
import math
import re
from xml.sax.saxutils import escape as _x

from core.units import sample

PT = 25.4 / 72.0
GAP_BLOCK = 1.5      # mm — 한 세트 안 블록 사이
GAP_SET = 4.0        # mm — 세트 사이
CIRC = "①②③④⑤⑥⑦⑧⑨⑩"
_NS = 'xmlns="http://www.w3.org/2000/svg"'


def esc(s):
    return _x(str(s), {'"': "&quot;"})


def _by_id(items):
    return {x.get("id"): x for x in (items or []) if isinstance(x, dict) and x.get("id")}


class Ctx(object):
    def __init__(self, skin, lib, sys=None):
        self.skin = skin or {"id": "", "tokens": {}}
        self.parts = _by_id(lib.get("parts"))
        self.blocks = _by_id(lib.get("blocks"))
        self.sys = dict(sys or {})
        self.warnings = []
        self._seen = set()

    def warn(self, msg):
        if msg not in self._seen:
            self._seen.add(msg)
            self.warnings.append(msg)

    def _tok(self, ref, kind, default):
        if ref is None:
            return default
        if not (isinstance(ref, str) and ref.startswith("$")):
            return ref                                    # 직접 값 — 분해 직후엔 허용
        v = ((self.skin.get("tokens") or {}).get(kind) or {}).get(ref[1:])
        if v is None:
            self.warn(f"토큰 없음 {ref} ({kind}) — 옷 {self.skin.get('id') or '(없음)'}")
            return "#ff00ff" if kind == "color" else "sans-serif"
        return v

    def color(self, ref, default="#000000"):
        return self._tok(ref, "color", default)

    def font(self, ref):
        return font_family(self._tok(ref, "font", "sans-serif"))

    def image(self, src):
        p = ((self.skin.get("images") or {}).get(src)) if src else None
        return p


def font_family(name):
    """PDF 의 PostScript 이름(NotoSansCJKkr-Regular)도 브라우저가 찾게 — 원래 이름 + 띄어 쓴 이름 + 기본."""
    base = (name or "").split("-")[0]
    spaced = re.sub(r"(?<=[a-z])(?=[A-Z0-9])|(?<=[A-Z])(?=[A-Z][a-z])", " ", base).replace("OTF", "").strip()
    fams = [name]
    if spaced and spaced != name:
        fams.append(spaced)
    fams.append("sans-serif")
    return ", ".join(f"'{f}'" if f != "sans-serif" else f for f in fams if f)


# ── 글 ─────────────────────────────────────────────────────────────
def rich_html(v):
    if v is None:
        return ""
    if isinstance(v, str):
        return esc(v).replace("\n", "<br/>")
    if isinstance(v, list):
        return "".join(rich_html(x) for x in v)
    if isinstance(v, dict):
        t = esc(v.get("t", ""))
        if v.get("u"):
            t = "<u>" + t + "</u>"
        if v.get("b"):
            t = "<b>" + t + "</b>"
        if v.get("i"):
            t = "<i>" + t + "</i>"
        return t
    return esc(v)


def rich_plain(v):
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "".join(rich_plain(x) for x in v)
    if isinstance(v, dict):
        return str(v.get("t", ""))
    return str(v)


def fmt(v, ftype):
    """필드 값 → (html, plain). choices 는 ①~ 줄로."""
    if ftype == "choices" and isinstance(v, list):
        rows = [(CIRC[i] if i < len(CIRC) else str(i + 1)) + " " + rich_plain(x) for i, x in enumerate(v)]
        return "<br/>".join(esc(r) for r in rows), "\n".join(rows)
    if ftype == "bool":
        s = "✓" if v else ""
        return s, s
    return rich_html(v), rich_plain(v)


def text_h(plain, w_mm, size_pt, leading_pt=None):
    """글이 차지할 높이(mm) 어림 — 한글·한자는 1em, 로마자는 0.52em."""
    em = size_pt * PT
    lead = (leading_pt or size_pt * 1.45) * PT
    lines = 0
    for para in (plain or "").split("\n"):
        width = sum(em * (1.0 if ord(c) > 0x2E7F else 0.52) for c in para)
        lines += max(1, int(math.ceil(width / max(w_mm, 0.1))))
    return lines * lead


# ── 부품 ────────────────────────────────────────────────────────────
def _stroke(ctx, st):
    if not st:
        return 'stroke="none"'
    s = f'stroke="{ctx.color(st.get("color"), "#000000")}" stroke-width="{(st.get("w") or 0.5) * PT:.3f}"'
    if st.get("dash"):
        s += ' stroke-dasharray="' + " ".join(f"{d * PT:.3f}" for d in st["dash"]) + '"'
    return s


def _text_content(ctx, a, values, types):
    """글 원자의 (html, plain). bind → 값 → 없으면 sys → 없으면 견본 글 → 없으면 {bind} 회색."""
    b = a.get("bind")
    if not b:
        return rich_html(a.get("text", "")), a.get("text", "")
    v = values.get(b)
    if v is None and b.startswith("sys."):
        v = ctx.sys.get(b[4:])
    if v is None:
        if a.get("text"):
            return rich_html(a["text"]), a["text"]
        return f'<span style="color:#b0b0b0">{{{esc(b)}}}</span>', "{" + b + "}"
    return fmt(v, types.get(b, "text"))


def _bounds(a):
    if a.get("t") == "line":
        y0, y1 = sorted((a["y1"], a["y2"]))
        return y0, y1 - y0
    return a["y"], a["h"]


def _fit(atoms, sx):
    """가로만 비례로 — 칸 폭에 맞춘다. 원(ellipse)은 자리만 옮기고 크기는 둔다."""
    out = []
    for a in atoms:
        a = dict(a)
        if a.get("t") == "line":
            a["x1"], a["x2"] = a["x1"] * sx, a["x2"] * sx
        else:
            a["x"] = a["x"] * sx
            if a.get("t") != "ellipse":
                a["w"] = a["w"] * sx
        out.append(a)
    return out


def part_svg(ctx, part, values=None, types=None, width=None):
    """부품 → (SVG 조각, 높이 mm). 조각은 부품 원점(0,0) 기준 — 호출자가 translate 로 놓는다.

    width 를 주면 부품 폭을 그 폭에 맞춘다(가로 비례). 글은 폭이 줄면 더 많이 감긴다.
    """
    values = values or {}
    types = types or {}
    atoms = part.get("atoms") or []
    pw = float(part.get("w") or 0)
    if width and pw > 0 and abs(width - pw) > 0.01:
        atoms = _fit(atoms, float(width) / pw)
    # 1) 글이 자라는 만큼
    grown = []                                # (원자 번호, 원래 위, 원래 아래, 왼쪽, 오른쪽, 늘어난 양)
    content = {}
    heights = {}
    for i, a in enumerate(atoms):
        if a.get("t") != "text":
            continue
        html, plain = _text_content(ctx, a, values, types)
        content[i] = html
        need = text_h(plain, a["w"], a["size"], a.get("leading"))
        heights[i] = max(a["h"], need)
        if need > a["h"] + 0.01:
            grown.append((i, a["y"], a["y"] + a["h"], a["x"], a["x"] + a["w"], need - a["h"]))
    # 2) 밀기·늘리기 — 자란 글 아래에 있는 원자는 내려가고, 자란 글을 **가로세로로 감싸는** 상자는 늘어난다
    #    (옆에 나란히 선 원 O/X 는 세로 범위가 같아도 감싸는 게 아니다 — 실측: 원이 타원이 됐다)
    out = []
    bottom = part.get("h", 0)
    for i, a in enumerate(atoms):
        y, h = _bounds(a)
        dy = 0.0
        dh = 0.0
        for gi, gy0, gy1, gx0, gx1, d in grown:
            if gi == i:
                continue                                          # 자기 자신
            if y >= gy1 - 0.01:
                dy += d                                           # 아래 것 → 민다
            elif (a.get("t") in ("rect", "image") and y <= gy0 + 0.01 and y + h >= gy1 - 0.01
                  and a["x"] <= gx0 + 0.01 and a["x"] + a["w"] >= gx1 - 0.01):
                dh += d                                           # 감싸는 상자 → 늘인다
        if a.get("t") == "text":
            h = heights.get(i, h)
        out.append(_atom_svg(ctx, a, dy, h + dh, content.get(i)))
        bottom = max(bottom, y + dy + h + dh)
    return "".join(out), bottom


def _atom_svg(ctx, a, dy, h, html):
    t = a.get("t")
    if t == "text":
        lead = (a.get("leading") or a["size"] * 1.45) * PT
        style = (f"margin:0;font-family:{esc(ctx.font(a.get('font')))};font-size:{a['size'] * PT:.3f}px;"
                 f"line-height:{lead:.3f}px;color:{ctx.color(a.get('color'))};text-align:{a.get('align', 'left')};"
                 f"overflow:hidden;word-break:break-word;white-space:normal")
        return (f'<foreignObject x="{a["x"]}" y="{a["y"] + dy:.3f}" width="{a["w"]}" height="{h:.3f}">'
                f'<div xmlns="http://www.w3.org/1999/xhtml" style="{style}">{html or ""}</div></foreignObject>')
    if t == "line":
        return (f'<line x1="{a["x1"]}" y1="{a["y1"] + dy:.3f}" x2="{a["x2"]}" y2="{a["y2"] + dy:.3f}" '
                f'{_stroke(ctx, a.get("stroke"))} stroke-linecap="butt"/>')
    if t == "rect":
        fill = ctx.color(a["fill"]) if a.get("fill") else "none"
        return (f'<rect x="{a["x"]}" y="{a["y"] + dy:.3f}" width="{a["w"]}" height="{h:.3f}" rx="{a.get("radius", 0)}" '
                f'fill="{fill}" {_stroke(ctx, a.get("stroke"))}/>')
    if t == "ellipse":
        fill = ctx.color(a["fill"]) if a.get("fill") else "none"
        return (f'<ellipse cx="{a["x"] + a["w"] / 2:.3f}" cy="{a["y"] + dy + h / 2:.3f}" rx="{a["w"] / 2:.3f}" ry="{h / 2:.3f}" '
                f'fill="{fill}" {_stroke(ctx, a.get("stroke"))}/>')
    if t == "image":
        src = a.get("src") or ""
        if ctx.image(src):
            href = f"/api/units/image/{esc(ctx.skin.get('id', ''))}/{esc(src)}"
            return (f'<image x="{a["x"]}" y="{a["y"] + dy:.3f}" width="{a["w"]}" height="{h:.3f}" '
                    f'href="{href}" preserveAspectRatio="xMidYMid meet"/>')
        if src:
            ctx.warn(f"이미지 없음 {src} — 옷 {ctx.skin.get('id') or '(없음)'}.images 에 파일을 적을 것")
        return (f'<g><rect x="{a["x"]}" y="{a["y"] + dy:.3f}" width="{a["w"]}" height="{h:.3f}" fill="#e6e6e6"/>'
                f'<text x="{a["x"] + a["w"] / 2:.3f}" y="{a["y"] + dy + h / 2:.3f}" font-size="2.2" fill="#888" '
                f'text-anchor="middle" dominant-baseline="middle">{esc(src or "image")}</text></g>')
    ctx.warn(f"모르는 원자 {t}")
    return ""


def wrap(inner, w, h, bg="#ffffff", extra=""):
    return (f'<svg {_NS} viewBox="0 0 {w:.3f} {h:.3f}" width="{w:.3f}mm" height="{h:.3f}mm" {extra}>'
            f'<rect width="{w:.3f}" height="{h:.3f}" fill="{bg}"/>{inner}</svg>')


def part_standalone(ctx, part, values=None, types=None, pad=2.0):
    frag, h = part_svg(ctx, part, values, types)
    w = part.get("w", 100)
    return wrap(f'<g transform="translate({pad},{pad})">{frag}</g>', w + pad * 2, h + pad * 2)


# ── 블록 ────────────────────────────────────────────────────────────
def variant_of(ctx, block):
    vs = block.get("variants") or []
    want = (ctx.skin.get("variants") or {}).get(block.get("id"))
    for v in vs:
        if v.get("id") == want:
            return v
    if want:
        ctx.warn(f"블록 {block.get('id')} 에 모양 {want} 없음 — 첫 모양으로")
    return vs[0] if vs else None


def block_standalone(ctx, block, fields=None):
    v = variant_of(ctx, block)
    part = ctx.parts.get(v.get("part")) if v else None
    if not part:
        ctx.warn(f"블록 {block.get('id')}: 부품 {(v or {}).get('part')} 없음")
        return wrap("", 60, 10)
    types = {k: (f or {}).get("type", "text") for k, f in (block.get("fields") or {}).items()}
    return part_standalone(ctx, part, sample.fill(block, fields), types)


# ── 지면 ────────────────────────────────────────────────────────────
def _items(ctx, sets):
    items = []
    for s in sets or []:
        blocks = s.get("blocks") or []
        for bi, b in enumerate(blocks):
            blk = ctx.blocks.get(b.get("block"))
            if not blk:
                ctx.warn(f"블록 없음 {b.get('block')} (세트 {s.get('id')})")
                continue
            v = variant_of(ctx, blk)
            part = ctx.parts.get(v.get("part")) if v else None
            if not part:
                ctx.warn(f"블록 {blk['id']}: 부품 {(v or {}).get('part')} 없음")
                continue
            items.append({
                "part": part, "block": blk["id"], "set_kind": s.get("kind"), "set_id": s.get("id"),
                "values": sample.fill(blk, b.get("fields")),
                "types": {k: (f or {}).get("type", "text") for k, f in (blk.get("fields") or {}).items()},
                "first": bi == 0, "last": bi == len(blocks) - 1, "idx": b.get("_i"),   # _i: 캔버스가 page.blocks 번호를 따라오게
            })
    return items


def _zones(page, W, mirror):
    out = []
    for z in page.get("zones") or []:
        x = W - z["x"] - z["w"] if mirror else z["x"]
        if z.get("flow") == "columns":
            n = max(2, int(z.get("cols") or 2))
            g = float(z.get("gutter") or 5)
            cw = (z["w"] - g * (n - 1)) / n
            for i in range(n):
                out.append(dict(z, id=f"{z['id']}.{i + 1}", x=x + i * (cw + g), w=cw, flow="continue"))
        else:
            out.append(dict(z, x=x))
    return out


def _accepts(z, it):
    acc = z.get("accepts")
    return not acc or it["block"] in acc or (it["set_kind"] and it["set_kind"] in acc)


def page_svgs(ctx, page, sets, spec, pno=1, label=""):
    """지면 하나에 세트들을 흘린다 → [{svg, label, page_no}]. 넘치면 같은 지면을 새 면으로."""
    W, H = float(spec["w"]), float(spec["h"])
    items = _items(ctx, sets)
    out = []
    idx = 0
    guard = 0
    while True:
        guard += 1
        if guard > 400:
            ctx.warn("면이 400을 넘었다 — 멈춤")
            break
        mirror = bool(page.get("mirror")) and pno % 2 == 0
        zones = [dict(z, cur=z["y"], closed=False) for z in _zones(page, W, mirror)]
        frags = []
        placed_any = False
        while idx < len(items):
            it = items[idx]
            placed = False
            for z in zones:
                if z["closed"] or not _accepts(z, it):
                    continue
                frag, h = part_svg(ctx, it["part"], it["values"], it["types"], width=z["w"])   # 부품 폭 = 칸 폭
                empty = abs(z["cur"] - z["y"]) < 0.01
                gap = 0 if empty else (GAP_SET if it["first"] else GAP_BLOCK)
                if not empty and z["cur"] + gap + h > z["y"] + z["h"] + 0.01:
                    continue
                if empty and h > z["h"] + 0.01:
                    ctx.warn(f"{page['id']}/{z['id']}: 블록 {it['block']} ({h:.1f}mm) 이 칸({z['h']:.1f}mm)보다 크다")
                frags.append(f'<g transform="translate({z["x"]:.3f},{z["cur"] + gap:.3f})" data-block="{esc(it["block"])}" '
                             f'data-set="{esc(it["set_id"])}"{"" if it.get("idx") is None else f' data-i="{it["idx"]}"'}>{frag}</g>')
                z["cur"] += gap + h
                if z["flow"] == "fixed" and it["last"]:
                    z["closed"] = True
                placed = placed_any = True
                break
            if not placed:
                if not placed_any:
                    ctx.warn(f"{page['id']}: 블록 {it['block']} 을 받는 칸이 없다 — 건너뜀")
                    idx += 1
                    continue
                break
            idx += 1
        out.append({"svg": _page_wrap(ctx, page, zones, frags, W, H, pno, mirror), "label": label, "page_no": pno})
        pno += 1
        if idx >= len(items):
            break
    return out


def _page_wrap(ctx, page, zones, frags, W, H, pno, mirror):
    sysv = dict(ctx.sys, page_no=pno)
    old = ctx.sys
    ctx.sys = sysv
    chrome = []
    for ci, c in enumerate(page.get("chrome") or []):
        part = ctx.parts.get(c.get("part"))
        if not part:
            ctx.warn(f"{page['id']}: 고정 부품 {c.get('part')} 없음")
            continue
        frag, _h = part_svg(ctx, part, {})
        x = W - c["x"] - part.get("w", 0) if mirror else c["x"]
        chrome.append(f'<g transform="translate({x:.3f},{c["y"]:.3f})" data-chrome="{esc(part["id"])}" data-ci="{ci}">{frag}</g>')
    # 자유 배치 — 캔버스에서 좌표에 놓은 요소(블록은 견본 값으로, 부품은 그대로). 파워포인트의 개체.
    # 콘텐츠 블록 자리는 캔버스에서만 그린다(실제 콘텐츠는 세트로 흘러 든다). 머리말·쪽번호 같은
    # system 블록과 부품은 언제나 그린다.
    canvas = bool(page.get("_canvas"))
    for fi, it in enumerate(page.get("items") or []):
        blk = ctx.blocks.get(it.get("block")) if it.get("block") else None
        if not canvas and blk is not None and blk.get("source") == "content":
            continue
        frag, part, w = _item_frag(ctx, it)
        if frag is None:
            ctx.warn(f"{page['id']}: 요소 {it.get('block') or it.get('part')} 없음")
            continue
        x = W - it["x"] - w if mirror else it["x"]
        chrome.append(f'<g transform="translate({x:.3f},{it["y"]:.3f})" data-fi="{fi}">{frag}</g>')
    ctx.sys = old
    guides = "" if not zones or page.get("_noguides") else "".join(
        f'<rect class="zone" x="{z["x"]:.3f}" y="{z["y"]:.3f}" width="{z["w"]:.3f}" height="{z["h"]:.3f}" '
        f'fill="none" stroke="#c9b8ff" stroke-width="0.25" stroke-dasharray="1.5 1"/>' for z in zones)
    bg = ctx.color(page.get("background"), "#ffffff") if page.get("background") else "#ffffff"
    return wrap(guides + "".join(frags) + "".join(chrome), W, H, bg, f'data-page="{pno}" data-tpl="{esc(page["id"])}"')


def atom_part(atom):
    """원자 하나를 임시 부품으로 — 캔버스에 낱개로 놓은 글상자·선·면·원·그림."""
    a = dict(atom)
    if a.get("t") == "line":
        w, h = abs(a.get("x2", 0) - a.get("x1", 0)), abs(a.get("y2", 0) - a.get("y1", 0))
    else:
        w, h = a.get("w", 10), a.get("h", 10)
    return {"id": "_atom", "name": "원자", "w": max(w, 0.5), "h": max(h, 0.5), "atoms": [a]}


def _item_frag(ctx, it):
    """자유 배치 요소 하나 → (SVG 조각, 부품, 폭). 블록이면 옷이 고른 모양의 부품 + 견본 값. 원자면 임시 부품."""
    if it.get("atom"):
        part = atom_part(it["atom"])
        w = float(it.get("w") or part["w"])
        frag, _h = part_svg(ctx, part, {}, width=w)
        return frag, part, w
    if it.get("block"):
        blk = ctx.blocks.get(it["block"])
        v = variant_of(ctx, blk) if blk else None
        part = ctx.parts.get(v.get("part")) if v else None
        if not part:
            return None, None, 0
        types = {k: (f or {}).get("type", "text") for k, f in (blk.get("fields") or {}).items()}
        w = float(it.get("w") or part.get("w") or 0)
        frag, _h = part_svg(ctx, part, sample.fill(blk, it.get("fields")), types, width=w)
        return frag, part, w
    part = ctx.parts.get(it.get("part"))
    if not part:
        return None, None, 0
    w = float(it.get("w") or part.get("w") or 0)
    frag, _h = part_svg(ctx, part, {}, width=w)
    return frag, part, w


DEFAULT_SPEC = {"id": "a4", "w": 210.0, "h": 297.0, "bleed": 3.0}


def page_canvas_svgs(ctx, page, spec, sample_set=None):
    """캔버스 미리보기 — 자유 배치 요소(items)를 그린다. 콘텐츠 블록 자리는 견본 값으로.

    sample_set(세트)을 주면 같은 블록의 값을 순서대로 끼운다 — 어법 O/X 줄 셋이면 세트의 1·2·3번 문장.
    (옛 형식: 칸 흐름 배치 page.blocks 도 아직 그린다.) 넘치면 여러 면이 되므로 캔버스는 첫 장만 보인다.
    """
    pg = json.loads(json.dumps(page))
    pg["_noguides"] = True                     # 캔버스는 자유 배치 — 칸 안내선은 안 보인다
    pg["_canvas"] = True                       # 콘텐츠 블록 자리(items)도 견본으로 그린다
    if sample_set:
        queue = {}
        for b in sample_set.get("blocks") or []:
            queue.setdefault(b.get("block"), []).append(b.get("fields") or {})
        for it in pg.get("items") or []:
            q = queue.get(it.get("block"))
            if q and not it.get("fields"):
                it["fields"] = q.pop(0) if len(q) > 1 else q[0]
    sets = []
    for z in pg.get("zones") or []:
        kind = "_canvas:" + z["id"]
        z["accepts"] = [kind]
        blocks = [{"block": b["block"], "fields": {}, "_i": i} for i, b in enumerate(pg.get("blocks") or []) if b.get("zone") == z["id"]]
        if blocks:
            sets.append({"kind": kind, "id": z["id"], "blocks": blocks})
    ctx.sys.setdefault("section", "STEP 2")
    return page_svgs(ctx, pg, sets, spec, 1, pg.get("name", ""))


def plan_svgs(ctx, plan, sets, lib):
    """틀 → 면 목록. 앞면 → 구간(간지 + 지면 반복) → 뒷면. 쪽번호는 이어진다."""
    specs = _by_id(lib.get("specs"))
    pages = _by_id(lib.get("pages"))
    spec = specs.get(plan.get("spec")) or DEFAULT_SPEC
    if plan.get("spec") not in specs:
        ctx.warn(f"규격 {plan.get('spec')} 없음 — A4 로")
    ctx.sys.setdefault("title", plan.get("name", ""))
    out = []
    pno = 1

    def emit(pid, ss, label):
        nonlocal pno
        pg = pages.get(pid)
        if not pg:
            ctx.warn(f"지면 없음 {pid}")
            return
        res = page_svgs(ctx, pg, ss, spec, pno, label)
        out.extend(res)
        pno += len(res)

    for pid in plan.get("front") or []:
        emit(pid, [], "앞")
    for sec in plan.get("sections") or []:
        ctx.sys["section"] = sec.get("name", "")
        if sec.get("divider"):
            emit(sec["divider"], [], sec.get("name", "") + " 간지")
        for pg in sec.get("pages") or []:
            kinds = pg.get("sets")
            ss = [s for s in sets or [] if not kinds or s.get("kind") in kinds]
            if pg.get("repeat") == "each_set":
                for s in ss:
                    emit(pg["page"], [s], f"{sec.get('name', '')} · {s.get('id', '')}")
            else:
                emit(pg["page"], ss, sec.get("name", ""))
    ctx.sys["section"] = ""
    for pid in plan.get("back") or []:
        emit(pid, [], "뒤")
    return out
