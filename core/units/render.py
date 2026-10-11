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
import unicodedata
from html import unescape as _unescape
from xml.sax.saxutils import escape as _x

from core.units import sample

PT = 25.4 / 72.0
TEXT_ZOOM = 100                    # 글상자 배치 해상도 — 지면 1mm 를 100px 로 (아래 _atom_svg_raw 의 글). 10 이면 0.1mm 단위로 반올림돼 빈칸 밑줄 0.176mm 가 0.1mm 로 나왔다
GAP_BLOCK = 1.5      # mm — 한 세트 안 블록 사이
GAP_SET = 4.0        # mm — 세트 사이
CIRC = "①②③④⑤⑥⑦⑧⑨⑩"
_NS = 'xmlns="http://www.w3.org/2000/svg"'


def esc(s):
    return _x(str(s), {'"': "&quot;"})


def _by_id(items):
    return {x.get("id"): x for x in (items or []) if isinstance(x, dict) and x.get("id")}


STYLE_KEYS = ("font", "size", "leading", "color", "align", "tracking", "tsume", "indent", "indent_first", "indent_right", "space_before", "space_after", "b", "i")


# 꾸밈없는 기본 견본 — 브랜드가 하나도 없어도 그린다(인디자인 기본 견본: 검정·종이·회색 · 기본 서체).
# 새 디자인은 직접 색·서체로 그리고, 다 만든 뒤 「브랜드로 등록」하면 브랜드가 생긴다. 브랜드에 없는 견본도 여기서 찾는다.
DEFAULT_SKIN = {"id": "", "name": "기본", "tokens": {
    "color": {"ink": "#231f20", "white": "#ffffff", "rule": "#b8b8b8", "gray": "#e6e6e6"},
    "font": {"body": "Noto Sans CJK KR"}}}


class Ctx(object):
    def __init__(self, skin, lib, sys=None):
        self.skin = skin or DEFAULT_SKIN
        self.skins = list(lib.get("skins") or [])          # 그림은 어느 옷에 등록돼 있든 찾는다
        self.parts = _by_id(lib.get("parts"))
        self.blocks = _by_id(lib.get("blocks"))
        self.pages = _by_id(lib.get("pages"))                 # 넘치면 이어 갈 면(page.cont) 찾기 — 인디자인의 다른 마스터 프레임으로 잇기
        self.sys = dict(sys or {})
        self.warnings = []
        self.print = None                                 # 인쇄 모드 {"bleed": mm, "marks": bool} — 도련 늘림·재단선
        self._at = None                                   # 그리는 중인 요소의 면 안 자리 (x, y, W, H) — 도련 늘림용
        self.issues = []                                  # 검수 — [{level: error|warn|info, msg}]
        self._seen = set()
        self._n = 0
        self.nums = {}          # 번호 매기기 — 목록 이름 → 마지막 번호 (인디자인 「글머리 기호 및 번호 매기기」)
        self.board = 0.0        # 캔버스 대지(pasteboard) mm — 지면 둘레의 회색 자리. 지면 밖 요소도 여기 보인다
        self.layers = {}        # 지면 레이어 {id: {hide, lock, nonprint}} — 숨김·비인쇄를 한꺼번에
        self._item_y = 0.0      # 그리는 중인 요소의 면 안 세로 자리 (기준선 격자용)
        self.map = {}           # 원고 연결표 {원고 유형·블록 id: 이 문서의 블록 id} — 문서(틀)의 map
        self.grid = None        # 기준선 격자 {start, step} — snap_baseline 인 글상자가 줄을 맞춘다

    def uid(self):
        """SVG 안 id(그라디언트·클립) — 한 그림 안에서 겹치지 않게."""
        self._n += 1
        return f"u{self._n}"

    def warn(self, msg):
        self.issue("warn", msg)

    def issue(self, level, msg):
        """검수 항목. error = 책으로 내면 안 되는 것(원고 빠짐·안 실림), warn = 확인할 것(넘침·토큰), info = 알림."""
        if msg not in self._seen:
            self._seen.add(msg)
            if level != "info":
                self.warnings.append(msg)
            self.issues.append({"level": level, "msg": msg})

    def _tok(self, ref, kind, default):
        if ref is None:
            return default
        if not (isinstance(ref, str) and ref.startswith("$")):
            return ref                                    # 직접 값 — 분해 직후엔 허용
        v = ((self.skin.get("tokens") or {}).get(kind) or {}).get(ref[1:])
        if v is None:
            v = DEFAULT_SKIN["tokens"].get(kind, {}).get(ref[1:])          # 기본 견본(잉크·흰색·회색·기본 서체)
        if v is None:
            self.warn(f"토큰 없음 {ref} ({kind}) — 옷 {self.skin.get('id') or '(없음)'}")
            return "#ff00ff" if kind == "color" else "sans-serif"
        return v

    def color(self, ref, default="#000000"):
        return self._tok(ref, "color", default)

    def font(self, ref):
        return font_family(self._tok(ref, "font", "sans-serif"))

    def image(self, src):
        """그림 찾기 — 이 옷에 없으면 다른 옷에서도 찾는다 (그림은 옷을 갈아입어도 그대로여야 한다)."""
        if not src:
            return None
        p = (self.skin.get("images") or {}).get(src)
        if p:
            return p
        for sk in getattr(self, "skins", []):
            p = (sk.get("images") or {}).get(src)
            if p:
                return p
        return None

    def image_href(self, src):
        """그림을 SVG 안에 **박아 넣는다** — PDF 는 파일로 열리므로 서버 주소를 못 읽는다."""
        rel = self.image(src)
        if not rel:
            return None
        key = f"_img_{src}"
        hit = getattr(self, "_imgcache", None)
        if hit is None:
            hit = self._imgcache = {}
        if key in hit:
            return hit[key]
        import base64
        import mimetypes
        import os as _os
        from core.units import store as _store
        path = rel if _os.path.isabs(rel) else _os.path.join(_store.udir(), rel)
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
        except OSError:
            hit[key] = None          # 파일을 못 읽으면 화면용 주소로 넘어간다 (PDF 는 빈 자리)
            return None
        mime = mimetypes.guess_type(path)[0] or "image/png"
        hit[key] = f"data:{mime};base64," + base64.b64encode(raw).decode()
        return hit[key]

    def cstyle_css(self, name):
        """브랜드(옷)의 문자 스타일 → 인라인 CSS. 없으면 경고 + 빈 값."""
        cs = (self.skin.get("cstyles") or {}).get(name)
        if cs is None:
            self.warn(f"문자 스타일 없음 {name} — 옷 {self.skin.get('id') or '(없음)'}")
            return ""
        return char_css(cs, self)

    def styled(self, a):
        """글 원자에 옷의 단락 스타일(a.style)을 입힌다 — 스타일 값이 원자 값보다 우선. 없는 스타일은 경고 + 원자 값 그대로."""
        name = a.get("style")
        if not name or a.get("t") != "text":
            return a
        st = (self.skin.get("styles") or {}).get(name)
        if st is None:
            self.warn(f"단락 스타일 없음 {name} — 옷 {self.skin.get('id') or '(없음)'}")
            return a
        out = dict(a)
        out.update({k: v for k, v in st.items() if k in STYLE_KEYS and v is not None and v != ""})
        return out


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
def anchored_html(v, ctx):
    """글 안에 고정한 개체(인디자인 앵커드) — 부품을 그려 글줄 안에 끼운다."""
    anc = v.get("anc") or {}
    part = (ctx.parts or {}).get(anc.get("part")) if ctx else None
    if not part:
        if ctx:
            ctx.warn(f"글 안 개체의 부품 없음 {anc.get('part')}")
        return ""
    w = float(anc.get("w") or part.get("w") or 20)
    frag, ph = part_svg(ctx, part)
    ph = float(anc.get("h") or ph or 10)
    al = anc.get("align") or "inline"
    box = f"width:{w:.3f}px;height:{ph:.3f}px;display:inline-block;vertical-align:middle;"
    if al in ("left", "right"):
        box += f"float:{al};margin:{0.5}px {1.0}px;"
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {part.get("w", w):.3f} {ph:.3f}" '
           f'width="{w:.3f}" height="{ph:.3f}" style="display:block;width:{w:.3f}px;height:{ph:.3f}px">{frag}</svg>')
    return f'<span style="{box}">{svg}</span>'


def text_zoom(a, outer=1):
    """글상자 배치 배율(TEXT_ZOOM) — 크롬은 글자를 1만 px 보다 크게 못 그린다(300pt 가 283pt 로): 큰 글은 낮춘다.
    outer = 이 글을 감싼 글의 배율(글 끝에 붙인 부품 속 글) — 배율이 곱해지므로 그만큼 나눈다(안 나누면 1만 px 에 걸려 1/3 크기로, 단위 10 O·X)."""
    big = max([float(a.get("size") or 9)] + [float(r.get("size") or 0) for r in a.get("grep") or []]) * PT
    return max(1, min(TEXT_ZOOM, int(9000 / max(big * outer, 0.1))))


def tail_html(a, ctx):
    """글 끝에 붙이는 개체(인디자인 인라인 앵커) — atom.tail = {part, gap mm, drop mm, w?, h?}.
    부품을 글줄 안 inline-block 으로 끝에 붙인다: 글자처럼 흘러 자리가 모자라면 마지막 낱말과 함께 다음 줄로 간다.
    U+2060 으로 마지막 낱말과 붙인다(원본의 붙임 공백). drop = 기준선에서 개체 아래 끝까지 아래로(mm, 음수면 위로).
    → (html, 폭 mm) 또는 None"""
    t = a.get("tail") or {}
    part = (ctx.parts or {}).get(t.get("part")) if (ctx and t.get("part")) else None
    if not part:
        if t.get("part") and ctx:
            ctx.warn(f"글 끝에 붙일 부품 없음 {t.get('part')}")
        return None
    w = float(t.get("w") or part.get("w") or 10)
    z0 = getattr(ctx, "zoom_out", 1)
    ctx.zoom_out = z0 * text_zoom(a, z0)                              # 부품 속 글은 바깥 글의 배율 안에서 그려진다
    try:
        frag, ph = part_svg(ctx, part)
    finally:
        ctx.zoom_out = z0
    h = float(t.get("h") or part.get("h") or ph or 5)
    gap, drop = float(t.get("gap") or 0), float(t.get("drop") or 0)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {float(part.get("w") or w):.3f} {float(part.get("h") or h):.3f}" '
           f'width="{w:.3f}" height="{h:.3f}" style="display:block;overflow:visible;width:{w:.3f}px;height:{h:.3f}px">{frag}</svg>')   # 크기를 스타일로도 — 바깥 .p svg 규칙(쪽 크기)이 안 걸리게
    lead = " " if t.get("space") else "\u2060"                         # 띄어 붙이기 — 줄 끝이면 띄어쓰기에서 꺾여 개체만 다음 줄로(인디자인: 글 끝 공백 + 인라인 개체)
    return (f'{lead}<span style="display:inline-block;width:{w:.3f}px;height:{h:.3f}px;margin-left:{gap:.3f}px;'
            f'vertical-align:{-drop:.3f}px;letter-spacing:0;text-indent:0">{svg}</span>', w + gap)


def rich_html(v, ctx=None):
    """서식 조각 → HTML. 조각(run)의 b·i·u·sup·sub 는 태그로, color·font·size(토큰)는 인라인 style 로."""
    if v is None:
        return ""
    if isinstance(v, str):
        return esc(v).replace("\n", "<br/>")
    if isinstance(v, list):
        isp = lambda x: isinstance(x, dict) and "para" in x
        return "".join(rich_html(x, ctx) for k, x in enumerate(v)
                       if not (x == "\n" and ((k and isp(v[k - 1])) or (k + 1 < len(v) and isp(v[k + 1])))))
    if isinstance(v, dict):
        if "ps" in v:                                                      # 한 줄기 글의 자리 표시(content.story_value) — 문단 첫머리 · 붙는 자리(번호)
            if v.get("inline"):
                return f'<span data-psi="{esc(v["ps"])}">{esc(v.get("t", ""))}</span>'
            return f'<span data-ps="{esc(v["ps"])}"></span>' + esc(v.get("t", ""))
        if "para" in v:                                                    # 단락 묶음 — 테두리 상자·들여쓰기 (자리마다 서식)
            return f'<div style="{para_css(v["para"], ctx)}">{rich_html(v.get("c"), ctx)}</div>'
        if v.get("anc"):
            return (anchored_html(v, ctx) if ctx else "") + esc(v.get("t", ""))
        a = getattr(ctx, "cur_atom", None) if ctx else None
        if "side" in v:                                                    # 옆 메모(고정 개체)
            return side_html(v["side"], a, ctx)
        t = esc(v.get("t", "")).replace("\n", "<br/>")
        if v.get("u"):
            t = "<u>" + t + "</u>"
        if v.get("b"):
            t = "<b>" + t + "</b>"
        if v.get("i"):
            t = "<i>" + t + "</i>"
        if v.get("s"):
            t = "<s>" + t + "</s>"
        if v.get("sup"):
            t = "<sup>" + t + "</sup>"
        elif v.get("sub"):
            t = "<sub>" + t + "</sub>"
        st = ""
        if v.get("color"):
            st += f"color:{ctx.color(v['color']) if ctx else v['color']};"
        if v.get("font"):
            st += f"font-family:{esc(ctx.font(v['font']) if ctx else v['font'])};"
        if v.get("size"):
            st += f"font-size:{float(v['size']) * PT:.3f}px;"
        if v.get("bshift"):
            st += f"position:relative;top:{-float(v['bshift']) * PT:.3f}px;"
        if v.get("tracking"):
            st += f"letter-spacing:{float(v['tracking']) / 1000.0:.4f}em;"
        if v.get("case"):
            st += {"upper": "text-transform:uppercase;", "lower": "text-transform:lowercase;", "small": "font-variant:small-caps;"}[v["case"]]
        hs, vs = v.get("hscale"), v.get("vscale")
        if hs or vs:
            st += f"display:inline-block;transform:scale({float(hs or 100) / 100.0:.3f},{float(vs or 100) / 100.0:.3f});transform-origin:0 100%;"
        if v.get("cs"):                                                    # 문자 스타일 — 조각의 칸 값이 그 위에
            st = (ctx.cstyle_css(v["cs"]) if ctx else "") + st
        if st:
            t = f'<span style="{st}">' + t + "</span>"
        rbs = v.get("ruby")                                                # 윗주 — 하나 또는 [위, 아래] 둘
        for rb in (rbs if isinstance(rbs, list) else [rbs] if rbs else []):
            if isinstance(rb, dict) and rb.get("t"):
                t = ruby_html(t, rb, a, ctx)
        return t
    return esc(v)


_TAG = re.compile(r"(<[^>]+>)")
_UL_STYLE = {"wavy": "wavy", "dotted": "dotted", "dashed": "dashed", "double": "double"}     # 밑줄 모양 — 없으면 실선
CSTYLE_KEYS = ("font", "size", "color", "weight", "b", "i", "track", "bshift", "u", "u_style", "line", "line_off", "line_color",
               "bg", "bg_pad", "bg_r")


def char_css(cs, ctx=None):
    """문자 스타일(인디자인 문자 스타일) → 인라인 CSS. 서체·크기 pt·색·굵기·기울임·자간 ‰·기준선 pt·밑줄(모양·굵기·내림·색 mm)·바탕(여백·모서리 mm).
    바탕 = 인디자인에서 굵게 올린 밑줄로 까는 형광 — 여백은 바깥으로만 넓혀 글 자리는 그대로 둔다."""
    col = lambda v: ctx.color(v) if ctx else v
    st = ""
    if cs.get("font"):
        st += f"font-family:{ctx.font(cs['font']) if ctx else font_family(cs['font'])};"
    if cs.get("size"):
        st += f"font-size:{float(cs['size']) * PT:.3f}px;"
    if cs.get("color"):
        st += f"color:{col(cs['color'])};"
    if cs.get("weight"):
        st += f"font-weight:{int(cs['weight'])};"
    elif cs.get("b"):
        st += "font-weight:700;"
    if cs.get("i"):
        st += "font-style:italic;"
    if cs.get("track"):
        st += f"letter-spacing:{float(cs['track']) / 1000:.4f}em;"
    if cs.get("bshift"):
        st += f"position:relative;top:{-float(cs['bshift']) * PT:.3f}px;"
    if cs.get("u"):
        lw = float(cs.get("line") or 0.18)
        st += (f"text-decoration:underline;text-decoration-thickness:{lw:.3f}px;"
               f"text-decoration-color:{col(cs['line_color']) if cs.get('line_color') else 'currentColor'};"
               f"text-decoration-style:{_UL_STYLE.get(cs.get('u_style'), 'solid')};"
               f"text-underline-offset:{float(cs.get('line_off') or 0.4) - lw / 2:.3f}px;text-decoration-skip-ink:none;")
    if cs.get("bg"):
        pad, rad = float(cs.get("bg_pad") or 0), float(cs.get("bg_r") or 0)
        st += (f"background-color:{col(cs['bg'])};padding:{pad:.3f}px;margin:0 {-pad:.3f}px;border-radius:{rad:.3f}px;"
               "-webkit-box-decoration-break:clone;box-decoration-break:clone;")
    return st


def ruby_html(base, rb, a, ctx):
    """윗주(인디자인 문자 패널의 윗주) — 본문 글 위나 아래에 작은 글. 본문 첫머리 기준선에 폭·높이 0 인 점(inline-block)을 찍고
    거기서 잰다: 줄 간격·줄 나눔이 그대로고(단락 컴포저는 inline-block 을 글자 하나로 센다) 본문과 함께 움직인다.
    rb = {t, pos: above|below, cs?, off?, align?} — 없는 값은 글상자의 윗주 설정(a.ruby: cs · off_above · off_below · align)."""
    d = (a or {}).get("ruby") or {}
    pos = "below" if rb.get("pos") == "below" else "above"
    off = rb.get("off")
    if off is None:
        off = d.get("off_below" if pos == "below" else "off_above")
    off = float(off if off is not None else (0.6 if pos == "below" else 0.4))
    name = rb.get("cs") or d.get("cs")
    st = (ctx.cstyle_css(name) if (ctx and name) else "") or "font-size:60%;"
    just = "center" if (rb.get("align") or d.get("align")) == "center" else "start"
    v = f"top:{off:.3f}px" if pos == "below" else f"bottom:{off:.3f}px"
    plain = re.sub(r"<[^>]+>", "", base)
    return ('\u2060<span data-ruby="1" style="display:inline-block;width:0;height:0;position:relative;vertical-align:baseline">'
            f'<span style="position:absolute;left:0;{v};display:grid;white-space:nowrap;line-height:1;text-indent:0;letter-spacing:0;word-spacing:0">'
            f'<span style="grid-area:1/1;height:0;overflow:hidden;visibility:hidden">{plain}</span>'
            f'<span style="grid-area:1/1;justify-self:{just};{st}">{esc(rb.get("t", ""))}</span></span></span>\u2060{base}')


def side_html(t, a, ctx):
    """옆 메모(인디자인 고정 개체 — 글에 붙어 다니는 글상자, 위치 = 텍스트 프레임 기준) — 메모가 붙은 줄 높이의 옆 칸에.
    글상자의 옆 메모 설정(a.side: x · w mm 글상자 왼쪽 기준, off mm 그 줄 기준선→메모 위 끝, cs 문자 스타일, lead 행간 pt).
    폭 0 점(inline-block) 안에 놓아 본문 줄 나눔에 안 낀다."""
    d = (a or {}).get("side") or {}
    st = ctx.cstyle_css(d["cs"]) if (ctx and d.get("cs")) else ""
    lead = d.get("lead")
    lh = f"line-height:{float(lead) * PT:.3f}px;" if lead else ""
    return ('<span data-side="1" style="display:inline-block;width:0;height:0">'
            f'<span style="position:absolute;left:{float(d.get("x") or 0):.3f}px;width:{float(d.get("w") or 30):.3f}px;margin-top:{float(d.get("off") or 0):.3f}px;'
            f'text-indent:0;letter-spacing:0;word-spacing:0;white-space:normal;text-align:left;{lh}{st}">{esc(t)}</span></span>')


# 원고 표시 읽기 — 바깥 시스템이 글로 보내는 약속 표시를 윗주·옆 메모 조각으로(글상자 「원고 표시 읽기」를 켠 자리만).
# {본문|아래 윗주} · {본문^위 윗주} · {본문^위|아래} · [[옆 메모]]. 꾸밈(형광·색)은 GREP → 문자 스타일로.
_MARK = re.compile(r"\{([^{}|^]+)(?:\^([^{}|]*))?(?:\|([^{}]*))?\}|\[\[(.+?)\]\]")


def markup_runs(v):
    """약속 표시가 든 글 → 조각 목록. 표시가 없으면 그대로(글)."""
    if not isinstance(v, str) or not _MARK.search(v):
        return v
    out, k = [], 0
    for m in _MARK.finditer(v):
        if m.start() > k:
            out.append(v[k:m.start()])
        if m.group(4) is not None:
            out.append({"t": "", "side": m.group(4)})
        elif m.group(2) is None and m.group(3) is None:          # {글} — 윗주 없는 중괄호는 손대지 않는다(워크북 {밑줄 칠 곳} 같은 다른 약속)
            out.append(m.group(0))
        else:
            rbs = [{"t": t, "pos": p} for t, p in ((m.group(2), "above"), (m.group(3), "below")) if t]
            out.append({"t": m.group(1), "ruby": rbs[0] if len(rbs) == 1 else rbs})
        k = m.end()
    if k < len(v):
        out.append(v[k:])
    return out


def grep_html(html, rules, ctx=None):
    """GREP 스타일 — 글 HTML 의 글자 부분(태그 밖)에서 패턴에 맞는 곳을 굵게·기울임·밑줄·색으로 감싼다.
    태그를 걸쳐 맞는 곳은 건드리지 않는다. 패턴이 틀리면 그 규칙만 건너뛴다."""
    for r in rules or []:
        try:
            rx = re.compile(r.get("re") or "")
        except re.error:
            continue
        if not rx.pattern:
            continue
        col = (ctx.color(r["color"]) if ctx else r["color"]) if r.get("color") else None
        st = f"color:{col};" if col else ""
        if r.get("size"):
            st += f"font-size:{float(r['size']) * PT:.3f}px;"
        if r.get("bshift"):                                                # 기준선 이동 pt — 양수면 위로
            st += f"position:relative;top:{-float(r['bshift']) * PT:.3f}px;"
        if r.get("weight"):                                                # 굵기 100~900 — 굵게(700)보다 먼저
            st += f"font-weight:{int(r['weight'])};"
        if r.get("font"):                                                  # 서체 — 인디자인 GREP 스타일의 문자 스타일 서체(제목 「A1」 만 다른 서체 등)
            st += f"font-family:{ctx.font(r['font']) if ctx else font_family(r['font'])};"
        if r.get("track"):                                                 # 자간 ‰ em
            st += f"letter-spacing:{float(r['track']) / 1000:.4f}em;"
        if r.get("cs"):                                                    # 문자 스타일 — 인디자인 GREP 스타일이 입히는 그것. 규칙의 칸 값이 그 위에
            st = (ctx.cstyle_css(r["cs"]) if ctx else "") + st
        ul = r.get("u") and not r.get("blank") and not r.get("fit") and (r.get("line") or r.get("line_off") or r.get("line_color"))
        if ul:                                                             # 밑줄 굵기·내림·색 — 내림 = 기준선 → 밑줄 가운데 (mm)
            lw = float(r.get("line") or 0.18)
            lc = (ctx.color(r["line_color"]) if ctx else r["line_color"]) if r.get("line_color") else "currentColor"
            st += (f"text-decoration:underline;text-decoration-thickness:{lw:.3f}px;text-decoration-color:{lc};"
                   f"text-underline-offset:{float(r.get('line_off') or 0.4) - lw / 2:.3f}px;text-decoration-skip-ink:none;")
        tags = [k for k in ("u", "i", "b") if r.get(k) and not (k == "u" and ul) and not (k == "b" and r.get("weight"))]

        def wrap(m):
            if r.get("fit"):                                               # 글 폭 칸 — 맞은 글을 감추고 그 폭(크기·자간 포함) + 더할 폭만큼 밑줄 (인디자인: 정답 글 칠 없음 + 밑줄)
                lw = float(r.get("line") or 0.2)
                off = float(r.get("line_off") or 0.4)
                lc = (ctx.color(r["line_color"]) if ctx else r["line_color"]) if r.get("line_color") else (col or "currentColor")
                t = esc(m.group(1) if r.get("hide") and m.re.groups else m.group(0))
                fs = st.replace(f"color:{col};", "") if col else st
                # overflow:hidden 인 inline-block 은 아래 끝이 기준선에 선다 — 높이 0 이면 밑줄을 기준선에서 정확히 내린다. 글은 칸 폭만 잡고 안 보인다
                # 폭은 낱자 폭 합(합자·커닝 없이) — 원본 칸 71개가 그 식에 맞는다(「off」 의 ff 합자가 자간 한 칸을 먹던 것, 단위 11)
                return (f'<span style="display:inline-block;height:0;overflow:hidden;white-space:nowrap;font-feature-settings:\'liga\' 0,\'calt\' 0;font-kerning:none;{fs}padding-right:{float(r.get("blank") or 0):.3f}px;'
                        f'border-bottom:{lw:.3f}px solid {lc};vertical-align:{-(off + lw / 2):.3f}px"><span style="color:transparent">{t}</span></span>'
                        f'<span style="{fs}">⁠</span>')                    # 감춘 글 크기의 줄 높이는 남긴다(원본: 큰 정답 글이 든 줄은 기준선이 내려간다)
            if r.get("blank"):                                             # 칸으로 바꾸기 — 맞은 글(예: ____) 대신 정한 폭의 밑줄 칸
                lw = float(r.get("line") or 0.2)
                off = float(r.get("line_off") or 0.4)
                lc = (ctx.color(r["line_color"]) if ctx else r["line_color"]) if r.get("line_color") else (col or "currentColor")
                return (f'\u2060<span style="display:inline-block;width:{float(r["blank"]):.3f}px;height:0;'   # U+2060 — 앞 글자(빈칸 첫 글자)와 칸 사이에서 줄이 안 바뀌게
                        f'border-bottom:{lw:.3f}px solid {lc};vertical-align:{-(off + lw / 2):.3f}px"></span>')
            # 표시 감추기 — 원고의 약속 표시(예: {밑줄 칠 곳})는 지우고 묶음 1 의 글에만 서식
            t = esc(m.group(1) if r.get("hide") and m.re.groups else m.group(0))
            for k in tags:
                t = f"<{k}>{t}</{k}>"
            return f'<span style="{st}">{t}</span>' if st else t
        out, stack = [], []                                                # 윗주·옆 메모(data-ruby · data-side) 안 글은 건너뛴다 — 인디자인도 다른 글(고정 개체·윗주)
        for p in _TAG.split(html):
            if p.startswith("<"):
                if p.startswith("</"):
                    stack and stack.pop()
                elif not p.endswith("/>"):
                    stack.append(stack[-1] if stack else ("data-ruby=" in p or "data-side=" in p))
                    stack[-1] = stack[-1] or "data-ruby=" in p or "data-side=" in p
                out.append(p)
                continue
            raw = _unescape(p)
            if not raw or (stack and stack[-1]) or not rx.search(raw):
                out.append(p)
                continue
            k = 0
            for m in rx.finditer(raw):
                if m.end() == m.start():
                    continue
                out.append(esc(raw[k:m.start()]) + wrap(m))
                k = m.end()
            out.append(esc(raw[k:]))
        html = "".join(out)
    return html


def keep_spaces(html):
    """연속 공백을 지킨다 — HTML 은 공백 여럿을 하나로 줄이지만 인디자인은 친 만큼 띄운다.
    두 번째 공백부터 줄 안 바뀜 공백(&#160;)으로 — 첫 공백에서는 그대로 줄이 바뀔 수 있다.
    글(단락) 끝 공백도 지킨다 — 브라우저는 버리지만 인디자인은 남기고, 그 공백을 보고 끝 글자의 문맥 대체 글자를 고른다(영도체 숫자 「01 」).
    글(단락) 첫 공백도 — 인디자인은 친 자리만큼 띄우고 시작한다(배열 조각 「 on / was found」, 단위 12)."""
    html = "".join(p if p.startswith("<") else re.sub(r" {2,}", lambda m: " " + "&#160;" * (len(m.group(0)) - 1), p)
                   for p in _TAG.split(html))
    html = re.sub(r"(^|<br/>)((?:<[^/>][^>]*>)*) ", r"\1\2&#160;", html)
    return re.sub(r" ((?:&#160;)*)(?=(?:</[a-z]+>)*(?:<br/>|$))", r"&#160;\1", html)


def base_word_spacing(a, ctx):
    """글상자의 기본 낱말 간격(‰ em) — 「낱말 사이」."""
    return float(a.get("word_spacing") or 0)


# 글 언어의 글리프를 쓸 글자 — 공백(Zs)·문장부호(P*)·물결표. 서체와 상관없는 규칙
LOCL_CHARS = "".join(c for c in map(chr, range(0x10000)) if unicodedata.category(c) in ("Zs", "Pc", "Pd", "Ps", "Pe", "Pi", "Pf", "Po")) + "~"
_LOCL_RUN = re.compile(r"&#?\w+;|[" + re.escape(LOCL_CHARS.replace("&", "")) + "]+")    # & 는 글 HTML 에서 늘 &amp; 같은 이름으로 온다
_OT_LANG = {"ko": "KOR ", "ja": "JAN ", "zh": "ZHS ", "zh-hans": "ZHS ", "zh-hant": "ZHT "}   # 글 언어 → OpenType 언어 태그
_LOCL_HIT = {}


def text_lang(a):
    """글 언어(인디자인 문자 패널의 언어) — 없으면 한국어."""
    return str(a.get("lang") or "ko").strip() or "ko"


def locl_chars(family, lang):
    """서체가 그 언어용 글리프(GSUB locl)를 가진 공백·문장부호 — 이 글자만 감싼다. 감싸면 크롬이 글을 거기서 끊어 그리므로
    (커닝·문맥 대체 글자가 그 자리에서 끊긴다) 그 언어 글리프가 없는 글자·서체는 건드리지 않는다.
    서체 파일(fc-match — 브라우저와 같은 서체 목록)·언어 태그를 모르면 "" — 감싸지 않는다(sans-serif 처럼 브라우저가 고르는 서체).
    Noto Sans CJK KR + ko = 예전 고정 목록(GSUB latn/KOR 실측 — 단위 04·07) + " 와 줄 안 바뀜 공백(예전에도 &quot;·&#160; 로 감싸던 것)."""
    tag = _OT_LANG.get(lang.lower())
    key = (family, tag)
    if key in _LOCL_HIT:
        return _LOCL_HIT[key]
    out = ""
    try:
        import subprocess
        from fontTools.ttLib import TTFont
        for name in [n.strip().strip("'\"") for n in family.split(",")]:   # font_family 의 후보 이름들 — 설치된 첫 이름
            if not tag or not name or name in ("sans-serif", "serif", "monospace", "sans"):
                continue
            fam, ps, path, idx = subprocess.check_output(["fc-match", "-f", "%{family}|%{postscriptname}|%{file}|%{index}", name],
                                                         text=True, timeout=10).split("|")
            norm = lambda s: s.lower().replace(" ", "")
            if norm(name) in [norm(x) for x in fam.split(",") + ps.split(",")]:   # 다른 서체로 대신 잡힌 것은 모른다
                break
        else:
            raise LookupError(family)
        f = TTFont(path, fontNumber=int(idx or 0), lazy=True)
        g = f["GSUB"].table if "GSUB" in f else None
        gl = set()
        if g and g.ScriptList and g.FeatureList and g.LookupList:
            fi = {i for sr in g.ScriptList.ScriptRecord for ls in sr.Script.LangSysRecord if ls.LangSysTag == tag for i in ls.LangSys.FeatureIndex}
            recs = g.FeatureList.FeatureRecord
            for li in {k for i in fi if recs[i].FeatureTag == "locl" for k in recs[i].Feature.LookupListIndex}:
                lk = g.LookupList.Lookup[li]
                for st in lk.SubTable:
                    t = lk.LookupType
                    if t == 7:
                        t, st = st.ExtensionLookupType, st.ExtSubTable
                    gl.update(getattr(st, {1: "mapping", 3: "alternates", 4: "ligatures"}.get(t, "_"), None) or ())
        cmap = f.getBestCmap() or {}
        out = "".join(c for c in LOCL_CHARS if cmap.get(ord(c)) in gl)
    except Exception:
        out = ""
    _LOCL_HIT[key] = out
    return out


def locl_html(html, family, lang):
    """글 HTML 의 공백·문장부호를 글 언어로 감싼다 — 인디자인(언어 한국어)은 서체의 locl KOR 글리프를 놓는다:
    Noto CJK 면 공백 0.280em(라틴 0.224em), 따옴표·괄호·빗금·마침표는 조금 위로, 줄표 — 1em, 가운뎃점 좁게 (원본 글리프 번호 실측 — 단위 04·07).
    글은 lang=en 이라야 라틴 합자가 켜진다 — 이 글자들만 그 언어로 감싼다(합자에 끼는 글자가 아니다). 언어가 en 이면 그대로.
    (공백을 낱말 간격 +56‰ 로 더하던 보정은 크롬이 이미 0.280em 으로 그리는 한글 사이 공백에 두 번 들어갔다.)"""
    if not lang or lang.lower().startswith("en"):
        return html
    only = locl_chars(family, lang)
    if not only:
        return html                                                       # 서체에 그 언어 글리프가 없다
    run = re.compile("[" + re.escape(only) + "]+")
    span = lambda t: f'<span lang="{esc(lang)}">{t}</span>'

    def wrap(m):
        t = m.group(0)
        if t.startswith("&"):                                             # &#160; &quot; &amp; … — 글자 하나로 보고
            return span(t) if _unescape(t) in only else t
        return run.sub(lambda k: span(k.group(0)), t)
    return "".join(p if p.startswith("<") else _LOCL_RUN.sub(wrap, p) for p in _TAG.split(html))


def ko_glyphs(html, a, ctx):
    """글 언어(a.lang, 기본 한국어)의 공백·문장부호 글리프 — locl_html."""
    if not ctx:
        return html
    return locl_html(html, ctx.font(a.get("font")), text_lang(a))


JC_DEFAULT = (80, 133, 0, 0, 1, 20, 0)  # 낱말 최소·최대 % · 자간 최소·최대 ‰ · 줄이기 비용 · 줄 비용 · 끝 줄 자간 최소 ‰ (units_compose.js)
# 기본 = 인디자인 공장 기본 「균등 배치」(낱말 80·100·133%, 자간 0·0·0). 책마다 다른 범위는 글상자 jc(word_min·word_max·letter_min·letter_max)로.
# 비용식(줄이기 비용 1 · 줄 비용 20 · 늘림 제곱)은 공통 — 인디자인 원본 5권(d1·d2·화이트북·세서특필·분석)으로 확인(scratch justify-analysis/beval2.py).
# 이 출판사 책 5권은 모두 같은 범위: 낱말 100·133%, 자간 최소 약 −5‰, 자간 늘림 큼 → jc 「100,133,-8,250」.


def jc_spec(a):
    """양끝 정렬 설정(인디자인 「균등 배치」) → 컴포저 data-jc. 글상자 atom.jc 가 있으면 그 값, 없으면 기본.
    끝 줄도 자간 최소까지만 줄인다(인디자인처럼 — 끝 줄만 더 줄이던 것은 원본 끝 줄 41개가 모두 최소 안이라 뺐다, 단위 14b·14c 「studio.」)."""
    j = a.get("jc") or {}
    v = list(JC_DEFAULT)
    for i, k in ((0, "word_min"), (1, "word_max"), (2, "letter_min"), (3, "letter_max")):
        if j.get(k) is not None:
            v[i] = j[k]
    v[6] = v[2]
    return ",".join(f"{x:g}" for x in v)


def soft_breaks(x, justify=False, word_min=None):
    """줄 나눔(U+2028, Shift+Enter) — 문단은 그대로 두고 그 자리에서 줄만 꺾는다(인디자인 강제 줄바꿈).
    양끝맞춤이면 꺾인 앞줄도 양끝을 맞춘다(인디자인과 같다). 조각마다 열린 태그를 닫았다 다시 연다.
    word_min(‰ em, 음수) — 양끝을 맞추는 줄의 낱말 간격 최소(인디자인 양끝맞춤 「낱말 간격 최소」): 그만큼 좁혀 놓고 양끝까지 늘린다.
    브라우저는 공백을 늘리기만 하므로, 인디자인이 공백을 줄여 한 줄에 넣은 글이 넘치지 않게."""
    if " " not in (x or ""):
        return x
    segs, stack, cur = [], [], ""
    for tok in _TAG.split(x):
        if tok.startswith("<"):
            if tok.startswith("</"):
                if stack:
                    stack.pop()
            elif not tok.endswith("/>"):
                stack.append(tok)
            cur += tok
            continue
        for i, part in enumerate(tok.split(" ")):
            if i:
                cur += "".join("</" + re.match(r"<(\w+)", t).group(1) + ">" for t in reversed(stack))
                segs.append(cur)
                cur = "".join(stack)
            cur += part
    segs.append(cur)
    last = len(segs) - 1
    if last and not _unescape(_TAG.sub("", segs[-1])).strip():            # 끝에 친 줄 나눔 — 빈 줄은 안 그리고 마지막 줄도 양끝을 맞춘다
        tail = segs.pop()
        segs[-1] += tail
        last = len(segs)
    ws =f"word-spacing:{float(word_min) / 1000.0:.4f}em;" if justify and word_min else ""
    return "".join(f'<span style="display:block;{"text-align-last:justify;" + ws if justify and i < last else ""}{"text-indent:0;" if i else ""}">'
                   f'{s or "&#160;"}</span>' for i, s in enumerate(segs))


def rich_plain(v):
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "".join(rich_plain(x) for x in v)
    if isinstance(v, dict):
        if "para" in v:
            return rich_plain(v.get("c"))
        return str(v.get("t", ""))
    return str(v)


PARA_KEYS = ("box", "indent", "space")          # 단락 모양 — 자리마다 서식 중 단락에 입히는 것 (나머지 b·i·color·size·font 는 글 조각)


def para_css(pf, ctx=None):
    """단락 묶음 모양 → CSS. 글상자 안 px = mm (지면 좌표가 mm)."""
    st = "display:block;"
    if pf.get("box"):
        st += f"border:0.3px solid {ctx.color('$ink', '#231f20') if ctx else '#231f20'};padding:1.2px 1.8px;margin:1px 0;"
    if pf.get("indent"):
        st += f"padding-left:{float(pf['indent']):.2f}px;"
    if pf.get("space"):
        st += f"margin-top:{float(pf['space']):.2f}px;"
    return st


def fmt(v, ftype, ctx=None):
    """필드 값 → (html, plain). choices 는 ①~ 줄로."""
    if ftype == "choices" and isinstance(v, list):
        rows = [(CIRC[i] if i < len(CIRC) else str(i + 1)) + " " + rich_plain(x) for i, x in enumerate(v)]
        return "<br/>".join(esc(r) for r in rows), "\n".join(rows)
    if ftype == "bool":
        s = "✓" if v else ""
        return s, s
    return rich_html(v, ctx), rich_plain(v)


_KR = "가나다라마바사아자차카타파하"


def num_text(n, f):
    """번호 하나 → 글자. f = 1 · 01 · (1) · ① · 가 · A · a"""
    n = max(1, int(n))
    if f == "01":
        return f"{n:02d}"
    if f == "(1)":
        return f"({n})"
    if f == "①":
        return CIRC[n - 1] if n <= len(CIRC) else str(n)
    if f == "가":
        return _KR[(n - 1) % len(_KR)]
    if f in ("A", "a"):
        s = ""
        k = n
        while k > 0:
            k, r = divmod(k - 1, 26)
            s = chr((65 if f == "A" else 97) + r) + s
        return s
    return str(n)


def next_num(ctx, a, v):
    """이 글상자의 번호 — 원고가 준 번호가 있으면 그것, 없으면 앞 번호 다음. 목록은 num_list(없으면 자리 이름)로 나뉜다."""
    key = str(a.get("num_list") or a.get("bind") or "_")
    start = int(a.get("num_start") or 1)
    n = None
    if v not in (None, "", []):
        try:
            n = int(str(v).strip())
        except ValueError:
            n = None
    if n is None:
        n = ctx.nums.get(key, start - 1) + 1
    ctx.nums[key] = n
    return num_text(n, a.get("num") or "1")


def insets(a):
    """글상자 안쪽 여백 (위, 오른쪽, 아래, 왼쪽) mm."""
    v = a.get("inset")
    if v is None:
        return 0.0, 0.0, 0.0, 0.0
    if isinstance(v, (list, tuple)) and len(v) == 4:
        return tuple(float(x or 0) for x in v)
    return (float(v),) * 4


def auto_size(a):
    """자동 크기 조정(인디자인 텍스트 프레임 옵션) — "height" 높이만(기본: 글이 길면 아래로) · "both" 높이와 너비 · "off" 끔(false 도 끔)."""
    v = a.get("auto_size")
    return "off" if v is False or v == "off" else "both" if v == "both" else "height"


def frame_css(fr, ctx=None):
    """글상자 칠·획·모서리(인디자인 텍스트 프레임의 칠·획) — 상자(안쪽 여백을 가진 div)에 그린다. 획은 가장자리 가운데(인디자인 기본 획 정렬)."""
    if not fr:
        return ""
    col = (lambda c: ctx.color(c) if ctx else c)
    css = f"background:{col(fr['fill'])};" if fr.get("fill") else ""
    st = fr.get("stroke") or {}
    if st.get("color") and float(st.get("w") or 0) > 0:
        w = float(st["w"]) * PT
        css += f"outline:{w:.3f}px solid {col(st['color'])};outline-offset:{-w / 2:.3f}px;"
    r = fr.get("radius")
    if r:
        rs = r if isinstance(r, (list, tuple)) else [r] * 4            # [왼쪽 위, 오른쪽 위, 오른쪽 아래, 왼쪽 아래] — 네모(rect)의 radius 와 같은 차례
        css += "border-radius:" + " ".join(f"{float(v or 0):.3f}px" for v in rs) + ";"
    return css


ROMAN_EM = 0.47          # 로마자 한 글자 폭 어림 (기준 책 실측 0.455 — 본문 서체마다 조금 다르다)


def text_h(plain, w_mm, size_pt, leading_pt=None, a=None):
    """글이 차지할 높이(mm) 어림 — 한글·한자는 1em, 로마자는 ROMAN_EM. 자간·들여쓰기·여백·다단·단락 간격을 넣는다."""
    a = a or {}
    em = size_pt * PT
    lead = (leading_pt or size_pt * 1.45) * PT
    it, ir, ib, il = insets(a)
    cols = max(int(a.get("columns") or 1), 1)
    gutter = float(a.get("gutter") or 0) if cols > 1 else 0.0
    col_w = (w_mm - il - ir - gutter * (cols - 1)) / cols - float(a.get("indent") or 0) - float(a.get("indent_right") or 0)
    track = em * float(a.get("tracking") or 0) / 1000.0
    tsume = em * float(a.get("tsume") or 0) / 100.0 * 0.13             # 자간 축소 — 글자 양옆 빈 곳 어림 0.13em(Noto CJK 한글 0.10~0.16)
    lines = 0
    paras = (plain or "").replace(" ", "\n").split("\n")             # 줄 나눔도 줄 하나
    first = float(a.get("indent_first") or 0)                          # 첫 줄 들여쓰기(음수 = 내어쓰기 — 첫 줄이 그만큼 넓다, 단위 14c 한 줄 발문이 두 줄로 어림됐다)
    for para in paras:
        width = first + sum(em * (1.0 if ord(c) > 0x2E7F else 0.28 if c == " " else ROMAN_EM) + track - (tsume if c != " " else 0) for c in para)   # 공백 0.28em(Noto CJK 한국어 꼴)
        lines += max(1, int(math.ceil(width / max(col_w, 0.1))))
    gaps = (len(paras) - 1) * (float(a.get("space_before") or 0) + float(a.get("space_after") or 0))
    return math.ceil(lines / float(cols)) * lead + gaps + it + ib


def text_end(plain, w_mm, size_pt, a=None):
    """글이 끝나는 가로 자리(mm) — 마지막 줄의 끝. 문장 끝에 붙는 개체(인디자인 앵커 개체)가 쓴다.

    text_h 와 같은 어림(한글 1em · 로마자 ROMAN_EM)을 쓴다. 줄이 넘어가면 마지막 줄만 센다.
    """
    a = a or {}
    em = size_pt * PT
    it, ir, ib, il = insets(a)
    track = em * float(a.get("tracking") or 0) / 1000.0
    col_w = max(w_mm - il - ir - float(a.get("indent") or 0) - float(a.get("indent_right") or 0), 0.1)
    last = 0.0
    for para in (plain or "").split("\n"):
        run = 0.0
        for c in para:
            cw = em * (1.0 if ord(c) > 0x2E7F else ROMAN_EM) + track
            if run + cw > col_w:
                run = cw                      # 줄바꿈 — 새 줄에서 다시
            else:
                run += cw
        last = run
    return il + last


_BULLET = {"disc": "disc", "circle": "circle", "square": "square", "decimal": "decimal",
           "decimal-paren": "decimal", "upper-alpha": "upper-alpha", "lower-alpha": "lower-alpha"}


def _rule_css(r, side, ctx=None):
    """단락 경계선 — 인디자인 단락 경계선(위/아래)."""
    if not r:
        return ""
    w = float(r.get("w") or 0.5) * PT
    col = (ctx.color(r.get("color"), "#000000") if ctx else (r.get("color") or "#000000"))
    off = float(r.get("offset") or 0)
    css = f"border-{side}:{w:.3f}px solid {col};"
    css += f"padding-{side}:{off:.3f}px;" if off else ""
    return css


def _decor_css(a, ctx=None):
    """밑줄·취소선 꾸밈 — 굵기·색·내린 거리·모양(인디자인 밑줄 옵션)."""
    css = ""
    for k, line in (("underline", "underline"), ("strike", "line-through")):
        d = a.get(k)
        if not d:
            continue
        css += f"text-decoration-line:{line};"
        if d.get("w"):
            css += f"text-decoration-thickness:{float(d['w']) * PT:.3f}px;"
        if d.get("color"):
            css += f"text-decoration-color:{ctx.color(d['color']) if ctx else d['color']};"
        if d.get("style") and d["style"] != "solid":
            css += f"text-decoration-style:{d['style']};"
        if k == "underline" and d.get("offset"):
            css += f"text-underline-offset:{float(d['offset']) * PT:.3f}px;"
    if a.get("case"):
        css += {"upper": "text-transform:uppercase;", "lower": "text-transform:lowercase;", "small": "font-variant:small-caps;"}[a["case"]]
    return css


def _wrap_floats(ctx, a, h):
    """텍스트 감싸기 — 이 글상자와 겹치는 「감싸기」 원자만큼 자리를 비운다(인디자인 텍스트 감싸기, 사각형)."""
    out = ""
    for w in (getattr(ctx, "wrappers", None) or []):
        if w.get("id") is a:
            continue
        off = float(w.get("offset") or 0)
        x0, y0 = w["x"] - off, w["y"] - off
        x1, y1 = w["x"] + w["w"] + off, w["y"] + w["h"] + off
        tx0, ty0, tx1, ty1 = a["x"], a["y"], a["x"] + a["w"], a["y"] + h
        if x1 <= tx0 or x0 >= tx1 or y1 <= ty0 or y0 >= ty1:
            continue                                              # 안 겹친다
        side = w.get("side") or "auto"
        if side == "auto":
            side = "left" if (x0 - tx0) < (tx1 - x1) else "right"
        ww = (x1 - tx0) if side == "left" else (tx1 - x0)
        hh = y1 - ty0
        if ww <= 0 or hh <= 0:
            continue
        mt = max(0.0, y0 - ty0)
        out += (f'<div style="float:{side};width:{min(ww, a["w"]):.3f}px;height:{hh - mt:.3f}px;'
                f'margin-top:{mt:.3f}px;shape-outside:none"></div>')
    return out


def _tab_html(a, para, ctx=None):
    """탭 자리 — 인디자인 탭 패널. 탭으로 나뉜 조각을 자리마다 세우고, 리더로 빈 곳을 채운다."""
    stops = a.get("tabs") or []
    if not stops or "\t" not in para:
        return None
    segs = para.split("\t")
    stops = sorted(stops, key=lambda t: float(t.get("at") or 0))
    cols, prev = [], 0.0
    for i, seg in enumerate(segs):
        if i == 0:
            cols.append((0.0, "left", "", seg))
            continue
        st = stops[min(i - 1, len(stops) - 1)]
        at = float(st.get("at") or 0)
        cols.append((at, st.get("align") or "left", st.get("leader") or "", seg))
    out = ""
    for i, (at, al, leader, seg) in enumerate(cols):
        if i == 0:
            out += f'<span>{seg}</span>'
            continue
        prev_at = cols[i - 1][0]
        w = max(at - prev_at, 0.5)
        just = {"left": "flex-start", "center": "center", "right": "flex-end", "decimal": "flex-end"}[al]
        lead = ""
        if leader:
            lead = (f'<span style="flex:1;overflow:hidden;white-space:nowrap;opacity:.6">'
                    + (esc(leader) * 60) + "</span>")
        out += (f'<span style="display:inline-flex;min-width:{w:.3f}px;justify-content:{just};align-items:baseline">'
                f'{lead}<span>{seg}</span></span>')
    return out


_PS_RE = re.compile(r'<span data-ps="([^"]*)"></span>')
_PSI_RE = re.compile(r'<span data-psi="([^"]*)">')


def slot_style(a, slot, ctx=None):
    """한 줄기 글 안 그 자리의 단락 스타일 — 글상자의 slot_fmt[자리](style = 옷의 단락 스타일 이름을 밑에 깔고 그 위에 덮는 값)."""
    fm = dict(((a.get("slot_fmt") or {}).get(slot) or {}))
    st = {}
    if fm.get("style") and ctx is not None:
        base = (ctx.skin.get("styles") or {}).get(fm["style"])
        if base is None:
            ctx.warn(f"단락 스타일 없음 {fm['style']} — 자리 {slot}")
        st.update(base or {})
    st.update({k: v for k, v in fm.items() if k != "style" and v not in (None, "")})
    return st


def _font_css(st, ctx):
    """서체·크기·행간·색·굵기·기울임·자간 — 단락 스타일 값 중 글자에 드는 것"""
    css = ""
    if st.get("font"):
        css += f"font-family:{esc(ctx.font(st['font']) if ctx else st['font'])};"
    if st.get("size"):
        css += f"font-size:{float(st['size']) * PT:.3f}px;"
    if st.get("leading") or st.get("size"):
        css += f"line-height:{float(st.get('leading') or float(st['size']) * 1.45) * PT:.3f}px;"
    if st.get("color"):
        css += f"color:{ctx.color(st['color']) if ctx else st['color']};"
    if st.get("weight"):
        css += f"font-weight:{int(st['weight'])};"
    elif st.get("b"):
        css += "font-weight:700;"
    if st.get("i"):
        css += "font-style:italic;"
    if st.get("tracking"):
        css += f"letter-spacing:{float(st['tracking']) / 1000.0:.4f}em;font-feature-settings:'liga' 1,'calt' 1;"
    return css


def _slot_para(a, x, slot, slots, k, ps, ctx):
    """한 줄기 글의 문단 하나 — 그 자리의 단락 스타일(서체·간격·들여쓰기·바탕·「다음 문단과 함께」「쪼개지 않기」)을 입힌 <p>.
    같은 자리의 잇닿은 문단에 바탕(shade)이 있으면 한 상자로 잇는다(인디자인 단락 음영·테두리 병합 — 조건·보기 상자)."""
    st = slot_style(a, slot, ctx) if slot else {}
    css = "margin:0;" + re.sub(r"margin-(top|bottom):[^;]*;", "", ps) + _font_css(st, ctx)   # 문단 간격은 자리 스타일로만(아래)
    if st.get("align"):
        css += f"text-align:{st['align']};"
    pad = float(st.get("pad") or 0)
    shade = st.get("shade")
    grp = lambda j: ((lambda s: (s.get("shade"), s.get("border"), s.get("border_color")) if s.get("shade") else None)(slot_style(a, slots[j], ctx))
                     if 0 <= j < len(slots) and slots[j] else None)
    g0 = grp(k)                                                       # 같은 바탕(색·테두리)이 잇닿으면 한 상자 — [조건] 머리줄과 조건 글
    first = not (g0 and grp(k - 1) == g0) if shade else not (k and slots[k - 1] == slot)
    last = not (g0 and grp(k + 1) == g0) if shade else not (k + 1 < len(slots) and slots[k + 1] == slot)
    if st.get("indent") is not None or pad:
        css += f"padding-left:{float(st.get('indent') or 0) + pad:.3f}px;"
    if st.get("indent_right") is not None or pad:
        css += f"padding-right:{float(st.get('indent_right') or 0) + pad:.3f}px;"
    if st.get("indent_first") is not None:
        css += f"text-indent:{float(st['indent_first']):.3f}px;"
    # 문단 사이 = 앞 문단 「뒤 간격」 + 이 문단 「앞 간격」(인디자인은 더한다 — CSS 여백은 겹쳐 큰 것만 남아 위 끝에 margin-top 하나로)
    # 같은 자리끼리는 「같은 스타일 사이 간격」(space_same, 인디자인 「동일한 스타일 단락 사이 간격」)이 있으면 그것. 바탕 상자 안 문단 사이는 0
    prev = slot_style(a, slots[k - 1], ctx) if k and slots[k - 1] else {}
    if k and slots[k - 1] == slot and st.get("space_same") is not None:
        gap = float(st["space_same"])
    elif k and slots[k - 1] == slot and shade:
        gap = 0.0                                                     # 바탕 상자 안 같은 자리 문단 사이
    else:
        gap = float(st.get("space_before") or 0) + float(prev.get("space_after") or 0)
    if k and gap:
        css += f"margin-top:{gap:.3f}px;"
    if shade:
        css += f"background-color:{ctx.color(shade) if ctx else shade};"
        css += (f"padding-top:{float(st.get('pad_top', pad)) if first else 0:.3f}px;"
                f"padding-bottom:{float(st.get('pad_bottom', pad)) if last else 0:.3f}px;")
        if st.get("border"):
            b = f"{float(st['border']) * PT:.3f}px solid {ctx.color(st.get('border_color') or '$ink') if ctx else st.get('border_color') or '#231f20'}"
            css += f"border-left:{b};border-right:{b};" + (f"border-top:{b};" if first else "") + (f"border-bottom:{b};" if last else "")
    attrs = f' data-slot="{esc(slot)}"' if slot else ""
    if st.get("keep_next"):
        attrs += ' data-keep-next="1"'                                # 다음 문단과 함께 — 단·쪽 끝에 혼자 남지 않는다(units_compose.js thread)
    if st.get("keep_together"):
        attrs += ' data-keep="1"'                                     # 쪼개지 않기 — 문단 전체가 한 상자에
    if st.get("keep_first"):
        attrs += f' data-keep-first="{int(st["keep_first"])}"'       # 행 유지 — 상자 끝에 처음 N줄 이상
    if st.get("keep_last"):
        attrs += f' data-keep-last="{int(st["keep_last"])}"'         # 행 유지 — 다음 상자에 마지막 N줄 이상
    if st.get("tsume"):
        attrs += f' data-tsume="{float(st["tsume"]):g}"'
    just = (st.get("align") or a.get("align")) == "justify"
    if just and a.get("compose") is not False and "\u2028" not in x:          # 손으로 친 줄 나눔이 있으면 컴포저 대신 브라우저
        attrs += f' data-jc="{jc_spec(dict(a, jc=st["jc"]) if st.get("jc") else a)}"'
    x = _PSI_RE.sub(lambda m: f'<span data-psi="{m.group(1)}" style="{_inline_css(slot_style(a, m.group(1), ctx), ctx)}">', x)
    return f'<p style="{css}"{attrs}>{soft_breaks(x, just, None) or "&#160;"}</p>'


def _inline_css(st, ctx):
    """문단 첫머리에 붙는 자리(문항 번호) — 글자 모양 + 정한 폭(번호 칸)"""
    css = "text-indent:0;line-height:0;" + re.sub(r"line-height:[^;]*;", "", _font_css(st, ctx))   # 큰 번호가 줄 높이를 늘리지 않게(줄 높이는 문단 것)
    if st.get("inline_w"):
        css += f"display:inline-block;width:{float(st['inline_w']):.3f}px;"
    if st.get("drop"):                                                 # 기준선 내리기 mm — 원본 번호는 발문 기준선보다 0.55mm 아래
        css += f"position:relative;top:{float(st['drop']):.3f}px;"
    return css


def _text_html(a, html, h, ctx=None):
    """글상자 안 HTML — 단락(<p>)마다 들여쓰기·앞뒤 간격·경계선·음영·글머리, 상자엔 여백·세로 정렬·다단·첫 기준선·장평."""
    ps = ""
    if a.get("indent"):
        ps += f"padding-left:{float(a['indent']):.3f}px;"
    if a.get("indent_right"):
        ps += f"padding-right:{float(a['indent_right']):.3f}px;"
    if a.get("indent_first"):
        ps += f"text-indent:{float(a['indent_first']):.3f}px;"
    if a.get("space_before"):
        ps += f"margin-top:{float(a['space_before']):.3f}px;"
    if a.get("space_after"):
        ps += f"margin-bottom:{float(a['space_after']):.3f}px;"
    ps += _rule_css(a.get("rule_above"), "top", ctx) + _rule_css(a.get("rule_below"), "bottom", ctx)
    if a.get("shade"):
        ps += f"background-color:{ctx.color(a['shade']) if ctx else a['shade']};"
    bul = _BULLET.get(a.get("bullet") or "")
    if bul:
        ps += f"display:list-item;list-style-type:{bul};list-style-position:inside;"
    paras = (html or "").split("<br/>")
    just = a.get("align") == "justify"
    # 단락 컴포저(static/js/units_compose.js) — 양끝맞춤이고 손으로 친 줄 나눔·탭이 없는 단락은 크롬 안에서 문단 전체를 보고 줄 끝을 고른다
    jc = (lambda x: f' data-jc="{jc_spec(a)}"' if just and a.get("compose") is not False and " " not in x and not a.get("tab") else "")
    slots = [(_PS_RE.search(x).group(1) if _PS_RE.search(x) else None) for x in paras]   # 한 줄기 여러 자리 — 문단마다 그 자리(content.story_value)
    if any(slots):
        inner = "".join(_slot_para(a, x, s, slots, k, ps, ctx) for k, (x, s) in enumerate(zip(paras, slots)))
    else:
        last = len(paras) - 1                                           # 상자 끝 문단은 뒤 간격 없이(인디자인 — 마지막 단락 뒤 간격은 상자 높이에 안 든다)
        inner = "".join(f'<p style="margin:0;{ps}{"margin-bottom:0;" if k == last else ""}"{jc(x)}>{soft_breaks(_tab_html(a, x, ctx) or x, just, (a.get("word_min") + base_word_spacing(a, ctx)) if a.get("word_min") else None) or "&#160;"}</p>'
                        for k, x in enumerate(paras))
    dc = a.get("drop_cap")
    if dc and dc.get("lines", 0) >= 2 and paras and paras[0]:
        n = int(dc.get("chars") or 1)
        lines = int(dc["lines"])
        lead = (a.get("leading") or float(a.get("size") or 9) * 1.45) * PT
        head, rest = paras[0][:n], paras[0][n:]
        if head and "<" not in head:                              # 첫 글자에 태그가 걸치면 건드리지 않는다
            cap = (f'<span style="float:left;font-size:{lead * lines * 0.86:.3f}px;line-height:{lead * lines:.3f}px;'
                   f'margin-right:{lead * 0.12:.3f}px">{head}</span>')
            inner = (f'<p style="margin:0;{ps}">{cap}{rest or "&#160;"}</p>'
                     + "".join(f'<p style="margin:0;{ps}">{_tab_html(a, x, ctx) or x or "&#160;"}</p>' for x in paras[1:]))
    it, ir, ib, il = insets(a)
    it += float(a.get("first_baseline") or 0)                    # 첫 기준선 — 상자 위에서 더 내린다
    cols = int(a.get("columns") or 1)
    box = f"height:{h:.3f}px;box-sizing:border-box;padding:{it:.3f}px {ir:.3f}px {ib:.3f}px {il:.3f}px;"
    fr, mode = a.get("frame") or {}, auto_size(a)
    if fr and mode != "off" and not a.get("story"):                   # 글 잇기 상자는 높이를 지킨다(넘친 줄을 다음 상자로)
        box = box.replace(f"height:{h:.3f}px;", "")                   # 바탕이 있으면 브라우저가 실제로 그린 글 높이 + 여백만큼(인디자인 자동 크기 조정 — 줄기도 한다)
    if mode == "both":
        box += "width:fit-content;max-width:100%;"                     # 높이와 너비 — 한 줄 글은 글 폭 + 여백, 길면 상자 폭까지
    box += frame_css(fr, ctx)
    if a.get("valign") in ("center", "bottom"):
        box += "display:flex;flex-direction:column;justify-content:" + ("center" if a["valign"] == "center" else "flex-end") + ";"
    if cols > 1:
        cr = a.get("column_rule")
        rule = ""
        if cr and cr.get("w"):
            rule = f";column-rule:{float(cr['w']) * PT:.3f}px solid {(ctx.color(cr.get('color'), '#000000') if ctx else (cr.get('color') or '#000000'))}"
        inner = f'<div style="column-count:{cols};column-gap:{float(a.get("gutter") or 0):.3f}px;column-fill:balance{rule}">{inner}</div>'
    hs, vs = float(a.get("h_scale") or 100), float(a.get("v_scale") or 100)
    if hs != 100 or vs != 100:                                   # 장평 — 글자는 늘리고 상자 폭은 지킨다
        inner = (f'<div style="width:{float(a["w"]) * 100.0 / hs:.3f}px;transform:scale({hs / 100.0:.4f},{vs / 100.0:.4f});'
                 f'transform-origin:0 0">{inner}</div>')
    if ctx is not None:
        inner = _wrap_floats(ctx, a, h) + inner                   # 감싸기 — 비울 자리를 먼저
    return f'<div style="{box}">{inner}</div>'


# ── 부품 ────────────────────────────────────────────────────────────
def tint(hex_color, pct):
    """색조 — 인디자인 Tint. 흰색과 섞는다. 100 = 그대로, 0 = 흰색."""
    if pct is None:
        return hex_color
    t = max(0.0, min(float(pct), 100.0)) / 100.0
    c = (hex_color or "#000000").lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    try:
        r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return hex_color
    return "#%02x%02x%02x" % tuple(round(v * t + 255 * (1 - t)) for v in (r, g, b))


def _stroke(ctx, st):
    if not st:
        return 'stroke="none"'
    s = f'stroke="{tint(ctx.color(st.get("color"), "#000000"), st.get("tint"))}" stroke-width="{(st.get("w") or 0.5) * PT:.3f}"'
    if st.get("dash"):
        s += ' stroke-dasharray="' + " ".join(f"{d * PT:.3f}" for d in st["dash"]) + '"'
    if st.get("cap") in ("round", "square"):
        s += f' stroke-linecap="{st["cap"]}"'
    if st.get("join") in ("round", "bevel"):
        s += f' stroke-linejoin="{st["join"]}"'
    if st.get("miter"):
        s += f' stroke-miterlimit="{float(st["miter"]):.2f}"'
    return s


_ARROW_D = {                                        # 화살촉 — 0~10 상자 안, 오른쪽(10,5)이 촉 끝
    "arrow": "M0 0 L10 5 L0 10 z",
    "open": "M0 0 L10 5 L0 10",
    "circle": "M5 0 A5 5 0 1 1 5 10 A5 5 0 1 1 5 0 z",
    "square": "M0 0 L10 0 L10 10 L0 10 z",
    "bar": "M8 0 L10 0 L10 10 L8 10 z",
}


def _arrows(ctx, st):
    """선 시작·끝 화살촉 → (defs, 속성). 인디자인 시작/끝 모양."""
    if not st:
        return "", ""
    defs, attrs = "", ""
    col = tint(ctx.color(st.get("color"), "#000000"), st.get("tint"))
    for side in ("start", "end"):
        kind = st.get(side)
        if not kind or kind == "none" or kind not in _ARROW_D:
            continue
        mid = ctx.uid()
        fill = "none" if kind == "open" else col
        defs += (f'<marker id="{mid}" viewBox="0 0 10 10" refX="{0 if kind == "open" else 9}" refY="5" markerWidth="5" markerHeight="5" '
                 f'orient="auto-start-reverse"><path d="{_ARROW_D[kind]}" fill="{fill}" stroke="{col}" stroke-width="1.2"/></marker>')
        attrs += f' marker-{side}="url(#{mid})"'
    return defs, attrs


def _fx_defs(ctx, a):
    """효과(그림자·광선·페더·혼합 모드) → (defs, g 속성). 인디자인 효과 패널."""
    fx = a.get("fx") or {}
    if not fx:
        return "", ""
    attrs = ""
    if fx.get("blend") and fx["blend"] != "normal":
        attrs += f' style="mix-blend-mode:{fx["blend"]}"'
    steps, last = [], "SourceGraphic"
    sh, gl, fe = fx.get("shadow"), fx.get("glow"), fx.get("feather")
    if sh:
        col = ctx.color(sh.get("color"), "#000000")
        op = 1.0 if sh.get("opacity") is None else float(sh["opacity"])
        dx, dy, bl = float(sh.get("x") or 0), float(sh.get("y") or 0), float(sh.get("blur") or 0)
        if sh.get("inner"):
            steps.append(f'<feOffset in="SourceAlpha" dx="{dx:.3f}" dy="{dy:.3f}" result="so"/>'
                         f'<feGaussianBlur in="so" stdDeviation="{max(bl, 0.01) / 2:.3f}" result="sb"/>'
                         f'<feComposite in="SourceAlpha" in2="sb" operator="out" result="si"/>'
                         f'<feFlood flood-color="{col}" flood-opacity="{op:.3f}" result="sc"/>'
                         f'<feComposite in="sc" in2="si" operator="in" result="sin"/>'
                         f'<feComposite in="sin" in2="{last}" operator="over" result="fx1"/>')
            last = "fx1"
        else:
            steps.append(f'<feDropShadow in="{last}" dx="{dx:.3f}" dy="{dy:.3f}" stdDeviation="{max(bl, 0.01) / 2:.3f}" '
                         f'flood-color="{col}" flood-opacity="{op:.3f}" result="fx1"/>')
            last = "fx1"
    if gl:
        col = ctx.color(gl.get("color"), "#ffff00")
        op = 1.0 if gl.get("opacity") is None else float(gl["opacity"])
        bl = max(float(gl.get("blur") or 1), 0.01)
        if gl.get("inner"):
            steps.append(f'<feGaussianBlur in="SourceAlpha" stdDeviation="{bl / 2:.3f}" result="gb"/>'
                         f'<feComposite in="SourceAlpha" in2="gb" operator="out" result="gi"/>'
                         f'<feFlood flood-color="{col}" flood-opacity="{op:.3f}" result="gc"/>'
                         f'<feComposite in="gc" in2="gi" operator="in" result="gin"/>'
                         f'<feComposite in="gin" in2="{last}" operator="over" result="fx2"/>')
        else:
            steps.append(f'<feGaussianBlur in="SourceAlpha" stdDeviation="{bl / 2:.3f}" result="gb"/>'
                         f'<feFlood flood-color="{col}" flood-opacity="{op:.3f}" result="gc"/>'
                         f'<feComposite in="gc" in2="gb" operator="in" result="gg"/>'
                         f'<feMerge result="fx2"><feMergeNode in="gg"/><feMergeNode in="{last}"/></feMerge>')
        last = "fx2"
    bv, sa = fx.get("bevel"), fx.get("satin")
    if bv:
        size = max(float(bv.get("size") or 0.6), 0.05)
        depth = float(bv.get("depth") or 1)
        ang = float(bv.get("angle") or 120)
        steps.append(f'<feGaussianBlur in="SourceAlpha" stdDeviation="{size / 2:.3f}" result="bb"/>'
                     f'<feSpecularLighting in="bb" surfaceScale="{2 * depth:.2f}" specularConstant="{0.9 * depth:.2f}" specularExponent="18" lighting-color="#ffffff" result="bl">'
                     f'<feDistantLight azimuth="{ang:.1f}" elevation="55"/></feSpecularLighting>'
                     f'<feComposite in="bl" in2="SourceAlpha" operator="in" result="bl2"/>'
                     f'<feComposite in="{last}" in2="bl2" operator="arithmetic" k1="0" k2="1" k3="1" k4="0" result="fxb"/>')
        last = "fxb"
    if sa:
        col = ctx.color(sa.get("color"), "#000000")
        op = 0.5 if sa.get("opacity") is None else float(sa["opacity"])
        bl = max(float(sa.get("blur") or 1), 0.01)
        ds = float(sa.get("distance") or 1)
        steps.append(f'<feOffset in="SourceAlpha" dx="{ds:.3f}" dy="{ds:.3f}" result="s1"/>'
                     f'<feOffset in="SourceAlpha" dx="{-ds:.3f}" dy="{-ds:.3f}" result="s2"/>'
                     f'<feComposite in="s1" in2="s2" operator="xor" result="sx"/>'
                     f'<feGaussianBlur in="sx" stdDeviation="{bl / 2:.3f}" result="sxb"/>'
                     f'<feFlood flood-color="{col}" flood-opacity="{op:.3f}" result="sc2"/>'
                     f'<feComposite in="sc2" in2="sxb" operator="in" result="sat"/>'
                     f'<feComposite in="sat" in2="SourceAlpha" operator="in" result="sat2"/>'
                     f'<feComposite in="sat2" in2="{last}" operator="over" result="fxs"/>')
        last = "fxs"
    if fe:
        steps.append(f'<feGaussianBlur in="SourceAlpha" stdDeviation="{max(float(fe), 0.01) / 2:.3f}" result="fm"/>'
                     f'<feComposite in="{last}" in2="fm" operator="in" result="fx3"/>')
        last = "fx3"
    if not steps:
        return "", attrs
    fid = ctx.uid()
    defs = f'<filter id="{fid}" x="-40%" y="-40%" width="180%" height="180%">{"".join(steps)}</filter>'
    return defs, attrs + f' filter="url(#{fid})"'


def _aligned_shape(ctx, a, el, bbox):
    """획 정렬(안쪽·바깥쪽) — SVG 획은 늘 가운데라, 두 배 굵기로 그린 뒤 자르거나 가린다.
    el(attrs) = 그 모양을 그 속성으로 만드는 함수."""
    st = a.get("stroke") or {}
    fill, gdefs = _fill(ctx, a)
    align = st.get("align") or "center"
    w = float(st.get("w") or 0)
    adefs, aattrs = _arrows(ctx, st)
    gap = ""
    if st.get("dash") and st.get("gap_color"):                    # 간격 색 — 밑에 꽉 찬 선을 깔고 그 위에 점선
        gap = el(f'fill="none" {_stroke(ctx, dict(st, color=st["gap_color"], dash=None))}')
    if not w or align == "center" or not st.get("color"):
        return gdefs + adefs + gap + el(f'fill="{fill}" {_stroke(ctx, st)}{aattrs}')
    thick = _stroke(ctx, dict(st, w=w * 2))
    cid = ctx.uid()
    base = el(f'fill="{fill}" stroke="none"')
    if align == "inside":
        clip = f'<clipPath id="{cid}">{el("")}</clipPath>'
        return gdefs + adefs + clip + base + el(f'fill="none" {thick}{aattrs} clip-path="url(#{cid})"')
    x, y, bw, bh = bbox
    pad = w * PT * 2 + 1
    mask = (f'<mask id="{cid}"><rect x="{x - pad:.3f}" y="{y - pad:.3f}" width="{bw + 2 * pad:.3f}" height="{bh + 2 * pad:.3f}" fill="white"/>'
            f'{el("fill=" + chr(34) + "black" + chr(34))}</mask>')
    return gdefs + adefs + mask + el(f'fill="none" {thick}{aattrs} mask="url(#{cid})"') + base


def path_d(d, x, y, w, h):
    """0~1 비율 path → mm path. 숫자만 x·y 번갈아 상자에 맞춰 편다(M L C Q Z 만 쓴다)."""
    out, k = [], 0
    for tok in re.findall(r"[MLCQZmlcqz]|-?\d*\.?\d+(?:e-?\d+)?", d or ""):
        if tok.isalpha():
            out.append(tok.upper())
            k = 0
        else:
            v = float(tok)
            out.append(f"{x + v * w:.3f}" if k % 2 == 0 else f"{y + v * h:.3f}")
            k += 1
    return " ".join(out)


def _fill(ctx, a):
    """채움 → (fill 값, defs). gradient 가 있으면 <linearGradient>/<radialGradient> 를 만들어 url 로 쓴다."""
    g = a.get("gradient")
    if not g or not g.get("stops"):
        return (tint(ctx.color(a["fill"]), a.get("tint")) if a.get("fill") else "none"), ""
    gid = ctx.uid()
    stops = g["stops"]
    n = max(len(stops) - 1, 1)
    inner = "".join(f'<stop offset="{(st.get("at") if st.get("at") is not None else i / n) * 100:.1f}%" stop-color="{ctx.color(st.get("c"))}"/>'
                    for i, st in enumerate(stops))
    if g.get("type") == "radial":
        defs = f'<radialGradient id="{gid}">{inner}</radialGradient>'
    else:
        defs = f'<linearGradient id="{gid}" gradientTransform="rotate({float(g.get("angle") or 0):.1f} 0.5 0.5)">{inner}</linearGradient>'
    return f"url(#{gid})", f"<defs>{defs}</defs>"


def _corner(x0, y0, x1, y1, cx, cy, r, shape):
    """한 귀 — (x0,y0)에서 (x1,y1) 로 가는 모서리. cx,cy = 그 귀의 꼭짓점. 인디자인 모서리 옵션 5종."""
    k = 0.5523
    ix, iy = x0 + x1 - cx, y0 + y1 - cy                          # 안쪽으로 들어간 점
    if shape == "bevel":                                         # 경사 — 곧게 자른다
        return f"L {x1:.3f} {y1:.3f}"
    if shape == "inset":                                         # 빗면 — 네모로 파낸다
        return f"L {ix:.3f} {iy:.3f} L {x1:.3f} {y1:.3f}"
    if shape == "inverse":                                       # 역둥글게 — 안으로 파인 원호
        return f"A {r:.3f} {r:.3f} 0 0 0 {x1:.3f} {y1:.3f}"
    if shape == "fancy":                                         # 팬시 — 안으로 들어갔다 나오는 S
        return f"C {ix:.3f} {iy:.3f} {cx:.3f} {cy:.3f} {x1:.3f} {y1:.3f}"
    return f"C {x0 + (cx - x0) * k:.3f} {y0 + (cy - y0) * k:.3f} {x1 + (cx - x1) * k:.3f} {y1 + (cy - y1) * k:.3f} {x1:.3f} {y1:.3f}"


def _rrect_path(x, y, w, h, r, shape="round"):
    """모서리마다 다른 반지름의 네모 → path. r = [왼쪽 위, 오른쪽 위, 오른쪽 아래, 왼쪽 아래]. shape = 모서리 모양."""
    tl, tr, br, bl = [max(0.0, min(float(v or 0), w / 2, h / 2)) for v in r]
    d = [f"M {x + tl:.3f} {y:.3f}", f"L {x + w - tr:.3f} {y:.3f}"]
    if tr:
        d.append(_corner(x + w - tr, y, x + w, y + tr, x + w, y, tr, shape))
    d.append(f"L {x + w:.3f} {y + h - br:.3f}")
    if br:
        d.append(_corner(x + w, y + h - br, x + w - br, y + h, x + w, y + h, br, shape))
    d.append(f"L {x + bl:.3f} {y + h:.3f}")
    if bl:
        d.append(_corner(x + bl, y + h, x, y + h - bl, x, y + h, bl, shape))
    d.append(f"L {x:.3f} {y + tl:.3f}")
    if tl:
        d.append(_corner(x, y + tl, x + tl, y, x, y, tl, shape))
    return " ".join(d) + " Z"


def _origin(a, cx, cy, h=None):
    """변형 기준점 — 없으면 가운데, tl·tr·bl·br 이면 그 귀."""
    o = a.get("origin")
    if not o or o == "center" or a.get("t") == "line":
        return cx, cy
    x, y, w = a.get("x", 0), a.get("y", 0), a.get("w", 0)
    hh = h if h is not None else a.get("h", 0)
    dy = cy - (y + hh / 2)                                        # 자란 만큼 따라간다
    return (x if "l" in o else x + w), (y + dy if "t" in o else y + hh + dy)


def _wrap_atom(a, svg, cx, cy, ctx=None):
    """회전·뒤집기·기울이기·배율·불투명·효과 — 원자 공통. 축은 기준점(기본 가운데)."""
    cx, cy = _origin(a, cx, cy)
    rot = float(a.get("rotate") or 0)
    op = a.get("opacity")
    flip, skew, sc = a.get("flip"), a.get("skew"), a.get("scale")
    fdefs, fattrs = _fx_defs(ctx, a) if ctx is not None else ("", "")
    tr = []
    if rot:
        tr.append(f"rotate({rot:.2f} {cx:.3f} {cy:.3f})")
    if flip or skew or sc:
        tr.append(f"translate({cx:.3f} {cy:.3f})")
        if flip:
            tr.append(f"scale({-1 if 'h' in flip else 1} {-1 if 'v' in flip else 1})")
        if sc and len(sc) == 2:
            tr.append(f"scale({float(sc[0]) / 100.0:.4f} {float(sc[1]) / 100.0:.4f})")
        if skew and len(skew) == 2:
            if float(skew[0]):
                tr.append(f"skewX({float(skew[0]):.2f})")
            if float(skew[1]):
                tr.append(f"skewY({float(skew[1]):.2f})")
        tr.append(f"translate({-cx:.3f} {-cy:.3f})")
    attrs = ""
    if tr:
        attrs += f' transform="{" ".join(tr)}"'
    if op is not None and float(op) < 1:
        attrs += f' opacity="{float(op):.3f}"'
    attrs += fattrs
    if not attrs and not fdefs:
        return svg
    return f"{fdefs}<g{attrs}>{svg}</g>"


def story_seq(a):
    """글 잇기 순서 — story_seq(없거나 잘못되면 1)."""
    try:
        return max(1, int(a.get("story_seq") or 1))
    except (TypeError, ValueError):
        return 1


def story_cont(a):
    """글 잇기(인디자인 텍스트 스레드)의 이어지는 상자인가 — story 가 있고 story_seq 가 2 이상.
    story_seq 1(또는 없음) = 첫 상자: 글·자리(bind)·스타일을 가진다. 이어지는 상자는 빈 그릇이고 넘친 줄을 받는다."""
    return bool(a.get("story")) and story_seq(a) > 1


def _text_content(ctx, a, values, types):
    """글 원자의 (html, plain). bind → 값 → 없으면 sys → 없으면 견본 글 → 없으면 {bind} 회색.

    번호 매기기(num)가 켜져 있으면 원고가 번호를 안 줘도 앞 번호 다음으로 저절로 매긴다.
    """
    b = a.get("bind")
    ctx.cur_atom = a                                                       # 조각의 윗주·옆 메모가 이 글상자 설정을 쓴다
    if a.get("num"):
        t = next_num(ctx, a, values.get(b) if b else None)
        return esc(t), t
    if not b:
        return rich_html(a.get("text", ""), ctx), rich_plain(a.get("text", ""))
    v = values.get(b)
    if v is None and b.startswith("sys."):
        v = ctx.sys.get(b[4:])
    if v is None:
        if a.get("text"):
            return rich_html(a["text"], ctx), rich_plain(a["text"])
        hint = " + ".join(_slot_label(x) for x in b.split("+"))        # 견본 글도 원고도 없으면 자리 이름을 회색으로
        return f'<span style="color:#b0b0b0">‹{esc(hint)}›</span>', "‹" + hint + "›"
    if a.get("markup"):                                                    # 원고 표시 읽기 — {본문|윗주} · [[옆 메모]] → 조각
        v = markup_runs(v)
    return fmt(v, types.get(b, "text"), ctx)


_SLOT_NAMES = {"passage": "지문 본문", "pnum": "지문 번호", "prompt": "발문", "choices": "선지", "answer": "정답", "no": "번호",
               "sentence": "문장 한 줄", "sentences": "문장 여럿", "kr": "한글 해석", "title": "제목", "label": "라벨", "answers": "정답 묶음"}


def _slot_label(b):
    from core.units.formats import labels_all
    return labels_all().get(b) or _SLOT_NAMES.get(b) or b


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
    atoms = [ctx.styled(a) for a in atoms]                  # 단락 스타일(옷) 입히기
    ctx.wrappers = [{"id": a, "x": a.get("x", 0), "y": a.get("y", 0), "w": a.get("w", 0), "h": a.get("h", 0),
                     "offset": (a.get("wrap") or {}).get("offset"), "side": (a.get("wrap") or {}).get("side")}
                    for a in atoms if (a.get("wrap") or {}).get("mode") == "bbox"]      # 텍스트 감싸기 상자들
    # 1) 글이 자라는 만큼
    grown = []                                # (원자 번호, 원래 위, 원래 아래, 왼쪽, 오른쪽, 늘어난 양)
    content = {}
    plains = {}
    heights = {}
    for i, a in enumerate(atoms):
        if a.get("t") != "text":
            continue
        if a.get("story"):                                             # 글 잇기 — 상자 크기는 그대로, 넘친 줄은 다음 상자로(units_compose.js)
            heights[i] = a["h"]
            if story_cont(a):                                          # 이어지는 상자 = 빈 그릇. 글·자리·스타일은 첫 상자 것
                content[i] = '<span class="story-hint" style="color:#b0b0b0">‹앞 상자에서 이어짐›</span>'
                plains[i] = ""
                continue
        html, plain = _text_content(ctx, a, values, types)
        html = ko_glyphs(keep_spaces(grep_html(html, a.get("grep"), ctx)), a, ctx)
        tail = tail_html(a, ctx)                                       # 글 끝에 붙는 개체 — 글자처럼 흘러 줄 나눔·컴포저에 낀다
        if tail:
            html += tail[0]
            plain += "M" * int(tail[1] / max(a["size"] * PT * 0.6, 0.1) + 1)   # 높이 어림에 개체 폭만큼
        content[i] = html
        plains[i] = plain
        if a.get("story"):                                             # 첫 상자 — 자라지 않는다(넘침은 이어지는 상자가 받는다)
            continue
        need = text_h(plain, a["w"], a["size"], a.get("leading"), a)
        if auto_size(a) == "off":                        # 상자 높이를 지킨다(인디자인 자동 크기 조정 끔)
            heights[i] = a["h"]
            if need > a["h"] + 0.01:
                ctx.issue("warn", f"글이 상자보다 길다 — {plain[:20]}… (자동 크기 조정 꺼짐)")
            continue
        heights[i] = max(a["h"], need)
        if need > a["h"] + 0.01:
            grown.append((i, a["y"], a["y"] + a["h"] - below_tol(a), a["x"], a["x"] + a["w"], need - a["h"]))
    # 1b) 문장 끝에 붙는 개체 (인디자인 앵커 개체) — anchor.after 로 자리 이름을 가리킨다
    bybind = {a.get("bind"): (i, a) for i, a in enumerate(atoms) if a.get("bind")}
    pw_now = float(width or part.get("w") or 0)
    for a in atoms:
        an = a.get("anchor")
        if not an or not an.get("after"):
            continue
        tgt = bybind.get(an["after"])
        if not tgt:
            ctx.warn(f"붙일 자리 {an['after']} 가 부품 {part.get('id')} 에 없다")
            continue
        ti, t = tgt
        plain = plains.get(ti, "")
        x = float(t["x"]) + text_end(plain, float(t["w"]), float(t["size"]), t) + float(an.get("gap") or 2)
        if pw_now:
            x = min(x, pw_now - float(a.get("w") or 0))                    # 부품 밖으로는 안 나간다
        a["x"] = round(max(x, float(t["x"])), 3)
        lead = (t.get("leading") or t["size"] * 1.45) * PT
        need = text_h(plain, float(t["w"]), float(t["size"]), t.get("leading"), t)
        lines = max(1, int(round(need / lead))) if lead else 1
        a["y"] = round(float(a["y"]) + (lines - 1) * lead, 3)              # 마지막 줄 옆으로
    # 2) 밀기·늘리기 — 자란 글 아래에 있는 원자는 내려가고, 자란 글을 **가로세로로 감싸는** 상자는 늘어난다
    #    (옆에 나란히 선 원 O/X 는 세로 범위가 같아도 감싸는 게 아니다 — 실측: 원이 타원이 됐다)
    out = []
    bottom = part.get("h", 0)
    tag = any(a.get("t") == "text" and auto_size(a) != "off" and not a.get("story") for a in atoms)
    for i, a in enumerate(atoms):
        y, h = _bounds(a)
        dy = 0.0
        dh = 0.0
        for gi, gy0, gy1, gx0, gx1, d in grown:
            if gi == i:
                continue                                          # 자기 자신
            if y >= gy1 - 0.01:
                dy += d                                           # 아래 것 → 민다
            elif (a.get("t") in ("rect", "image") and not a.get("anchor")      # 문장 끝에 붙는 개체는 안 늘어난다
                  and y <= gy0 + 0.01 and y + h >= gy1 - 0.01
                  and a["x"] <= gx0 + 0.01 and a["x"] + a["w"] >= gx1 - 0.01):
                dh += d                                           # 감싸는 상자 → 늘인다
        if a.get("t") == "text":
            h = heights.get(i, h)
        svg = _atom_svg(ctx, a, dy, h + dh, content.get(i))
        if tag:                                                   # 설계 자리(y·높이) · 서버가 민 만큼 · 지금 높이 — 브라우저가 실제 글 높이로 바로잡을 때 쓴다
            x0 = min(a["x1"], a["x2"]) if a.get("t") == "line" else float(a.get("x") or 0)
            w0 = abs(a["x2"] - a["x1"]) if a.get("t") == "line" else float(a.get("w") or 0)
            y0, h0 = _bounds(a)
            svg = (f'<g data-ai="{i}" data-at="{a.get("t")}" data-ax="{x0:.3f}" data-aw="{w0:.3f}" data-ay="{y0:.3f}" '
                   f'data-ah0="{h0:.3f}" data-ady="{dy:.3f}" data-ah="{h + dh:.3f}">{svg}</g>')
        out.append(svg)
        bottom = max(bottom, y + dy + h + dh)
    return "".join(out), bottom


def _atom_svg(ctx, a, dy, h, html):
    a = with_ostyle(ctx, a)                                       # 개체 스타일 먼저
    lay = (ctx.layers or {}).get(a.get("layer") or "")
    if lay and (lay.get("hide") or (lay.get("nonprint") and ctx.print)):
        return ""                                                 # 숨긴 레이어 · 비인쇄 레이어
    if a.get("nonprint") and ctx.print:                           # 비인쇄 — 화면에만
        return ""
    svg = _atom_svg_raw(ctx, a, dy, h, html)
    if a.get("t") == "line":
        cx, cy = (a["x1"] + a["x2"]) / 2, (a["y1"] + a["y2"]) / 2 + dy
    else:
        cx, cy = a["x"] + a["w"] / 2, a["y"] + dy + h / 2
    return _wrap_atom(a, svg, cx, cy, ctx)


def _bleed_box(ctx, x, y, w, h):
    """인쇄 모드: 면 가장자리에 붙은 상자·그림을 도련만큼 밖으로 늘린다 (인디자인에서 도련선까지 끌어 놓는 일)."""
    p = ctx.print
    if not p or not p.get("bleed") or not ctx._at:
        return x, y, w, h
    b = float(p["bleed"])
    ox, oy, W, H = ctx._at
    ax, ay = ox + x, oy + y
    if ax <= 0.05:
        x -= b + ax
        w += b + ax
    if ax + w >= W - 0.05:
        w += b + (W - ax - w)
    if ay <= 0.05:
        y -= b + ay
        h += b + ay
    if ay + h >= H - 0.05:
        h += b + (H - ay - h)
    return x, y, w, h


def crop_marks(W, H, bleed, length=4.0, gap=0.5):
    """재단선 — 네 귀에 가로·세로 두 줄씩. 도련 밖(gap)에서 length 만큼. 먹 100%."""
    o = bleed + gap
    L = o + length
    s = 'stroke="#000000" stroke-width="0.09"'
    out = []
    for cx, sx in ((0.0, -1), (W, 1)):
        for cy, sy in ((0.0, -1), (H, 1)):
            out.append(f'<line x1="{cx + sx * o:.3f}" y1="{cy:.3f}" x2="{cx + sx * L:.3f}" y2="{cy:.3f}" {s}/>')
            out.append(f'<line x1="{cx:.3f}" y1="{cy + sy * o:.3f}" x2="{cx:.3f}" y2="{cy + sy * L:.3f}" {s}/>')
    return "".join(out)


def print_margin(ctx):
    """인쇄 모드에서 면 바깥 여유(mm) — 도련 + 재단선 자리."""
    p = ctx.print or {}
    return float(p.get("bleed") or 0) + (5.0 if p.get("marks") else 0.0)


def with_ostyle(ctx, a):
    """개체 스타일(인디자인) — 옷의 obj_styles[이름] 을 밑에 깔고 원자 값으로 덮는다."""
    nm = a.get("ostyle")
    if not nm:
        return a
    st = ((ctx.skin.get("obj_styles") or {}).get(nm)) or {}
    if not st:
        ctx.warn(f"개체 스타일 없음 {nm} — 옷 {ctx.skin.get('id') or '(없음)'}.obj_styles")
        return a
    out = dict(st)
    out.update(a)
    return out


def _atom_svg_raw(ctx, a, dy, h, html):
    t = a.get("t")
    if t == "text":
        lead = (a.get("leading") or a["size"] * 1.45) * PT
        if a.get("snap_baseline") and getattr(ctx, "grid", None):
            step = float((ctx.grid or {}).get("step") or 0)
            if step > 0:
                lead = math.ceil(lead / step - 0.01) * step           # 행간을 격자 간격의 배수로
                start = float((ctx.grid or {}).get("start") or 0)
                off = float(getattr(ctx, "_item_y", 0) or 0)                       # 요소가 면 안에 놓인 자리
                top = off + a["y"] + dy
                first = start + math.ceil((top - start) / step - 0.01) * step
                a = dict(a, first_baseline=max(0.0, first - top))     # 첫 줄을 격자 줄에 세운다
        style = (f"margin:0;font-family:{esc(ctx.font(a.get('font')))};font-size:{a['size'] * PT:.3f}px;"
                 f"line-height:{lead:.3f}px;color:{ctx.color(a.get('color'))};text-align:{a.get('align', 'left')};"
                 f"overflow-x:visible;overflow-y:clip;word-break:break-word;white-space:normal")   # 옆으로는 상자 밖까지(줄 끝 공백 밑줄이 단 끝을 넘는다 — 인디자인), 아래로는 자른다
        if a.get("tracking"):
            style += f";letter-spacing:{float(a['tracking']) / 1000.0:.4f}em"
            # 브라우저는 자간이 있으면 합자·문맥 대체 글자를 끈다 — 인디자인은 자간을 줘도 그대로 쓴다(fi 합자·영도체 이어지는 숫자)
            style += ";font-feature-settings:'liga' 1,'calt' 1"
        if a.get("kerning") == "none":
            style += ";font-kerning:none"
        if a.get("hyphenate"):
            style += ";hyphens:auto;-webkit-hyphens:auto"
        if a.get("justify_mode"):
            style += ";text-justify:" + ("inter-character" if a["justify_mode"] == "letter" else "inter-word")
        ws = base_word_spacing(a, ctx)
        if ws:
            style += f";word-spacing:{ws / 1000.0:.4f}em"
        dec = _decor_css(a, ctx)
        if dec:
            style += ";" + dec
        if a.get("baseline"):
            style += f";position:relative;top:{-float(a['baseline']) * PT:.3f}px"
        if a.get("weight"):                                                    # 굵기(100~900)가 굵게보다 먼저
            style += f";font-weight:{int(a['weight'])}"
        elif a.get("b"):
            style += ";font-weight:700"
        if a.get("i"):
            style += ";font-style:italic"
        if a.get("tab"):
            style = style.replace("white-space:normal", "white-space:pre-wrap") + f";tab-size:{float(a['tab']):.3f}px"
        # lang=en — 언어가 없으면 크롬이 한국어로 그려 Noto CJK 의 라틴 합자(ff·fi)가 꺼진다(인디자인은 쓴다). 글 언어(a.lang)의 공백·문장부호는 ko_glyphs 가 그 언어로 감쌌다
        # 글은 TEXT_ZOOM 배 해상도로 배치하고 그만큼 줄여 그린다 — 지면 1mm = CSS 1px 이라 브라우저가 줄 위치·글자 높이를
        # px 단위로 반올림하면 줄마다 최대 0.5mm 씩 어긋난다(행간 7.76mm 가 8·8·7·8mm 로). zoom 으로 반올림을 0.1mm 로.
        z = text_zoom(a, getattr(ctx, "zoom_out", 1))
        # 글 잇기 — 같은 이야기의 상자끼리 넘친 줄을 차례로 넘긴다(units_compose.js 의 thread)
        st = f' data-story="{esc(a["story"])}" data-seq="{story_seq(a)}"' if a.get("story") else ""
        if auto_size(a) != "off" and not a.get("story"):                       # 자동 크기 — 브라우저가 실제로 그린 글 높이로 상자를 다시 맞춘다(units_compose.js grow)
            st += f' data-grow="1" data-h0="{float(a["h"]):.3f}" data-hcur="{h:.3f}" data-tol="{below_tol(a):.3f}"'
            if a.get("bind") and not str(a["bind"]).startswith("sys."):          # 원고 자리 — 글 길이가 바뀌는 상자(틀 검사가 본다)
                st += f' data-slot="{esc(a["bind"])}"'
        if a.get("tsume"):                                                     # 자간 축소 — 글자 잉크 상자는 크롬 안에서 잰다(units_compose.js 의 tsume)
            st += f' data-tsume="{float(a["tsume"]):g}"'
        return (f'<g transform="translate({a["x"]} {a["y"] + dy:.3f}) scale({1 / z:g})">'
                f'<foreignObject x="0" y="0" width="{float(a["w"]) * z:.2f}" height="{h * z:.2f}" style="overflow:visible">'
                f'<div xmlns="http://www.w3.org/1999/xhtml" lang="en"{st} style="zoom:{z};{style}">{_text_html(a, html, h, ctx)}</div></foreignObject></g>')
    if t == "line":
        adefs, aattrs = _arrows(ctx, a.get("stroke"))
        return (adefs + f'<line x1="{a["x1"]}" y1="{a["y1"] + dy:.3f}" x2="{a["x2"]}" y2="{a["y2"] + dy:.3f}" '
                f'{_stroke(ctx, a.get("stroke"))}{aattrs}/>')
    if t == "path":
        rule = ' fill-rule="evenodd"' if a.get("evenodd") else ""
        d = path_d(a.get("d"), a["x"], a["y"] + dy, a["w"], h)
        join = "" if (a.get("stroke") or {}).get("join") else ' stroke-linejoin="round"'
        el = lambda at: f'<path d="{d}"{rule} {at}{join}/>'
        return _aligned_shape(ctx, a, el, (a["x"], a["y"] + dy, a["w"], h))
    if t == "rect":
        r = a.get("radius") or 0
        shape = a.get("corner") or "round"
        bx, by, bw, bh = _bleed_box(ctx, a["x"], a["y"] + dy, a["w"], h)
        if isinstance(r, (list, tuple)) or (r and shape != "round"):
            rr = r if isinstance(r, (list, tuple)) else [r, r, r, r]
            d = _rrect_path(bx, by, bw, bh, rr, shape)
            el = lambda at: f'<path d="{d}" {at}/>'
        else:
            el = lambda at: f'<rect x="{bx:.3f}" y="{by:.3f}" width="{bw:.3f}" height="{bh:.3f}" rx="{r}" {at}/>'
        return _aligned_shape(ctx, a, el, (bx, by, bw, bh))
    if t == "ellipse":
        cx0, cy0, rx0, ry0 = a["x"] + a["w"] / 2, a["y"] + dy + h / 2, a["w"] / 2, h / 2
        el = lambda at: f'<ellipse cx="{cx0:.3f}" cy="{cy0:.3f}" rx="{rx0:.3f}" ry="{ry0:.3f}" {at}/>'
        return _aligned_shape(ctx, a, el, (a["x"], a["y"] + dy, a["w"], h))
    if t == "image":
        src = a.get("src") or ""
        if ctx.image(src):
            href = ctx.image_href(src) or f"/api/units/image/{esc(ctx.skin.get('id', ''))}/{esc(src)}"
            im = a.get("img")
            if im:
                # 틀 안 그림의 자리 — 틀 밖은 클립으로 자른다 (인디자인 프레임 안 그래픽)
                cid = ctx.uid()
                return (f'<clipPath id="{cid}"><rect x="{a["x"]}" y="{a["y"] + dy:.3f}" width="{a["w"]}" height="{h:.3f}"/></clipPath>'
                        f'<image x="{a["x"] + float(im["x"]):.3f}" y="{a["y"] + dy + float(im["y"]):.3f}" width="{float(im["w"]):.3f}" height="{float(im["h"]):.3f}" '
                        f'href="{href}" preserveAspectRatio="none" clip-path="url(#{cid})"/>')
            if a.get("clip"):                                   # 클리핑 패스 — 이 모양으로 오려 낸다
                cid2 = ctx.uid()
                par2 = "xMidYMid slice" if a.get("fit") == "cover" else "xMidYMid meet"
                return (f'<clipPath id="{cid2}"><path d="{path_d(a["clip"], a["x"], a["y"] + dy, a["w"], h)}"/></clipPath>'
                        f'<image x="{a["x"]}" y="{a["y"] + dy:.3f}" width="{a["w"]}" height="{h:.3f}" '
                        f'href="{href}" preserveAspectRatio="{par2}" clip-path="url(#{cid2})"/>')
            par = "xMidYMid slice" if a.get("fit") == "cover" else "xMidYMid meet"
            bx, by, bw, bh = _bleed_box(ctx, a["x"], a["y"] + dy, a["w"], h)          # 인쇄: 가장자리 그림은 도련까지
            return (f'<image x="{bx:.3f}" y="{by:.3f}" width="{bw:.3f}" height="{bh:.3f}" '
                    f'href="{href}" preserveAspectRatio="{par}"/>')
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


def load_page_env(ctx, page):
    """지면의 레이어·기준선 격자를 ctx 에 싣는다 (원자를 그릴 때 본다)."""
    ctx.layers = {l.get("id"): l for l in (page.get("layers") or []) if l.get("id")}
    ctx.grid = page.get("baseline_grid") or None
    return ctx


def _join_paras(a, b):
    """두 값을 단락으로 잇는다 (문자열 / 서식 조각 목록)."""
    if isinstance(a, str) and isinstance(b, str):
        return a + "\n" + b
    return (a if isinstance(a, list) else [a]) + ["\n"] + (b if isinstance(b, list) else [b])


def _atom_slot(it):
    """원고 자리가 붙은 낱개 글상자인가 (책이 채우는 sys.* 는 아니다). 글 잇기의 이어지는 상자는 자리가 아니다(이야기 하나 = 자리 하나)."""
    a = it.get("atom") or {}
    b = a.get("bind")
    return a.get("t") == "text" and bool(b) and not str(b).startswith("sys.") and not it.get("hide") and not story_cont(a)


def _fill_by_slots(pg, sample_set, ctx, canvas, pending, filled, sid):
    """자리 이름으로 채우기 — 원고 자리 글상자(낱개 원자)와, 유형으로 못 짝지은 블록(요소)의 자리.

    인디자인 데이터 병합처럼: 같은 자리가 여럿이면 읽는 순서(위→아래, 왼→오른)로 n번째 자리에 원고의 n번째 값.
    그 자리가 하나뿐이면 원고의 그 자리 값이 전부 단락으로 흘러 들어간다(스토리). 자리 이름 a+b 는 원고에 나온 순서대로 섞는다.
    같은 요소(블록)를 다섯 번 놓으면 O/X 한 줄씩 — 요소 안의 자리들이 같은 n번째 값을 받는다.
    """
    blocks = sample_set.get("blocks") or []
    vals, src = {}, {}
    for bi, b in enumerate(blocks):
        for f, v in (b.get("fields") or {}).items():
            vals.setdefault(f, []).append(v)
            src.setdefault(f, []).append((bi, b.get("block")))
    labels = sample_set.get("labels") or {}

    def slot_keys(it):
        if _atom_slot(it):
            return [it["atom"]["bind"]]
        blk = (ctx.blocks.get(it.get("block")) if ctx else None) or {}
        return [f for f in (blk.get("fields") or {}) if not f.startswith("sys.")]

    # 요소(블록)를 자리 이름으로 채우는 것은 **역할 원고**(원고 형식이 읽은 원고 — 세트의 블록이 단락 역할, labels 가 붙어 온다)일 때만.
    # 라이브러리 블록 원고는 유형 이름으로만 짝짓는다 — 자리 이름이 같아도 다른 유형(어법 O/X ↔ 본문 O/X)으로 새지 않게
    role_set = bool(sample_set.get("labels"))                   # 자리 이름 원고 — 원고 형식(core/units/formats)이 labels 를 붙인다
    entries = []
    for it in [x for x in pg.get("items") or [] if _atom_slot(x)] + pending:
        keys = slot_keys(it)
        if it.get("block") and not (role_set and any(k in vals or ("+" in k and any(w in vals for w in k.split("+"))) for k in keys)):
            if ctx and not canvas:                               # 못 짝지은 블록 — 비워 두고 알린다
                bid = it["block"]
                blk = ctx.blocks.get(bid) or {}
                it["fields"] = {}
                it["_empty"] = True
                n = sum(1 for b in blocks if b.get("block") == bid)
                if n:
                    ctx.issue("warn", f"원고 {sid}: 지면 {pg.get('id')} 의 {blk.get('name') or bid} 자리 {sum(1 for x in pg['items'] if x.get('block') == bid)}개 중 {n}개만 찼다 — 나머지는 빈 채")
                else:
                    ctx.issue("error", f"원고 {sid}: 지면 {pg.get('id')} 의 {blk.get('name') or bid} 자리에 넣을 원고가 없다 — 비워 둔다")
            continue
        entries.append((it, keys))
    if not entries:
        return
    count = {}
    for _, keys in entries:
        for k in keys:
            count[k] = count.get(k, 0) + 1
    used, taken = set(), {}

    set_fmt = sample_set.get("fmt") or {}

    def styled(v, f, it):
        """자리마다 서식(인디자인 단락 스타일 ↔ 원고 역할) — 글상자의 slot_fmt 가 원고 형식의 기본(fmt)보다 우선."""
        fmt = dict(set_fmt.get(f) or {})
        fmt.update(((it.get("atom") or {}).get("slot_fmt") or {}).get(f) or {})
        fmt = {k: x for k, x in fmt.items() if x not in (None, "", False, 0) and k not in PARA_KEYS}
        if not fmt or v in (None, ""):
            return v
        return [dict(fmt, t=x) if isinstance(x, str) else dict(fmt, **x) for x in (v if isinstance(v, list) else [v])]

    def para_of(f, it):
        pf = {k: x for k, x in (set_fmt.get(f) or {}).items() if k in PARA_KEYS}
        pf.update({k: x for k, x in ((((it or {}).get("atom") or {}).get("slot_fmt") or {}).get(f) or {}).items() if k in PARA_KEYS})
        return {k: x for k, x in pf.items() if x not in (None, "", False, 0)}

    def with_no(v, bf):
        no = bf.get("no")
        return v if no in (None, "") else [f"{no} "] + (v if isinstance(v, list) else [v])

    def flow(pairs, number, it=None, fields=None):
        """(블록 번호, 값) 목록 → 한 스토리. number 면 번호를 글 앞에. fields 를 주면 값마다 그 자리의 서식,
        단락 모양(상자·들여쓰기)이 있는 자리는 잇닿은 같은 자리 단락을 한 묶음으로 — 지문 여러 단락이 상자 하나에."""
        joined, group, gf = None, None, None

        def flush():
            nonlocal joined, group
            if group is not None:
                piece = [{"para": para_of(gf, it), "c": group if isinstance(group, list) else [group]}]
                joined = piece if joined is None else _join_paras(joined, piece)
                group = None
        for k, (bi, v) in enumerate(pairs):
            f = fields[k] if fields is not None else None
            if f is not None:
                v = styled(v, f, it)
            v = with_no(v, blocks[bi].get("fields") or {}) if number else v
            used.add((bi, blocks[bi].get("block")))
            if f is not None and para_of(f, it):
                if group is not None and gf == f:
                    group = _join_paras(group, v)
                else:
                    flush()
                    group, gf = v, f
                continue
            flush()
            joined = v if joined is None else _join_paras(joined, v)
        flush()
        return joined

    for it, keys in sorted(entries, key=lambda e: (round(float(e[0].get("y") or 0), 1), float(e[0].get("x") or 0))):
        out = {}
        # 번호를 글 앞에 붙일까 — 흘려 넣는 자리는 번호 칸과 줄이 안 맞으니, 이 자리 곁에 번호 칸이 따로 없거나(면에 번호 자리 없음) 같은 요소 안이면 글 앞에
        number = "no" not in count or "no" in keys
        for f in sorted(keys, key=lambda x: x == "no"):          # 번호 자리는 맨 나중 — 흘려 넣었으면 비운다
            k = taken.get(f, 0)
            taken[f] = k + 1
            if "+" in f:                                         # 자리 여럿 — 원고에 나온 순서대로 섞는다
                want = [x for x in f.split("+") if x]
                hits = [(bi, (b.get("fields") or {})[w], w) for bi, b in enumerate(blocks) for w in want
                        if (b.get("fields") or {}).get(w) not in (None, "")]
                out[f] = flow([(bi, v) for bi, v, _ in hits], number, it, [w for *_, w in hits]) if hits else ""
            elif f != "no" and count[f] == 1 and len(vals.get(f) or []) > 1:
                out[f] = flow([(bi, v) for (bi, _), v in zip(src[f], vals[f])], number, it, [f] * len(vals[f]))   # 자리 하나 — 전부 흘려 넣는다
                taken[f] = len(vals[f])
                if "no" in keys:
                    out["no"] = ""
                    taken["no"] = len(vals.get("no") or [])
            elif f == "no" and "no" in out:
                continue
            elif k < len(vals.get(f) or []):
                out[f] = styled(vals[f][k], f, it)
                used.add(src[f][k])
            elif ctx and not canvas:
                out[f] = ""
                ctx.issue("warn" if vals.get(f) else "error",
                          f"원고 {sid}: 지면 {pg.get('id')} 의 「{labels.get(f, f)}」 자리 {k + 1}번째에 넣을 원고가 없다 — 비워 둔다")
        it["fields"] = out
    for bi, bid in used:
        filled[bid] = filled.get(bid, 0) + 1
    if ctx and not canvas:
        for f, n in taken.items():
            if "+" not in f and len(vals.get(f) or []) > n:
                ctx.issue("error", f"원고 {sid}: 「{labels.get(f, f)}」 {len(vals[f])}개 중 {len(vals[f]) - n}개는 지면 {pg.get('id')} 에 자리가 없어 안 실린다")


def _fill_items(pg, sample_set, ctx=None, canvas=False):
    """세트의 값을 지면의 블록 자리(items)에 순서대로 끼운다 — 어법 O/X 줄 셋이면 세트의 1·2·3번 문장.

    세트에 없는 자리는 **비워 둔다**(_empty — 견본 글이 책에 들어가면 안 된다) + 검수 error.
    자리보다 원고가 많으면(줄 셋인데 자리 둘) 남는 원고는 안 실린다 + 검수 error.
    """
    def kind_of(bid):
        """그 블록의 원고 유형 이름 — kind 가 있으면 그것, 없으면 블록 이름(없으면 id)."""
        b = (ctx.blocks.get(bid) if ctx else None) or {}
        return str(b.get("kind") or b.get("name") or bid or "").strip().lower()

    queue, by_kind, origin = {}, {}, {}
    for b in sample_set.get("blocks") or []:
        bid = b.get("block")
        fs = b.get("fields") or {}
        origin[id(fs)] = bid                                     # 채운 원고가 원래 어느 블록 것인지 — 검수 셈은 원고 쪽으로
        queue.setdefault(bid, []).append(fs)
        by_kind.setdefault(kind_of(bid), []).append(fs)          # id 가 달라도 유형 이름이 같으면 붙는다
    total = {k: len(v) for k, v in queue.items()}
    filled = {}
    pending = []
    sid = sample_set.get("id", "")
    for it in pg.get("items") or []:
        bid = it.get("block")
        if not bid or it.get("hide") or it.get("fields"):
            continue
        blk = (ctx.blocks.get(bid) if ctx else None) or {}
        if ctx and not canvas and blk.get("source") != "content":
            continue
        q = queue.get(bid)
        if not q:
            q = by_kind.get(kind_of(bid))                        # 블록을 새로 만들었어도 유형 이름이 같으면 꽂힌다
        if not q and ctx:                                        # 블록이 「받는 항목」에 적어 둔 이름들로
            blk2 = ctx.blocks.get(bid) or {}
            for acc in (blk2.get("accepts") or []):
                key = str(acc).strip()
                q = queue.get(key) or by_kind.get(key.lower())
                if q:
                    break
        if not q and ctx and ctx.map:                            # 그래도 없으면 문서의 원고 연결표를 본다
            for src, dst in (ctx.map or {}).items():
                if dst != bid:
                    continue
                q = queue.get(src) or by_kind.get(str(src).strip().lower())
                if q:
                    break
        if not q:                                                # 자리가 여럿인 요소 — 원고의 자리들을 모아 한 벌로
            want = [k for k in (blk.get("fields") or {})]
            if len(want) > 1 and all(queue.get(k) or by_kind.get(k) for k in want):
                merged = {}
                for k in want:
                    qq = queue.get(k) or by_kind.get(k)
                    fs = qq.pop(0) if (ctx and not canvas) or len(qq) > 1 else qq[0]
                    merged.update({k2: v2 for k2, v2 in (fs or {}).items()})
                it["fields"] = merged
                filled[bid] = filled.get(bid, 0) + 1
                continue
        if q:
            if ctx and not canvas:
                it["fields"] = q.pop(0)                      # 책: 원고를 하나씩 소진 — 같은 줄이 두 번 실리지 않게
            else:
                it["fields"] = q.pop(0) if len(q) > 1 else q[0]
            src = origin.get(id(it["fields"]), bid)
            filled[src] = filled.get(src, 0) + 1
            if ctx and not canvas:
                for f, d in (blk.get("fields") or {}).items():
                    if (d or {}).get("required") and (it["fields"].get(f) in (None, "", [])):
                        ctx.issue("error", f"원고 {sid}: {blk.get('name') or bid} 의 필수 자리 {f} 가 비었다")
        else:
            pending.append(it)                                  # 유형으로 못 짝지은 블록 — 아래에서 자리 이름으로 채워 본다
    _fill_by_slots(pg, sample_set, ctx, canvas, pending, filled, sid)
    optional = {b.get("block") for b in sample_set.get("blocks") or [] if b.get("optional")}      # 받을 자리가 없어도 되는 원고(머리 정보)
    if ctx and not canvas:
        for bid, n in total.items():
            if bid in optional:
                continue
            k = filled.get(bid, 0)
            blk = ctx.blocks.get(bid) or {}
            if k == 0:
                ctx.issue("error", f"원고 {sid}: {blk.get('name') or bid} {n}개가 지면 {pg.get('id')} 에 자리가 없어 안 실린다")
            elif n > k:
                ctx.issue("error", f"원고 {sid}: {blk.get('name') or bid} {n}개 중 {n - k}개는 지면 {pg.get('id')} 에 자리가 없어 안 실린다")


def _stack_pages(ctx, page, sets, spec):
    """쌓기 자리(item.flow) — 세트마다(세트 안 같은 블록마다) 자리 사본을 아래로 쌓는다. 한계선을 넘으면 새 면(고정·장식 요소는 그대로)."""
    H = float(spec["h"])
    limit = H - float((page.get("margins") or {}).get("bottom") or 20)
    items = page.get("items") or []
    flows = [i for i, it in enumerate(items) if it.get("flow") and not it.get("hide")]
    static = [json.loads(json.dumps(it)) for i, it in enumerate(items) if i not in flows and not it.get("hide")
              and not ((ctx.blocks.get(it.get("block")) or {}).get("source") == "content" and it.get("block"))]
    pages = []
    cur = None
    for fi in flows:
        base = items[fi]
        gap = float(base.get("gap") or 2)
        y = float(base["y"])
        for s in sets:
            for b in (s.get("blocks") or []):
                if b.get("block") != base.get("block"):
                    continue
                it = json.loads(json.dumps(base))
                it["fields"] = b.get("fields") or {}
                it.pop("flow", None)
                _f, _p, _w, h = _item_frag(ctx, it)
                h *= float(it.get("s") or 1)
                if cur is not None and y + h > limit + 0.01 and any(x.get("_stacked") for x in cur["items"]):
                    pages.append(cur)
                    cur = None
                if cur is None:
                    cur = json.loads(json.dumps(page))
                    cur["items"] = [json.loads(json.dumps(x)) for x in static]
                    cur["_canvas"] = True
                    cur["_noguides"] = True
                    cur["_flowed"] = True
                    y = float(base["y"])
                it["y"] = round(y, 3)
                it["_stacked"] = True
                cur["items"].append(it)
                y += h + gap
    if cur is not None:
        pages.append(cur)
    if not pages:
        pg = json.loads(json.dumps(page))
        pg["items"] = static
        pg["_canvas"] = True
        pg["_noguides"] = True
        pages.append(pg)
    return pages


def page_svgs(ctx, page, sets, spec, pno=1, label=""):
    """지면 하나에 세트들을 흘린다 → [{svg, label, page_no}]. 넘치면 같은 지면을 새 면으로.

    캔버스에서 만든 지면(콘텐츠 블록 자리 = items)은 **슬롯 모드**: 세트마다 한 면, 자리에 값을 끼운다.
    글이 길어 자리가 자라면 아래 요소를 민다(_page_wrap). 칸(zones) 흐름은 옛 지면용.
    """
    load_page_env(ctx, page)                                   # 레이어·기준선 격자
    W, H = float(spec["w"]), float(spec["h"])
    slots = [it for it in page.get("items") or [] if it.get("block") and (ctx.blocks.get(it["block"]) or {}).get("source") == "content"]
    slots += [it for it in page.get("items") or [] if _atom_slot(it)]              # 원고 자리 글상자도 자리다
    if not slots and not page.get("zones"):
        sets = []                                              # 원고 자리가 없는 면(표지·간지) — 원고를 안 받는다
    if slots and any(it.get("flow") for it in slots) and sets and not page.get("_canvas"):
        out = []
        for k, fp in enumerate(_stack_pages(ctx, page, sets, spec)):        # 쌓기 자리 — 세트를 아래로 쌓고 차면 다음 면
            mirror = bool(fp.get("mirror")) and pno % 2 == 0
            out.append({"svg": _page_wrap(ctx, fp, _zones(fp, W, mirror), [], W, H, pno, mirror),
                        "label": label + (f" ({k + 1})" if k else ""), "page_no": pno})
            pno += 1
        return out
    if slots:
        out = []
        from core.units import flow
        for s in (sets or [None]):
            pg = json.loads(json.dumps(page))
            pg["_noguides"] = True
            if s is not None and not page.get("_canvas"):
                _fill_items(pg, s, ctx)
                pg["_canvas"] = True
            lab = label + (f" · {s.get('id', '')}" if s and not label.endswith(str(s.get("id", ""))) else "")
            for k, fp in enumerate([pg] if page.get("_canvas") else flow.thread(ctx, pg, spec)):   # 책에선 넘치면 다음 면으로. 캔버스는 한 면 + 경고
                mirror = bool(fp.get("mirror")) and pno % 2 == 0
                out.append({"svg": _page_wrap(ctx, fp, _zones(fp, W, mirror), [], W, H, pno, mirror),
                            "label": lab + (f" (이어서 {k + 1})" if k else ""), "page_no": pno})
                pno += 1
        return out
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
    for pl in place_items(ctx, page, W, H, mirror):
        it = pl["it"]
        if pl["y"] + pl["h"] > H + 0.01 and not bleeds(pl, H, (ctx.print or {}).get("bleed")):
            ctx.warn(f"{page['id']}: 요소 {it.get('block') or it.get('part') or '원자'} 이 면 아래로 넘친다 ({pl['y'] + pl['h']:.0f}mm > {H:.0f}mm)" + ("" if page.get("_flowed") else " — 책에선 다음 면으로 이어진다"))
        x = W - it["x"] - pl["w"] if mirror else it["x"]
        tf = f"translate({x:.3f},{pl['y']:.3f})" + (f" scale({pl['s']:.4f})" if abs(pl["s"] - 1) > 1e-6 else "")
        chrome.append(f'<g transform="{tf}" data-fi="{pl["fi"]}" data-dy="{pl["dy"]:.2f}"{" data-lock=\"1\"" if it.get("lock") else ""}'
                      f' data-x="{x:.3f}" data-w="{pl["w"]:.3f}" data-y0="{float(it["y"]):.3f}" data-h0="{pl["h0"]:.3f}" data-hc="{pl["h"]:.3f}"'
                      f' data-s="{pl["s"]:.4f}"{" data-fixed=\"1\"" if pl["fixed"] else ""}>{pl["frag"]}</g>')
    ctx.sys = old
    guides = "" if not zones or page.get("_noguides") else "".join(
        f'<rect class="zone" x="{z["x"]:.3f}" y="{z["y"]:.3f}" width="{z["w"]:.3f}" height="{z["h"]:.3f}" '
        f'fill="none" stroke="#c9b8ff" stroke-width="0.25" stroke-dasharray="1.5 1"/>' for z in zones)
    bg = ctx.color(page.get("background"), "#ffffff") if page.get("background") else "#ffffff"
    extra = f'data-page="{pno}" data-tpl="{esc(page["id"])}"' + (f' data-spare="{esc(page["_spare"])}"' if page.get("_spare") else "") \
        + ((' data-push="row" data-tx="%.3f %.3f"' % text_area(page, W)) if page.get("push") == "row" else "")   # 본문 영역 — 크롬 쪽 밀기도 같게
    if ctx.print:
        # 인쇄 모드 — 면 밖에 도련(배경도 늘림) + 재단선. 매체 크기 = 재단 + 2×(도련 + 재단선 자리)
        b = float(ctx.print.get("bleed") or 0)
        m = print_margin(ctx)
        MW, MH = W + 2 * m, H + 2 * m
        inner = (f'<rect x="{-b:.3f}" y="{-b:.3f}" width="{W + 2 * b:.3f}" height="{H + 2 * b:.3f}" fill="{bg}"/>'
                 + "".join(frags) + "".join(chrome) + (crop_marks(W, H, b) if ctx.print.get("marks") else ""))
        return (f'<svg {_NS} viewBox="0 0 {MW:.3f} {MH:.3f}" width="{MW:.3f}mm" height="{MH:.3f}mm" {extra} data-trim="{W:.3f} {H:.3f}" data-bleed="{b:.3f}">'
                f'<rect width="{MW:.3f}" height="{MH:.3f}" fill="#ffffff"/><g transform="translate({m:.3f},{m:.3f})">{inner}</g></svg>')
    if page.get("_canvas") and ctx.board:
        # 대지 — 인디자인처럼 지면 둘레에 자리를 둔다. 지면 밖에 놓은 요소가 잘리지 않는다
        B = float(ctx.board)
        BW, BH = W + 2 * B, H + 2 * B
        return (f'<svg {_NS} viewBox="{-B:.3f} {-B:.3f} {BW:.3f} {BH:.3f}" width="{BW:.3f}mm" height="{BH:.3f}mm" {extra} data-board="{B:.3f}">'
                f'<rect x="{-B:.3f}" y="{-B:.3f}" width="{BW:.3f}" height="{BH:.3f}" fill="#dedbe9"/>'
                f'<rect width="{W:.3f}" height="{H:.3f}" fill="{bg}"/>'
                f'{guides}{"".join(frags)}{"".join(chrome)}</svg>')
    return wrap(guides + "".join(frags) + "".join(chrome), W, H, bg, extra)


def is_fixed(ctx, it, page=None, H=None):
    """머리말·쪽번호·간지(system 블록)는 자리가 고정 — 밀리지도, 다음 면으로 넘어가지도 않는다.

    아래 여백 **밖**(꼬리말 자리)에 그려 둔 것도 고정이다 — 인디자인 마스터 페이지의 꼬리말과 같다.
    본문이 길어져도 쪽번호·꼬리말이 다음 면으로 떠밀려 가면 안 된다.
    """
    blk = ctx.blocks.get(it.get("block")) if it.get("block") else None
    if blk is not None and blk.get("source") == "system":
        return True
    if page is not None and H:
        bm = float((page.get("margins") or {}).get("bottom") or 20)
        if float(it.get("y") or 0) >= float(H) - bm - 0.01:
            return True
        if blk is not None and blk.get("source") != "content":
            # 원고를 안 받는 요소가 꼬리말 자리까지 내려오면(옆 탭 + 쪽 번호 묶음) 마스터 꼬리처럼 고정 — 흘림이 다음 면으로 떠밀지 않는다
            v = variant_of(ctx, blk)
            part = ctx.parts.get(v.get("part")) if v else None
            if part and float(it.get("y") or 0) + float(part.get("h") or 0) * float(it.get("s") or 1) > float(H) - bm + 0.01:
                return True
    return False


def can_grow(it, part):
    """자라서 아래를 미는 요소인가 — **원고가 들어오는 자리만** 자란다.

    인디자인과 같다: 판에 그려 둔 글상자는 크기가 정해져 있고 넘치면 넘침이다. 자리(bind)에는 원고 길이가
    그때그때 다르니 자라고, 그만큼 아래 요소를 민다. `it.grow` 로 하나씩 뒤집을 수 있다.
    """
    if it.get("grow") is not None:
        return bool(it["grow"])
    if it.get("block"):
        return True
    a = it.get("atom")
    if a is not None:
        return bool(a.get("bind")) and not str(a["bind"]).startswith("sys.")      # 쪽 번호·책 제목(책이 채움)은 짧다 — 넘침 계산 중 자리 이름 길이로 자라 본문을 밀면 안 된다
    return any(x.get("bind") for x in (part.get("atoms") or []))


def below_tol(a):
    """「아래에 선 것」의 너그러움(mm) — 글상자 아래 끝에서 줄 높이의 30% 안에서 시작하는 것도 아래 것으로 본다(밀린다).
    다음 줄 글상자는 앞 상자의 줄 간격 여백(반 행간)과 조금 겹쳐 시작한다(11 해석: 문장 상자 끝보다 0.8~0.9mm 위). 글상자가 아니면 0."""
    if a.get("t") != "text":
        return 0.0
    return 0.3 * float(a.get("leading") or float(a.get("size") or 9) * 1.45) * PT


def place_items(ctx, page, W, H, mirror=False):
    """자유 배치 요소를 놓는다 → [{fi, it, frag, w, h, h0, y, dy, fixed}] (그리는 순서).

    글이 길어 자리가 자라면(실제 높이 > 설계 높이) **그 아래, 가로로 겹치는** 요소를 그만큼 민다 — 부품 안 원자와 같은 규칙.
    콘텐츠 블록 자리는 캔버스(_canvas)에서만 그린다(실제 콘텐츠는 세트가 끼운다).
    """
    canvas = bool(page.get("_canvas"))
    ctx.nums = {}                        # 번호 매기기는 면마다 다시 1부터 (시작 번호는 원자의 num_start)
    placed = []
    folded, bands = fold_bands(page)     # 접기 묶음 — 원고가 비운 자리의 묶음은 안 그리고(번호도 안 센다) 그 띠만큼 아래 것을 당긴다
    for fi, it in enumerate(page.get("items") or []):
        if it.get("hide") or fi in folded:
            continue
        blk = ctx.blocks.get(it.get("block")) if it.get("block") else None
        if not canvas and blk is not None and blk.get("source") == "content":
            continue
        frag, part, w, h = _item_frag(ctx, it, (W, H, mirror))
        if frag is None:
            ctx.warn(f"{page['id']}: 요소 {it.get('block') or it.get('part')} 없음")
            continue
        sc = float(it.get("s") or 1)                                   # 균일 배율 — 자리 계산은 배율 곱한 크기로
        placed.append({"fi": fi, "it": it, "frag": frag, "w": w * sc, "h": h * sc, "h0": float(part.get("h") or h) * sc, "s": sc,
                       "fixed": is_fixed(ctx, it, page, H), "grow": can_grow(it, part)})
    grown = [(p["fi"], p["it"]["x"], p["it"]["x"] + p["w"], p["it"]["y"] + p["h0"] - p["s"] * below_tol((p["it"].get("atom") or {})), p["h"] - p["h0"])
             for p in placed if p["grow"] and p["h"] > p["h0"] + 0.01]
    grown += bands
    row = page.get("push") == "row"                                    # 쪽 설정 「자라면 아래 것 모두 밀기」 — 가로로 안 겹쳐도(옆 꼬리표·번호) 아래면 민다
    tx0, tx1 = text_area(page, W)                                      # 단 본문 영역(좌우 여백 안)에 걸친 것만 — 여백 밖 장식(옆 탭)은 그대로
    for p in placed:
        it = p["it"]
        inside = it["x"] < tx1 - 0.01 and it["x"] + p["w"] > tx0 + 0.01
        p["dy"] = 0.0 if p["fixed"] else sum(d for gi, gx0, gx1, gb, d in grown
                                          if gi != p["fi"] and it["y"] >= gb - 0.01 and ((row and inside) or (it["x"] < gx1 - 0.01 and it["x"] + p["w"] > gx0 + 0.01)))
        p["y"] = it["y"] + p["dy"]
    return placed


def text_area(page, W):
    """본문 영역 가로(좌우 여백 안) — 쪽 「여백 및 단」, 없으면 20mm"""
    m = page.get("margins") or {}
    return float(m.get("left") or 20), float(W) - float(m.get("right") or 20)


def fold_bands(page):
    """접기 묶음(원자 fold = 묶음 이름) — 묶음 안 원고 자리 중 하나라도 원고가 비웠으면(_empty, content.fill) 묶음째 접는다.
    → (접힌 요소 번호 set, 당기기 [(-1, x0, x1, 띠 아래 끝, -당길 양)]). 당길 양 = 묶음 높이 + (위 것과 떨어진 묶음이면 아래 틈까지)
    — 떨어진 묶음(문제 하나)은 그 자리로 다음 것이 올라오고, 위 것에 붙은 묶음(지문 상자 밑 주석)은 제 높이만 걷혀 아래 틈이 남는다
    (인디자인 데이터 병합 「빈 필드 줄 제거」를 묶음 단위로)."""
    items = page.get("items") or []
    groups = {}
    for fi, it in enumerate(items):
        g = (it.get("atom") or {}).get("fold")
        if g:
            groups.setdefault(g, []).append(fi)
    folded, bands = set(), []
    box = lambda it: (float(it.get("x") or 0), float(it.get("y") or 0), float((it.get("atom") or {}).get("w") or it.get("w") or 0),
                      float((it.get("atom") or {}).get("h") or it.get("h") or 0))
    for g, fis in groups.items():
        if not any(items[fi].get("_empty") for fi in fis):
            continue
        folded.update(fis)
        bx = [box(items[fi]) for fi in fis]
        x0, x1 = min(b[0] for b in bx), max(b[0] + b[2] for b in bx)
        top, bot = min(b[1] for b in bx), max(b[1] + b[3] for b in bx)
        over = lambda b: b[0] < x1 - 0.01 and b[0] + b[2] > x0 + 0.01
        below = [box(it)[1] for fi, it in enumerate(items) if fi not in folded and not it.get("hide") and box(it)[1] >= bot - 0.01 and over(box(it))]
        above = [box(it)[1] + box(it)[3] for fi, it in enumerate(items) if fi not in folded and not it.get("hide")
                 and box(it)[1] + box(it)[3] <= top + 0.01 and over(box(it))]
        gap_below = (min(below) - bot) if below else 0.0
        attached = bool(above) and top - max(above) < 0.5               # 위 것에 붙은 묶음(지문 상자 밑 주석) — 제 높이만. 떨어진 묶음(문제 하나) — 아래 틈까지
        bands.append((-1, x0, x1, bot, -((bot - top) + (0.0 if attached else gap_below))))
    return folded, bands


def atom_part(atom):
    """원자 하나를 임시 부품으로 — 캔버스에 낱개로 놓은 글상자·선·면·원·그림·도형."""
    a = dict(atom)
    if a.get("t") == "line":
        w, h = abs(a.get("x2", 0) - a.get("x1", 0)), abs(a.get("y2", 0) - a.get("y1", 0))
    else:
        w, h = a.get("w", 10), a.get("h", 10)
    return {"id": "_atom", "name": "원자", "w": max(w, 0.5), "h": max(h, 0.5), "atoms": [a]}


def _item_frag(ctx, it, at=None):
    """자유 배치 요소 하나 → (SVG 조각, 부품, 폭, 실제 높이). 블록이면 옷이 고른 모양의 부품 + 견본 값. 원자면 임시 부품.

    at = (W, H, mirror) 를 주면 인쇄 모드의 도련 늘림이 면 안 자리를 안다.
    """
    def origin(w):
        ctx._item_y = float(it.get("y") or 0)                          # 기준선 격자 — 이 요소가 면에서 놓인 세로 자리
        if at and ctx.print:
            W, H, mirror = at
            sc = float(it.get("s") or 1)                               # 도련 늘림은 배율 전 좌표계에서 — 면 크기를 배율로 나눠 넣는다
            ctx._at = (((W - float(it["x"]) - w * sc) if mirror else float(it["x"])) / sc, float(it["y"]) / sc, W / sc, H / sc)
        else:
            ctx._at = None
    if it.get("atom"):
        part = atom_part(it["atom"])
        if at and at[2]:
            part = mirror_part(part)                                   # 낱개 글상자 — 자리는 _page_wrap 이, 정렬은 여기서 뒤집는다
        w = float(it.get("w") or part["w"])
        origin(w)
        values = it.get("fields") or {}                                # 원고 자리 글상자 — 세트가 끼운 값
        types = {k: ("rich" if isinstance(v, list) else "text") for k, v in values.items()}
        frag, h = part_svg(ctx, part, values, types, width=w)
        return frag, part, w, h
    if it.get("block"):
        blk = ctx.blocks.get(it["block"])
        v = variant_of(ctx, blk) if blk else None
        part = ctx.parts.get(v.get("part")) if v else None
        if not part:
            return None, None, 0, 0
        if at and at[2]:
            part = mirror_part(part)
        types = {k: (f or {}).get("type", "text") for k, f in (blk.get("fields") or {}).items()}
        w = float(it.get("w") or part.get("w") or 0)
        values = {k: "" for k in types} if it.get("_empty") else sample.fill(blk, it.get("fields"))   # 책에서 원고 없는 자리는 빈 채로
        given = set((it.get("fields") or {}).keys())
        for a2 in (part.get("atoms") or []):                           # 번호 매기기 자리는 견본 번호 대신 저절로 매긴다
            if a2.get("num") and a2.get("bind") and a2["bind"] not in given:
                values.pop(a2["bind"], None)
        origin(w)
        frag, h = part_svg(ctx, part, values, types, width=w)
        return frag, part, w, h
    part = ctx.parts.get(it.get("part"))
    if not part:
        return None, None, 0, 0
    if at and at[2]:
        part = mirror_part(part)
    w = float(it.get("w") or part.get("w") or 0)
    origin(w)
    frag, h = part_svg(ctx, part, {}, width=w)
    return frag, part, w, h


def mirror_part(part):
    """왼쪽 면(짝수 쪽) — 요소 안쪽 배치도 좌우로 뒤집는다(글자는 안 뒤집는다). 인디자인의 좌우 마스터처럼
    오른쪽 면에 그린 요소의 「바깥쪽」(옆 탭·쪽 번호)이 왼쪽 면에선 왼쪽 바깥에 온다. 요소 상자 자리는 _page_wrap 이 뒤집는다."""
    pw = float(part.get("w") or 0)
    atoms = []
    for a in part.get("atoms") or []:
        a = dict(a)
        if a.get("t") == "line":
            a["x1"], a["x2"] = pw - float(a["x1"]), pw - float(a["x2"])
        else:
            a["x"] = pw - float(a.get("x") or 0) - float(a.get("w") or 0)
        if a.get("align") in ("left", "right"):                          # 정렬을 준 글만 — 바깥쪽 정렬(인디자인 「책등 반대쪽 정렬」)
            a["align"] = "left" if a["align"] == "right" else "right"
        atoms.append(a)
    return dict(part, atoms=atoms)


DEFAULT_SPEC = {"id": "a4", "w": 210.0, "h": 297.0, "bleed": 3.0}


def bleeds(pl, H, bleed=None):
    """재단 여백까지 칠한 요소(바탕·막대)인가 — 넘침이 아니다. 제자리(밀리지 않은) 원자이고 끝이 도련 안."""
    it = pl["it"]
    b = float(bleed if bleed is not None else DEFAULT_SPEC["bleed"])
    return pl.get("dy", 0) < 0.01 and not it.get("block") and not _atom_slot(it) and pl["y"] + pl["h"] <= H + b + 0.01


def story_spares(ctx, pages, spec_of):
    """넘치면 쪽 더하기(인디자인 스마트 텍스트 리플로우) — 원고가 든 이야기(글 잇기)가 틀의 상자들보다 길 듯하면, 그 이야기가 끝나는 쪽 뒤에
    「넘치면 이어 갈 면」(page.cont, 없으면 그 쪽)을 여유 있게 덧붙인다. 덧붙인 쪽에는 그 이야기 상자(차례 번호를 이어서)와 장식만 남긴다.
    크롬이 글을 흘린 뒤 빈 채로 남은 덧쪽은 지운다(units_compose.js dropSpares). → {쪽 번호: [덧쪽 지면…]}"""
    out = {}
    heads, boxes = {}, {}
    for pi, pg in enumerate(pages):
        for it in pg.get("items") or []:
            a = it.get("atom") or {}
            if a.get("t") != "text" or not a.get("story"):
                continue
            boxes.setdefault(a["story"], []).append((pi, it))
            if story_seq(a) <= 1 and (it.get("fields") or {}).get(a.get("bind")) not in (None, ""):
                heads[a["story"]] = (pi, it)
    for name, (hpi, head) in heads.items():
        a = head["atom"]
        chain = boxes[name]
        last_pi = max(pi for pi, _ in chain)
        cap = sum(float(it.get("h") or (it.get("atom") or {}).get("h") or 0) for _, it in chain)
        w = float(head.get("w") or a.get("w") or 80)
        plain = rich_plain(head["fields"][a["bind"]])
        need = text_h(plain, w, float(a.get("size") or 9), a.get("leading"), a) * 2.0         # 넉넉히 — 자리마다 단락 스타일(행간·앞 간격)은 어림에 안 든다(정본 실전 문제 54쪽에서 모자랐다). 남는 덧쪽은 크롬이 지운다
        if need <= cap * 0.9:
            continue
        last = pages[last_pi]
        has = lambda t: any((it.get("atom") or {}).get("story") == name for it in t.get("items") or [])
        tpl = ctx.pages.get(last.get("cont")) or last
        if not has(tpl):                                               # 이어 갈 면에 이 이야기 상자가 없다 — 지금 쪽 모양으로
            tpl = last
        per = sum(float(it.get("h") or (it.get("atom") or {}).get("h") or 0) for it in tpl.get("items") or []
                  if (it.get("atom") or {}).get("story") == name) or 1
        n = min(120, int(math.ceil((need - cap) / per)) + 1)                 # 덧쪽 한도 — 실전 문제 한 구간 75쪽(정본 198~272)
        seq = max(story_seq(it["atom"]) for _, it in chain)
        spares = []
        for k in range(n):
            pg = json.loads(json.dumps(tpl))
            nxt = ctx.pages.get(tpl.get("cont"))                       # 다음 덧쪽은 이 면의 「이어 갈 면」 — 왼쪽·오른쪽 면이 번갈아(인디자인 마스터 A·B)
            tpl = nxt if nxt and has(nxt) else tpl
            items = []
            for it in pg.get("items") or []:
                at = it.get("atom") or {}
                if at.get("story") == name:
                    seq += 1
                    at = dict(at, story_seq=seq)
                    at.pop("bind", None)
                    it = dict(it, atom=at)
                    it.pop("fields", None)
                elif _atom_slot(it) or (it.get("block") and (ctx.blocks.get(it["block"]) or {}).get("source") == "content"):
                    continue                                           # 다른 원고 자리는 덧쪽에 안 둔다
                items.append(it)
            pg["items"] = items
            pg["_spare"] = name
            spares.append(pg)
        out.setdefault(last_pi, []).extend(spares)
    return out


def page_canvas_svgs(ctx, page, spec, sample_set=None, pno=1):
    """캔버스 미리보기 — 자유 배치 요소(items)를 그린다. 콘텐츠 블록 자리는 견본 값으로.
    pno = 이 쪽이 문서에서 몇째 쪽인가(쪽 번호 자리 sys.page_no 가 이 값). 모르면 1.

    sample_set(세트)을 주면 같은 블록의 값을 순서대로 끼운다 — 어법 O/X 줄 셋이면 세트의 1·2·3번 문장.
    (옛 형식: 칸 흐름 배치 page.blocks 도 아직 그린다.) 넘치면 여러 면이 되므로 캔버스는 첫 장만 보인다.
    """
    load_page_env(ctx, page)                                   # 레이어·기준선 격자
    pg = json.loads(json.dumps(page))
    pg["_noguides"] = True                     # 캔버스는 자유 배치 — 칸 안내선은 안 보인다
    pg["_canvas"] = True                       # 콘텐츠 블록 자리(items)도 견본으로 그린다
    pg["mirror"] = False                       # 캔버스는 그린 그대로 — 쪽 번호(pno)가 짝수여도 뒤집지 않는다(예전엔 늘 1쪽으로 그려 안 뒤집혔다)
    if sample_set:
        _fill_items(pg, sample_set, ctx=ctx, canvas=True)          # 캔버스 미리보기 — 검수 항목은 안 쌓되 유형 이름 짝짓기는 한다
    sets = []
    for z in pg.get("zones") or []:
        kind = "_canvas:" + z["id"]
        z["accepts"] = [kind]
        blocks = [{"block": b["block"], "fields": {}, "_i": i} for i, b in enumerate(pg.get("blocks") or []) if b.get("zone") == z["id"]]
        if blocks:
            sets.append({"kind": kind, "id": z["id"], "blocks": blocks})
    ctx.sys.setdefault("section", "STEP 2")
    return page_svgs(ctx, pg, sets, spec, pno, pg.get("name", ""))


def _per(pg):
    """그 면에 원고 몇 개씩 — 「지문 2개씩 한 장」이면 2 (인디자인 데이터 병합의 여러 레코드)."""
    try:
        return max(1, int(pg.get("per") or 1))
    except (TypeError, ValueError):
        return 1


def _merge_sets(ss):
    """원고 여럿 → 한 면에 넣을 한 원고. 자리 이름이 같은 값은 차례로 — 지문 번호 상자 둘이면 20 · 21."""
    if len(ss) == 1:
        return ss[0]
    return {"kind": ss[0].get("kind"), "id": " · ".join(str(s.get("id", "")) for s in ss), "group": ss[0].get("group"),
            "labels": ss[0].get("labels"),
            "blocks": [b for k, s in enumerate(ss) for b in s.get("blocks") or [] if k == 0 or not b.get("optional")]}   # 머리 정보(optional)는 첫 원고 것만


def plan_svgs(ctx, plan, sets, lib):
    """틀 → 면 목록. 앞면 → 구간(간지 + 지면 반복) → 뒷면. 쪽번호는 이어진다."""
    ctx.map = plan.get("map") or ctx.map or {}                 # 문서의 원고 연결표 — 책·PDF·검수에도 쓴다
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
        res = page_svgs(ctx, pg, ss, specs.get(pg.get("spec")) or spec, pno, label)     # 면마다 자기 판형 (B4 시험지 면 · A4 표지 …)
        out.extend(res)
        pno += len(res)

    for pid in plan.get("front") or []:
        emit(pid, [], "앞")
    if any("answers" in (pg.get("sets") or []) for sec in plan.get("sections") or [] for pg in sec.get("pages") or []):
        from core.units import answers as _answers
        sets = list(sets or []) + _answers.answer_sets(sets, list(ctx.blocks.values()))      # 정답지 — 세트의 정답을 모아 정답 세트로
    by_set = (plan.get("order") or "by_page") == "by_set"          # 묶는 순서 — 원고가 바깥쪽 반복(지문별) / 면이 바깥쪽(유형별)

    def pg_sets(pg):
        kinds = pg.get("sets")
        return [s for s in sets or [] if not kinds or s.get("kind") in kinds]

    for sec in plan.get("sections") or []:
        ctx.sys["section"] = sec.get("name", "")
        if sec.get("divider"):
            emit(sec["divider"], [], sec.get("name", "") + " 간지")
        pgs = sec.get("pages") or []
        i = 0
        while i < len(pgs):
            pg = pgs[i]
            if pg.get("repeat") == "none":                          # 찍지 않는 면 — 다른 면이 넘친 글을 이어 받는 모양(page.cont)으로만
                i += 1
                continue
            if pg.get("repeat") != "each_set":
                ss = pg_sets(pg)
                if ss and (pg.get("sets") or []) == ["answers"]:        # 정답지 한 번만 — 정답을 한 흐름으로 모아 넘치면 다음 면
                    ss = [{"kind": "answers", "id": "answers", "labels": {}, "blocks": [b for s in ss for b in s.get("blocks") or []]}]
                emit(pg["page"], ss, sec.get("name", ""))
                i += 1
                continue
            if not by_set:                                          # 유형별 — 이 면을 원고 수만큼 몰아서 (per 개씩 한 면)
                ss = pg_sets(pg)
                per = _per(pg)
                for k in range(0, len(ss), per):
                    m = _merge_sets(ss[k:k + per])
                    emit(pg["page"], [m], f"{sec.get('name', '')} · {m.get('id', '')}")
                i += 1
                continue
            j = i                                                   # 지문별 — 잇닿은 「지문마다」 면들을 한 벌로 묶어 원고마다 한 벌씩
            while j < len(pgs) and pgs[j].get("repeat") == "each_set":
                j += 1
            run = pgs[i:j]
            groups = []                                             # 같은 지문(group)의 세트끼리 — 스텝마다 세트가 따로 와도 지문 20 의 A1·A2… 가 한 벌
            for s in sets or []:
                g = str(s.get("group") or s.get("id"))
                if g not in groups:
                    groups.append(g)
            n = max(_per(p2) for p2 in run)                          # 한 면에 지문 둘인 면이 있으면 지문 둘씩 한 벌
            for gi in range(0, len(groups), n):
                chunk = set(groups[gi:gi + n])
                for p2 in run:
                    kinds = p2.get("sets")
                    ss = [s for s in sets or [] if str(s.get("group") or s.get("id")) in chunk and (not kinds or s.get("kind") in kinds)]
                    per = _per(p2)
                    for k in range(0, len(ss), per):
                        m = _merge_sets(ss[k:k + per])
                        emit(p2["page"], [m], f"{sec.get('name', '')} · {m.get('id', '')}")
            i = j
    ctx.sys["section"] = ""
    for pid in plan.get("back") or []:
        emit(pid, [], "뒤")
    return out
