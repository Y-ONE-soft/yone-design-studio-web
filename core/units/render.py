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
        if ref == "none":                                 # 색상 견본 [없음] — 투명(인디자인). 글자 색 [없음] + 밑줄 = 정답 칸
            return "transparent"
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
def anchor_obj(anc, ctx, a=None):
    """고정 개체의 내용 — 부품(그룹)이면 SVG, 글이면 텍스트 프레임(글꼴 · 크기 · 행간 · 색 · 문자 스타일 · 폭). → (html, 폭 mm, 높이 mm) 또는 None"""
    if anc.get("part"):
        part = (ctx.parts or {}).get(anc["part"]) if ctx else None
        if not part:
            if ctx:
                ctx.warn(f"고정 개체의 그룹(부품) 없음 {anc['part']}")
            return None
        z0 = getattr(ctx, "zoom_out", 1)
        ctx.zoom_out = z0 * text_zoom(a or {}, z0)                    # 그룹 속 글은 바깥 글의 배율 안에서 그려진다
        try:
            frag, ph = part_svg(ctx, part)
        finally:
            ctx.zoom_out = z0
        w = float(anc.get("w") or part.get("w") or 10)
        h = float(anc.get("h") or part.get("h") or ph or 5)
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {float(part.get("w") or w):.3f} {float(part.get("h") or h):.3f}" '
               f'width="{w:.3f}" height="{h:.3f}" style="display:block;overflow:visible;width:{w:.3f}px;height:{h:.3f}px">{frag}</svg>')
        return svg, w, h
    if anc.get("text") is not None:                                    # 글 — 고정 개체 텍스트 프레임(문단마다 한 줄 이상)
        st = (ctx.cstyle_css(anc["cs"]) if (ctx and anc.get("cs")) else "").replace("line-height:0;", "")
        st += _font_css({k: anc[k] for k in ("font", "size", "leading", "color", "weight", "tracking") if anc.get(k) not in (None, "")}, ctx) if ctx else ""
        if anc.get("align"):
            st += align_css(anc["align"])
        w = anc.get("w")
        ws = f"width:{float(w):.3f}px;" if w else "width:max-content;"
        body = "".join(f'<span style="display:block">{esc(x) or "&#160;"}</span>' for x in str(anc["text"]).split("\n"))
        return (f'<span style="display:block;{ws}text-indent:0;letter-spacing:0;word-spacing:0;white-space:{"normal" if w else "nowrap"};text-align:left;{st}">{body}</span>',
                float(w or 0), 0.0)
    return None


def anchored_html(anc, ctx, a=None):
    """인디자인 고정 개체 하나 → 글 안에 끼울 HTML(인라인 · 사용자 정의). 줄 위는 _para 가 제 단락으로 놓는다.
    인라인: X 오프셋(앞 글과 사이) · Y 오프셋(위가 +) — 글자처럼 흘러 자리가 모자라면 마지막 낱말과 함께 다음 줄로(space 면 개체만).
    사용자 정의: X 기준 텍스트 프레임 가장자리(frame) · 앵커 표시자(anchor), Y 기준 라인(기준선)(baseline) · 라인(행간 위쪽)(leading) — 글 흐름에 안 낀다."""
    o = anchor_obj(anc, ctx, a)
    if not o:
        return ""
    body, w, h = o
    pos = anc.get("pos") or "inline"
    x, y = float(anc.get("x") or 0), float(anc.get("y") or 0)
    if pos == "custom":
        va = "top" if anc.get("yref") == "leading" else "baseline"
        hx = f"left:calc({x:.3f}px - var(--ax, 0px));" if anc.get("xref", "frame") == "frame" else f"margin-left:{x:.3f}px;"
        return (f'<span data-side="1" style="display:inline-block;width:0;height:0;vertical-align:{va}">'
                f'<span style="position:absolute;{hx}margin-top:{y:.3f}px">{body}</span></span>')
    lead = " " if anc.get("space") else "\u2060"                      # 개체 앞 공백 문자 — 줄 끝이면 공백에서 꺾여 개체만 다음 줄로
    return (f'{lead}<span data-anc="1" style="display:inline-block;{f"width:{w:.3f}px;" if w else ""}{f"height:{h:.3f}px;" if h else ""}margin-left:{x:.3f}px;'
            f'vertical-align:{y:.3f}px;letter-spacing:0;text-indent:0">{body}</span>')


def text_zoom(a, outer=1):
    """글상자 배치 배율(TEXT_ZOOM) — 크롬은 글자를 1만 px 보다 크게 못 그린다(300pt 가 283pt 로): 큰 글은 낮춘다.
    outer = 이 글을 감싼 글의 배율(글 끝에 붙인 부품 속 글) — 배율이 곱해지므로 그만큼 나눈다(안 나누면 1만 px 에 걸려 1/3 크기로, 단위 10 O·X)."""
    big = float(a.get("size") or 9) * PT
    return max(1, min(TEXT_ZOOM, int(9000 / max(big * outer, 0.1))))


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
        if "ps" in v:                                                      # 한 줄기 글의 자리 표시(content.story_value) — 문단 첫머리 · 같은 단락에 이어 쓰는 필드(번호)
            if v.get("inline"):                                            # 템플릿 단락 「«번호»⇥«발문»」 — 번호 뒤 글자(sep: 탭 · 공백 …)까지
                a = getattr(ctx, "cur_atom", None) or {} if ctx else {}
                sep = (((a.get("slot_fmt") or {}).get(v["ps"]) or {}).get("sep"))
                return f'<span data-psi="{esc(v["ps"])}">{esc(v.get("t", ""))}</span>' + esc(_after(sep))
            ov = {k: v["ov"][k] for k in OV_KEYS if isinstance(v.get("ov"), dict) and v["ov"].get(k) is not None}   # 단락 스타일 재정의(인디자인 로컬 서식)
            return (f'<span data-ps="{esc(v["ps"])}"' + (f' data-ov="{esc(json.dumps(ov))}"' if ov else "") + (' data-v0="1"' if v.get("v0") else "")
                    + '></span>') + esc(v.get("t", ""))
        if "para" in v:                                                    # 단락 묶음 — 테두리 상자·들여쓰기 (자리마다 서식)
            return f'<div style="{para_css(v["para"], ctx)}">{rich_html(v.get("c"), ctx)}</div>'
        a = getattr(ctx, "cur_atom", None) if ctx else None
        if v.get("anc"):                                                   # 고정 개체(인디자인) — 글 안 그 자리에
            return (anchored_html(v["anc"], ctx, a) if ctx else "") + esc(v.get("t", ""))
        if "side" in v:                                                    # 원고 꼴 옆 메모 [[…]] — 이 텍스트 프레임의 「원고 고정 개체」 설정으로 고정 개체(사용자 정의 위치)
            d = (a or {}).get("side") or {}
            return anchored_html({"text": v["side"], "pos": "custom", "xref": "frame", "yref": "baseline", "x": d.get("x") or 0, "y": d.get("off") or 0,
                                  "w": d.get("w") or 30, "leading": d.get("lead"), "cs": d.get("cs")}, ctx, a) if ctx else ""
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
        if v.get("size"):                                                  # 줄 높이 0 — 크기 바꾼 조각이 고정 행간 줄을 키우지 않게(인디자인 행간)
            st += f"font-size:{float(v['size']) * PT:.3f}px;line-height:0;"
        if v.get("bshift"):
            st += f"position:relative;top:{-float(v['bshift']) * PT:.3f}px;"
        if v.get("tracking"):
            st += f"letter-spacing:{float(v['tracking']) / 1000.0:.4f}em;"
        if v.get("case") in ("upper", "small"):
            st += "text-transform:uppercase;" if v["case"] == "upper" else "font-variant:small-caps;"
        hs, vs = v.get("hscale"), v.get("vscale")
        if hs or vs:
            st += f"display:inline-block;transform:scale({float(hs or 100) / 100.0:.3f},{float(vs or 100) / 100.0:.3f});transform-origin:0 100%;"
        direct = st                                                        # 고른 글자에 바로 준 서식(인디자인 로컬 서식) — GREP 스타일보다 앞선다(grep_html 이 data-lo 를 이어 붙인다)
        if v.get("cs"):                                                    # 문자 스타일(하나 또는 여럿 — 글자색 + 형광 띠) — 조각의 칸 값이 그 위에
            names = [v["cs"]] if isinstance(v["cs"], str) else list(v["cs"])
            st = ("".join(ctx.cstyle_css(c) for c in names) if ctx else "") + st
        if st:
            lo = f' data-lo="{esc(direct)}"' if direct else ""
            t = f'<span style="{st}"{lo}>' + t + "</span>"
        rb = v.get("ruby")                                                 # 윗주(인디자인) — 글자 하나에 하나
        extra = ""
        if isinstance(rb, list):                                           # 원고 꼴 [위, 아래] — 첫째는 윗주, 나머지는 그 낱말에 붙인 고정 개체(앵커 표시자 기준, 윗주와 같은 모양)
            plain = re.sub(r"<[^>]+>", "", t)
            rest = [x for x in rb[1:] if isinstance(x, dict) and x.get("t")]
            rb = rb[0] if rb else None
            extra = "".join(ruby_html("", x, a, ctx, plain).replace('data-ruby="1"', 'data-side="1"') for x in rest)
        if isinstance(rb, dict) and rb.get("t"):
            t = ruby_html(t, rb, a, ctx)
        return extra + t
    return esc(v)


_TAG = re.compile(r"(<[^>]+>)")
_UL_STYLE = {"wavy": "wavy", "dotted": "dotted", "dashed": "dashed", "double": "double"}     # 밑줄 모양 — 없으면 실선
CSTYLE_KEYS = ("font", "size", "color", "weight", "i", "track", "bshift", "u", "u_w", "u_off", "u_color", "u_style", "nobreak", "case")
_ASC = {}


_HW = {}
HANGUL_BASE = 0.92                 # 넘침 어림(한글 1em)을 맞춰 둔 서체 Noto Sans CJK KR 의 한글 폭(em)


def hangul_scale(family, weight=400):
    """넘침 어림의 한글 폭 배율 — 그 서체 「가」 폭 / Noto 한글 폭(0.92em), 1 을 넘지 않는다. 못 찾으면 1(지금 어림 그대로).
    KCC도담도담처럼 한글이 좁은 서체(0.76em)는 안 넘치는 글을 넘친다고 보던 것"""
    if not family:
        return 1.0
    key = (family, int(weight or 400))
    if key not in _HW:
        v = 1.0
        try:
            from core.units.fonts import system_fonts
            fs = [f for f in system_fonts() if f["family"] == family and not f["italic"]]
            f = next((f for f in fs if f["weight"] == key[1]), None) or (fs[0] if fs else None)
            if f:
                from fontTools.ttLib import TTFont
                t = TTFont(f["path"], lazy=True, fontNumber=0)
                g = t.getBestCmap().get(ord("가"))
                if g:
                    v = min(1.0, t["hmtx"][g][0] / t["head"].unitsPerEm / HANGUL_BASE)
        except Exception:
            pass
        _HW[key] = v
    return _HW[key]


def font_ascent(family, weight=400):
    """서체 윗높이(em) — hhea(크롬이 글 상자 높이를 잡는 값). 못 찾으면 1.0"""
    key = (family, int(weight or 400))
    if key not in _ASC:
        v = 1.0
        try:
            from core.units.fonts import system_fonts
            fs = [f for f in system_fonts() if f["family"] == family and not f["italic"]]
            f = next((f for f in fs if f["weight"] == key[1]), None) or (fs[0] if fs else None)
            if f:
                from fontTools.ttLib import TTFont
                t = TTFont(f["path"], lazy=True)
                v = t["hhea"].ascent / t["head"].unitsPerEm
        except Exception:
            pass
        _ASC[key] = v
    return _ASC[key]


def _fit_align(a):
    """그림 맞춤 기준점(인디자인 프레임 맞춤 옵션) → SVG preserveAspectRatio 정렬. tl·t·tr·l·c·r·bl·b·br, 없으면 가운데.
    fit = fill(틀에 맞게 늘이기)이면 "none" — 뒤에 붙는 meet · slice 는 SVG 가 무시한다"""
    if a.get("fit") == "fill":
        return "none"
    at = a.get("fit_at") or "c"
    x = "xMin" if "l" in at else "xMax" if "r" in at else "xMid"
    y = "YMin" if at[0] == "t" else "YMax" if at[0] == "b" else "YMid"
    return x + y


def char_css(cs, ctx=None):
    """문자 스타일(인디자인 문자 스타일) → 인라인 CSS. 글꼴 · 글꼴 스타일(굵기 · 기울임) · 크기 pt · 문자 색상 · 자간(1/1000 em) · 기준선 이동 pt ·
    밑줄(두께 · 오프셋 pt — 기준선에서 밑줄 위 끝까지, 유형, 색상) · 줄 바꿈 없음 · 대소문자."""
    col = lambda v: ctx.color(v) if ctx else v
    st = ""
    if cs.get("font"):
        st += f"font-family:{ctx.font(cs['font']) if ctx else font_family(cs['font'])};"
    if cs.get("size"):                                                     # 줄 높이 0 — 작은 글자가 고정 행간 줄을 키우지 않게(인디자인 행간)
        st += f"font-size:{float(cs['size']) * PT:.3f}px;line-height:0;"
    if cs.get("color"):
        st += f"color:{col(cs['color'])};"
    if cs.get("weight"):
        st += f"font-weight:{int(cs['weight'])};"
    if cs.get("i"):
        st += "font-style:italic;"
    if cs.get("track"):
        st += f"letter-spacing:{float(cs['track']) / 1000:.4f}em;"
    if cs.get("bshift"):
        st += f"position:relative;top:{-float(cs['bshift']) * PT:.3f}px;"
    if cs.get("nobreak"):                                                  # 줄 바꿈 없음 — 한 줄에(인디자인 문자 스타일 · GREP 스타일)
        st += "white-space:nowrap;"
    if cs.get("case") in ("upper", "small"):
        st += "text-transform:uppercase;" if cs["case"] == "upper" else "font-variant:small-caps;"
    if cs.get("u"):
        st += underline_css(cs, ctx)
    return st


def underline_css(cs, ctx=None):
    """밑줄 옵션(인디자인) — 두께 u_w pt · 오프셋 u_off pt(기준선 → 밑줄 위 끝, 아래가 +) · 유형 · 색상.
    실선은 글 뒤 바탕 그림으로 그린다(굵은 밑줄을 위로 올린 형광 띠까지 — 크롬은 조각이 섞인 글에서 두꺼운 밑줄을 빠뜨린다).
    자리는 글 상자 위 끝(기준선 − 윗높이)에서 잰다 — 서체 윗높이(hhea)를 em 으로."""
    col = (lambda v: ctx.color(v) if ctx else v)
    w = float(cs.get("u_w") if cs.get("u_w") is not None else 0.5) * PT
    off = float(cs.get("u_off") if cs.get("u_off") is not None else 1.0) * PT
    c = col(cs["u_color"]) if cs.get("u_color") else "currentColor"
    style = cs.get("u_style") or "solid"
    if style == "solid" and c != "currentColor":
        a = getattr(ctx, "cur_atom", None) or {} if ctx else {}
        fam = cs.get("font") or a.get("font") or ""
        if ctx and str(fam).startswith("$"):
            fam = ctx._tok(fam, "font", "")
        asc = font_ascent(fam, cs.get("weight") or a.get("weight") or 400)
        return (f"background-image:linear-gradient({c},{c});background-repeat:no-repeat;"
                f"background-size:100% {w:.3f}px;background-position:0 calc({asc:.4f}em + {off:.3f}px);"
                "-webkit-box-decoration-break:clone;box-decoration-break:clone;")
    return (f"text-decoration:underline;text-decoration-thickness:{w:.3f}px;text-decoration-color:{c};"
            f"text-decoration-style:{_UL_STYLE.get(style, 'solid')};text-underline-offset:{off:.3f}px;text-decoration-skip-ink:none;")


def ruby_html(base, rb, a, ctx, plain=None):
    """윗주(인디자인 윗주) — 본문 글자 위나 아래 작은 글. 본문 첫머리 기준선에 폭 · 높이 0 인 점(inline-block)을 찍고 거기서 잰다:
    줄 간격 · 줄 나눔이 그대로고(단락 컴포저는 inline-block 을 글자 하나로 센다) 본문과 함께 움직인다.
    rb = {t, pos: above | below, align: left | center | right, ox, oy(mm), font, size(pt), color} — 없는 값은 텍스트 프레임의 윗주 기본값(a.ruby).
    오프셋 Y = 본문 글자 상자(전각 상자: 기준선 위 0.88em · 아래 0.12em) 바깥 끝에서 윗주까지, 바깥이 +."""
    d = (a or {}).get("ruby") or {}
    deco = ""
    if rb.get("cs") and ctx:                                            # 원고가 문자 스타일 이름을 준 윗주(서술형★ · 기출✓) — 그 스타일의 글꼴 · 크기 · 색상을 이 윗주 값으로
        cs = (ctx.skin.get("cstyles") or {}).get(rb["cs"]) or {}
        rb = dict({k: cs[k] for k in ("font", "size", "color") if cs.get(k) is not None}, **rb)
        if any(cs.get(k) for k in ("weight", "track", "u")):            # 굵기 · 자간 · 밑줄(굵은 밑줄 = 바탕 띠, 상자 딱지) — 글꼴은 띠 자리(윗높이) 재기에만
            deco = char_css({k: cs[k] for k in ("font", "weight", "track", "u", "u_w", "u_off", "u_color", "u_style") if cs.get(k) is not None}, ctx)
    g = lambda k, dv=None: rb.get(k) if rb.get(k) is not None else d.get(k, dv)
    pos = "below" if rb.get("pos") == "below" else "above"
    bsz = float((a or {}).get("size") or 9) * PT
    st = ""
    if g("font"):
        st += f"font-family:{esc(ctx.font(g('font')) if ctx else g('font'))};"
    st += f"font-size:{float(g('size')) * PT:.3f}px;" if g("size") else "font-size:50%;"
    if g("color"):
        st += f"color:{ctx.color(g('color')) if ctx else g('color')};"
    oy = float(rb.get("oy") if rb.get("oy") is not None else d.get("oy_below" if pos == "below" else "oy_above", 0) or 0)
    off = oy + (0.88 if pos == "above" else 0.12) * bsz                 # 기준선에서 윗주 끝까지
    ox = float(g("ox", 0) or 0)
    al = g("align", "left") or "left"
    v = f"top:{off:.3f}px" if pos == "below" else f"bottom:{off:.3f}px"
    plain = plain if plain is not None else re.sub(r"<[^>]+>", "", base)
    js = {"center": "center", "right": "end"}.get(al, "start")
    txt = f'<span style="{deco}">{esc(rb.get("t", ""))}</span>' if deco else esc(rb.get("t", ""))   # 꾸밈은 줄 안 글 칸에 — 바탕 띠가 글꼴 높이만큼 그려지게(칸 상자는 줄 높이 1 이라 잘린다)
    inner = (f'<span style="grid-area:1/1;justify-self:center;width:0;display:flex;justify-content:center;{st}"><span style="white-space:nowrap">{txt}</span></span>'
             if js == "center" else f'<span style="grid-area:1/1;justify-self:{js};{st}">{txt}</span>')
    return ('\u2060<span data-ruby="1" style="display:inline-block;width:0;height:0;position:relative;vertical-align:baseline">'
            f'<span style="position:absolute;left:{ox:.3f}px;{v};display:grid;width:max-content;white-space:nowrap;line-height:1;text-indent:0;letter-spacing:0;word-spacing:0">'   # 칸 폭 = 본문 폭
            f'<span style="grid-area:1/1;height:0;overflow:hidden;visibility:hidden">{plain}</span>'
            + inner + f'</span></span>\u2060{base}')


# 원고 표시 읽기 — 바깥 시스템이 글로 보내는 약속 표시를 윗주·옆 메모 조각으로(글상자 「원고 표시 읽기」를 켠 자리만).
# {본문|아래 윗주} · {본문^위 윗주} · {본문^위|아래} · [[옆 메모]]. 꾸밈(형광·색)은 GREP → 문자 스타일로.
_MARK = re.compile(r"\{([^{}|^]+)(?:\^([^{}|]*))?(?:\|([^{}]*))?\}|\[\[(.+?)\]\]")


def markup_runs(v):
    """약속 표시가 든 글 → 조각 목록. 표시가 없으면 그대로(글)."""
    if isinstance(v, list):                                    # 조각 목록(한 글상자 여러 자리 등) — 글 조각마다
        out = []
        for x in v:
            r = markup_runs(x) if isinstance(x, str) else x
            out.extend(r if isinstance(r, list) else [r])
        return out
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
    """GREP 스타일(인디자인) — 글 HTML 의 글자 부분(태그 밖)에서 대상 텍스트(정규식)에 맞는 곳에 문자 스타일을 적용한다.
    태그를 걸쳐 맞는 곳은 건드리지 않는다. 정규식이 틀리면 그 규칙만 건너뛴다."""
    for r in rules or []:
        try:
            rx = re.compile(r.get("re") or "")
        except re.error:
            continue
        if not rx.pattern or not r.get("cs"):
            continue
        st = ctx.cstyle_css(r["cs"]) if ctx else ""

        def wrap(m):
            t = esc(m.group(0))
            lo = los[-1] if los else ""                                    # 고른 글자에 바로 준 서식은 GREP 스타일 위에(인디자인 로컬 서식)
            return f'<span style="{st}{lo}">{t}</span>' if (st or lo) else t
        out, stack, los = [], [], []                                       # 윗주·옆 메모(data-ruby · data-side) 안 글은 건너뛴다 — 인디자인도 다른 글(고정 개체·윗주)
        head = True                                                        # 문단 첫머리인가 — 「^」 는 문단 처음에서만 맞는다(인디자인). 꾸밈 조각마다 글이
        for p in _TAG.split(html):                                         # 끊겨도 조각 첫머리에서 맞으면 안 된다(문장 가운데 「12 young」 에 번호 배지, 2026-10-11)
            if p.startswith("<"):
                inside = bool(stack and stack[-1])
                if p.startswith("</"):
                    stack and stack.pop()
                    los and los.pop()
                elif not p.endswith("/>"):
                    inn = "data-ruby=" in p or "data-side=" in p or "data-anc=" in p     # 윗주 · 고정 개체 안 글은 다른 글
                    stack.append(stack[-1] if stack else inn)
                    stack[-1] = stack[-1] or inn
                    mlo = re.search(r'data-lo="([^"]*)"', p)
                    los.append(_unescape(mlo.group(1)) if mlo else (los[-1] if los else ""))
                if not inside and re.match(r"</?(?:p|div)\b|<br\s*/?>", p):
                    head = True
                out.append(p)
                continue
            raw = _unescape(p)
            if not raw or (stack and stack[-1]):
                out.append(p)
                continue
            lead = "" if head else "\0"                                    # 문단 첫머리가 아니면 앞에 글자 하나를 대 「^」 가 못 맞게
            head = False
            if not rx.search(lead + raw):
                out.append(p)
                continue
            k = 0
            for m in rx.finditer(lead + raw):
                s, e = m.start() - len(lead), m.end() - len(lead)
                if e == s or s < 0:
                    continue
                out.append(esc(raw[k:s]) + wrap(m))
                k = e
            out.append(esc(raw[k:]))
        html = "".join(out)
    return html


FIXED_SPACES = {"\u2003": 1.0, "\u2002": 0.5, "\u2004": 1 / 3, "\u2005": 0.25, "\u2006": 1 / 6, "\u2009": 0.125, "\u200a": 1 / 24}   # 엠 · 엔 · 1/3 · 1/4 · 1/6 · 가는 · 아주 가는 공백


def fixed_spaces(html):
    """인디자인 고정 폭 공백 — 글꼴 글리프가 아니라 정해진 em 폭(엠 1 · 엔 1/2 · 가는 1/8 · 아주 가는 1/24 …)"""
    if not any(c in html for c in FIXED_SPACES):
        return html
    return "".join(p if p.startswith("<") else re.sub("[" + "".join(FIXED_SPACES) + "]",
                                                       lambda m: f'<span style="display:inline-block;width:{FIXED_SPACES[m.group(0)]:.4f}em"></span>', p)
                   for p in _TAG.split(html))


def keep_spaces(html):
    """연속 공백을 지킨다 — HTML 은 공백 여럿을 하나로 줄이지만 인디자인은 친 만큼 띄운다.
    두 번째 공백부터 줄 안 바뀜 공백(&#160;)으로 — 첫 공백에서는 그대로 줄이 바뀔 수 있다.
    글(단락) 끝 공백도 지킨다 — 브라우저는 버리지만 인디자인은 남기고, 그 공백을 보고 끝 글자의 문맥 대체 글자를 고른다(영도체 숫자 「01 」).
    글(단락) 첫 공백도 — 인디자인은 친 자리만큼 띄우고 시작한다(배열 조각 「 on / was found」, 단위 12)."""
    html = "".join(p if p.startswith("<") else re.sub(r" {2,}", lambda m: " " + "&#160;" * (len(m.group(0)) - 1), p)
                   for p in _TAG.split(html))
    html = re.sub(r"(^|<br/>)((?:<[^/>][^>]*>)*) ", r"\1\2&#160;", html)
    return re.sub(r" ((?:&#160;)*)(?=(?:</[a-z]+>)*(?:<br/>|$))", r"&#160;\1", html)


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
    ul = []                                                               # 열린 span 마다 밑줄인가 — 밑줄 안 공백만의 조각은 크롬이 밑줄을 안 긋는다(공백을 지키면 긋는다 · 줄 바꿈은 바깥 그대로)
    span = lambda t: (f'<span lang="{esc(lang)}" style="white-space-collapse:preserve">{t}</span>' if any(ul) and not t.replace("&#160;", "").strip()
                      else f'<span lang="{esc(lang)}">{t}</span>')

    def wrap(m):
        t = m.group(0)
        if t.startswith("&"):                                             # &#160; &quot; &amp; … — 글자 하나로 보고
            return span(t) if _unescape(t) in only else t
        return run.sub(lambda k: span(k.group(0)), t)
    out = []
    for p in _TAG.split(html):
        if p.startswith("</span"):
            if ul:
                ul.pop()
        elif p.startswith("<span"):
            ul.append("text-decoration:underline" in p)
        out.append(p if p.startswith("<") else _LOCL_RUN.sub(wrap, p))
    return "".join(out)


def ko_glyphs(html, a, ctx):
    """글 언어(a.lang, 기본 한국어)의 공백·문장부호 글리프 — locl_html."""
    if not ctx:
        return html
    return locl_html(html, ctx.font(a.get("font")), text_lang(a))


JC_DEFAULT = (80, 133, 0, 0, 1, 20, 0)  # 낱말 최소·최대 % · 자간 최소·최대 ‰ · 줄이기 비용 · 줄 비용 · 끝 줄 자간 최소 ‰ (units_compose.js)
# 기본 = 인디자인 공장 기본 「균등 배치」(낱말 80·100·133%, 자간 0·0·0). 책마다 다른 범위는 글상자 jc(word_min·word_max·letter_min·letter_max)로.
# 비용식(줄이기 비용 1 · 줄 비용 20 · 늘림 제곱)은 공통 — 인디자인 원본 5권(d1·d2·화이트북·세서특필·분석)으로 확인(scratch justify-analysis/beval2.py).
# 이 출판사 책 5권은 모두 같은 범위: 낱말 100·133%, 자간 최소 약 −5‰, 자간 늘림 큼 → jc 「100,133,-8,250」.


def jc_spec(a, space_em=0.25):
    """균등 배치(인디자인 단락 「균등 배치」) → 컴포저 data-jc. 단어 간격 최소 · 최대 %(공백 폭 기준), 문자 간격 최소 · 최대 %(공백 폭 기준 — 컴포저는 ‰ em 으로 받는다).
    텍스트 프레임 jc 가 있으면 그 값, 없으면 기본. 끝 줄도 문자 간격 최소까지만 줄인다(인디자인)."""
    j = a.get("jc") or {}
    v = list(JC_DEFAULT)
    for i, k in ((0, "word_min"), (1, "word_max")):
        if j.get(k) is not None:
            v[i] = j[k]
    for i, k in ((2, "letter_min"), (3, "letter_max")):
        if j.get(k) is not None:
            v[i] = round(float(j[k]) * space_em * 10, 3)               # % of 공백 → ‰ em
    v[6] = v[2]
    return ",".join(f"{x:g}" for x in v)


def soft_breaks(x, justify=False, jc=None):
    """줄 나눔(U+2028, Shift+Enter) — 문단은 그대로 두고 그 자리에서 줄만 꺾는다(인디자인 강제 줄바꿈).
    양끝맞춤이면 꺾인 앞줄도 양끝을 맞춘다(인디자인과 같다). 조각마다 열린 태그를 닫았다 다시 연다.
    jc — 단락 컴포저 설정(data-jc): 조각마다 컴포저가 줄 끝을 고른다(인디자인은 강제 줄바꿈이 있어도 단락 컴포저로 짠다)."""
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
    dj = f' data-jc="{jc}"' if jc else ""
    return "".join(f'<span style="display:block;{"text-align-last:justify;" if justify and i < last else ""}{"text-indent:0;" if i else ""}"{dj}>'
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
    """자동 크기 조정(인디자인 텍스트 프레임 옵션) — "off" 끔(기본) · "height" 높이만 · "width" 너비만 · "both" 높이 및 너비.
    기준점(auto_ref: tl t tr l c r bl b br)이 자라는 쪽을 정한다 — 위면 아래로, 아래면 위로, 가운데면 양쪽으로."""
    v = a.get("auto_size")
    return v if v in ("height", "width", "both") else "off"


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


def align_css(v):
    """인디자인 단락 정렬 → CSS — 왼쪽 · 가운데 · 오른쪽 정렬, 양쪽 정렬(마지막 줄 왼쪽 · 가운데 · 오른쪽), 모두 정렬"""
    last = {"justify": "left", "justify_center": "center", "justify_right": "right", "justify_all": "justify"}.get(v)
    if last:
        return f"text-align:justify;text-align-last:{last};"
    return f"text-align:{v if v in ('left', 'center', 'right') else 'left'};"


AUTO_LEAD = 1.2          # 자동 행간 — 글자 크기의 120%(인디자인 기본, 2026-10-14 전엔 145%)
ROMAN_EM = 0.47          # 로마자 한 글자 폭 어림 (기준 책 실측 0.455 — 본문 서체마다 조금 다르다)


def text_h(plain, w_mm, size_pt, leading_pt=None, a=None):
    """글이 차지할 높이(mm) 어림 — 한글·한자는 1em, 로마자는 ROMAN_EM. 자간·들여쓰기·여백·다단·단락 간격을 넣는다."""
    a = a or {}
    tb = a.get("table")
    if tb:                                                             # 표 — 줄마다 그 줄에서 가장 긴 칸(최소 높이 이상), 줄 사이 간격
        it, ir, ib, il = insets(a)
        cols = max(int(tb.get("cols") or 1), 1)
        gx, gy = float(tb.get("gap_x") or 0), float(tb.get("gap_y") or 0)
        cw = (w_mm - il - ir - gx * (cols - 1)) / cols
        ca = {k: v for k, v in a.items() if k not in ("table", "inset", "columns")}
        if tb.get("inset") is not None:
            ca["inset"] = tb["inset"]
        cells = (plain or "").split(CELL_SEP)
        rows = [cells[k:k + cols] for k in range(0, len(cells), cols)]
        return (sum(max(float(tb.get("row_h") or 0), max(text_h(c, cw, size_pt, leading_pt, ca) for c in r)) for r in rows)
                + gy * max(len(rows) - 1, 0) + it + ib)
    em = size_pt * PT
    lead = (leading_pt or size_pt * AUTO_LEAD) * PT
    it, ir, ib, il = insets(a)
    cols = max(int(a.get("columns") or 1), 1)
    gutter = float(a.get("gutter") or 0) if cols > 1 else 0.0
    col_w = (w_mm - il - ir - gutter * (cols - 1)) / cols - float(a.get("indent") or 0) - float(a.get("indent_right") or 0)
    track = em * float(a.get("tracking") or 0) / 1000.0
    tsume = em * float(a.get("tsume") or 0) / 100.0 * 0.13             # 자간 축소 — 글자 양옆 빈 곳 어림 0.13em(Noto CJK 한글 0.10~0.16)
    hs = hangul_scale(a.get("font"), a.get("weight"))                # 한글 폭 — 서체가 좁으면 그만큼(Noto 기준 어림)
    lines = 0
    paras = (plain or "").replace(" ", "\n").split("\n")             # 줄 나눔도 줄 하나
    first = float(a.get("indent_first") or 0)                          # 첫 줄 들여쓰기(음수 = 내어쓰기 — 첫 줄이 그만큼 넓다, 단위 14c 한 줄 발문이 두 줄로 어림됐다)
    for para in paras:
        width = first + sum(em * (hs if ord(c) > 0x2E7F else 0.28 if c == " " else ROMAN_EM) + track - (tsume if c != " " else 0) for c in para)   # 공백 0.28em(Noto CJK 한국어 꼴)
        lines += max(1, int(math.ceil(width / max(col_w, 0.1))))
    gaps = (len(paras) - 1) * (float(a.get("space_before") or 0) + float(a.get("space_after") or 0))
    return math.ceil(lines / float(cols)) * lead + gaps + it + ib


def story_h(ctx, a, v):
    """한 줄기 여러 자리 글(content.story_value — 문단마다 자리 표시 ps)의 높이 어림 — 문단마다 그 자리 단락 스타일(서체 · 크기 · 행간 · 자간 ·
    들여쓰기)로 세고, 문단 사이는 앞 · 뒤 간격(같은 자리끼리는 「같은 스타일 사이 간격」). 자리 표시가 없는 값이면 None(보통 어림을 쓴다)"""
    if not (isinstance(v, list) and any(isinstance(x, dict) and "ps" in x and not x.get("inline") for x in v)):
        return None
    paras, cur = [], None
    for x in v:
        if isinstance(x, dict) and "ps" in x and not x.get("inline"):
            cur = [x["ps"], "", {k: float(x["ov"][k]) for k in OV_KEYS if isinstance(x.get("ov"), dict) and x["ov"].get(k) is not None}]   # 재정의
            paras.append(cur)
            continue
        if x == "\n":
            continue
        if cur is None:
            cur = [None, "", {}]
            paras.append(cur)
        cur[1] += x.get("t", "") if isinstance(x, dict) and "ps" in x else rich_plain(x)
    it, ir, ib, il = insets(a)
    h, prev, pov = it + ib, None, {}
    for slot, t, ov in paras:
        st = dict(slot_style(a, slot, ctx) if slot else {}, **ov)
        aa = {k: v2 for k, v2 in a.items() if k not in ("inset", "space_before", "space_after", "table", "columns")}
        aa.update({k: st[k] for k in ("font", "weight", "size", "leading", "tracking", "indent", "indent_right", "indent_first", "tsume") if st.get(k) not in (None, "")})
        h += text_h(t, float(a["w"]) - il - ir, float(aa.get("size") or a["size"]), aa.get("leading"), aa)
        if prev is not None:
            if prev == slot and st.get("space_same") is not None:
                h += float(st["space_same"])
            else:
                h += float(st.get("space_before") or 0) + float(dict(slot_style(a, prev, ctx) if prev else {}, **pov).get("space_after") or 0)
        prev, pov = slot, ov
    return h


def text_end(plain, w_mm, size_pt, a=None):
    """글이 끝나는 가로 자리(mm) — 마지막 줄의 끝. 문장 끝에 붙는 개체(인디자인 앵커 개체)가 쓴다.

    text_h 와 같은 어림(한글 1em · 로마자 ROMAN_EM)을 쓴다. 줄이 넘어가면 마지막 줄만 센다.
    """
    a = a or {}
    em = size_pt * PT
    it, ir, ib, il = insets(a)
    track = em * float(a.get("tracking") or 0) / 1000.0
    col_w = max(w_mm - il - ir - float(a.get("indent") or 0) - float(a.get("indent_right") or 0), 0.1)
    hs = hangul_scale(a.get("font"), a.get("weight"))
    last = 0.0
    for para in (plain or "").split("\n"):
        run = 0.0
        for c in para:
            cw = em * (hs if ord(c) > 0x2E7F else ROMAN_EM) + track
            if run + cw > col_w:
                run = cw                      # 줄바꿈 — 새 줄에서 다시
            else:
                run += cw
        last = run
    return il + last


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
    if a.get("case") in ("upper", "small"):                              # 모두 대문자 · 작은 대문자
        css += "text-transform:uppercase;" if a["case"] == "upper" else "font-variant:small-caps;"
    return css


def _wrap_floats(ctx, a, h):
    """텍스트 감싸기 — 이 글상자와 겹치는 「감싸기」 원자만큼 자리를 비운다(인디자인 텍스트 감싸기, 사각형)."""
    out = ""
    for w in (getattr(ctx, "wrappers", None) or []):
        if w.get("id") is a:
            continue
        o = w.get("o") or {}
        off = float(w.get("offset") or 0)
        ot, ob, ol, orr = (float(o.get(k)) if o.get(k) is not None else off for k in ("t", "b", "l", "r"))   # 오프셋 위쪽 · 아래쪽 · 왼쪽 · 오른쪽
        x0, y0 = w["x"] - ol, w["y"] - ot
        x1, y1 = w["x"] + w["w"] + orr, w["y"] + w["h"] + ob
        tx0, ty0, tx1, ty1 = a["x"], a["y"], a["x"] + a["w"], a["y"] + h
        if x1 <= tx0 or x0 >= tx1 or y1 <= ty0 or y0 >= ty1:
            continue                                              # 안 겹친다
        to = w.get("to") or "largest"                                  # 감싸기 옵션 — 글이 흐를 쪽: 오른쪽 · 왼쪽 · 가장 큰 영역
        side = "left" if to == "right" else "right" if to == "left" else ("left" if (x0 - tx0) < (tx1 - x1) else "right")
        ww = (x1 - tx0) if side == "left" else (tx1 - x0)
        hh = y1 - ty0
        if ww <= 0 or hh <= 0:
            continue
        mt = max(0.0, y0 - ty0)
        out += (f'<div style="float:{side};width:{min(ww, a["w"]):.3f}px;height:{hh - mt:.3f}px;'
                f'margin-top:{mt:.3f}px;shape-outside:none"></div>')
    return out


def _tab_html(stops, para, start=0.0, indent=None):
    """탭 — 인디자인 탭 패널. 첫 줄의 탭으로 나뉜 조각을 탭 정지 자리(텍스트 프레임 안쪽 왼쪽에서 mm)에 세우고 채움 문자로 빈 곳을 채운다.
    start = 첫 줄 글 시작 자리(왼쪽 들여쓰기 + 첫 줄 들여쓰기). indent = 첫 줄 내어쓰기일 때 왼쪽 들여쓰기 자리(숨은 탭 정지, 인디자인).
    정지가 모자라면 기본 탭 정지(12.7mm 마다)로."""
    if "\t" not in para:
        return None
    segs = para.split("\t")
    st = sorted((dict(t) for t in (stops or []) if t.get("at") is not None), key=lambda t: float(t["at"]))
    if indent is not None and indent > start + 0.01 and not any(abs(float(t["at"]) - indent) < 0.01 for t in st):
        st = sorted(st + [{"at": indent}], key=lambda t: float(t["at"]))
    cols, cur = [], start
    for i, seg in enumerate(segs):
        if i == 0:
            cols.append((start, "left", "", seg))
            continue
        nxt = next((t for t in st if float(t["at"]) > cur + 0.01), None)
        if nxt is None:                                                # 기본 탭 정지
            at = (math.floor(cur / DEFAULT_TAB + 1e-6) + 1) * DEFAULT_TAB
            nxt = {"at": at}
        at = float(nxt["at"])
        cols.append((at, nxt.get("align") or "left", nxt.get("leader") or "", seg))
        cur = at
    out, open_ = "", None                                         # open_ = 왼쪽 맞춤 탭 앞 조각 [시작 자리, 글] — 다음 탭 자리까지 넓힌다
    for i, (at, al, leader, seg) in enumerate(cols):
        if i == 0:
            open_ = [start, seg]
            continue
        if al == "left" and not leader:                           # 왼쪽 탭 — 글이 탭 자리에서 시작한다(인디자인). 앞 조각을 그 자리까지 넓힌다
            out += f'<span style="display:inline-block;text-indent:0;min-width:{max(at - open_[0], 0):.3f}px">{open_[1]}</span>'   # 칸 안은 들여쓰기 없이(단락의 첫 줄 들여쓰기는 칸 자리에 이미 들었다)
            open_ = [at, seg]
            continue
        if open_ is not None:
            out += f'<span>{open_[1]}</span>'
            open_ = None
        prev_at = cols[i - 1][0]
        w = max(at - prev_at, 0.5)
        just = {"left": "flex-start", "center": "center", "right": "flex-end", "decimal": "flex-end"}[al]
        lead = ""
        if leader:
            lead = (f'<span style="flex:1;overflow:hidden;white-space:nowrap">'
                    + (esc(leader) * 80) + "</span>")
        out += (f'<span style="display:inline-flex;text-indent:0;min-width:{w:.3f}px;justify-content:{just};align-items:baseline">'
                f'{lead}<span>{seg}</span></span>')
    if open_ is not None:                                         # 끝 조각
        out += f'<span>{open_[1]}</span>'
    return out


DEFAULT_TAB = 12.7                                                # 인디자인 기본 탭 정지 — 0.5인치


_PS_RE = re.compile(r'<span data-ps="([^"]*)"(?: data-ov="([^"]*)")?( data-v0="1")?></span>')
OV_KEYS = ("space_before", "space_after", "space_same", "indent", "indent_first", "indent_right", "leading")   # 재정의 칸 — 단락 스타일의 같은 이름 값을 그 문단에서만 바꾼다


def _ov_of(x):
    """문단 html 첫머리 표시의 재정의 값 → dict (없으면 {})"""
    m = _PS_RE.search(x or "")
    if not (m and m.group(2)):
        return {}
    try:
        return {k: float(v) for k, v in json.loads(_unescape(m.group(2))).items() if k in OV_KEYS}
    except (ValueError, TypeError):
        return {}


_PSI_RE = re.compile(r'<span data-psi="([^"]*)">')
_PS_LEAD_RE = re.compile(r'<span data-ps="[^"]*"(?: data-ov="[^"]*")?(?: data-v0="1")?></span>'
                         r'(?:<span data-psi="[^"]*"[^>]*>[^<]*</span>[\t      ]*)*')   # 문단 첫머리 + 같은 단락에 이어 쓰는 필드들(+ 필드 뒤 공백 문자만 — 다음 글까지 먹으면 글머리 기호가 첫 낱말 뒤에 붙었다)
# 단락 값(인디자인 단락 패널 · 단락 스타일) — 텍스트 프레임에 두면 그 프레임 모든 단락의 값, 단락 스타일이 그 위에, 재정의가 또 그 위에
PARA_ATTRS = ("indent", "indent_first", "indent_right", "space_before", "space_after", "space_same", "align",
              "shade", "shade_fit", "shade_r", "shade_ot", "shade_ob", "shade_ol", "shade_or",
              "border", "border_color", "border_fit", "border_r", "border_ot", "border_ob", "border_ol", "border_or",
              "rule_above", "rule_below", "list", "tabs", "keep_next", "keep_together", "keep_first", "keep_last", "jc", "tsume")


def para_attrs(a, slot, ctx=None):
    """한 단락의 단락 값 — 텍스트 프레임 단락 값 위에 그 데이터 필드의 단락 스타일"""
    st = {k: a[k] for k in PARA_ATTRS if a.get(k) not in (None, "")}
    if slot:
        st.update(slot_style(a, slot, ctx))
    return st


def font_metrics(family, weight=400):
    """서체 높이들(em) — asc · desc(hhea, 크롬이 줄 상자를 잡는 값) · d(「d」 위 끝 = 인디자인 어센트) · cap(대문자 높이) · x(x 높이). 못 찾으면 어림"""
    key = ("m", family, int(weight or 400))
    if key not in _ASC:
        m = {"asc": 0.88, "desc": 0.12, "d": 0.72, "cap": 0.7, "x": 0.5, "space": 0.25}
        try:
            from core.units.fonts import system_fonts
            fs = [f for f in system_fonts() if f["family"] == family and not f["italic"]]
            f = next((f for f in fs if f["weight"] == key[2]), None) or (fs[0] if fs else None)
            if f:
                from fontTools.ttLib import TTFont
                from fontTools.pens.boundsPen import BoundsPen
                t = TTFont(f["path"], lazy=True, fontNumber=0)
                upm = t["head"].unitsPerEm
                m["asc"], m["desc"] = t["hhea"].ascent / upm, -t["hhea"].descent / upm
                gs, cmap = t.getGlyphSet(), t.getBestCmap()

                def top(ch):
                    g = cmap.get(ord(ch))
                    if not g:
                        return None
                    bp = BoundsPen(gs)
                    gs[g].draw(bp)
                    return bp.bounds[3] / upm if bp.bounds else None
                m["d"] = top("d") or m["d"]
                sp = cmap.get(32)
                if sp:
                    m["space"] = t["hmtx"][sp][0] / upm                 # 공백 폭 — 균등 배치 문자 간격 % 의 기준
                os2 = t["OS/2"] if "OS/2" in t else None
                m["cap"] = max(0, getattr(os2, "sCapHeight", 0) or 0) / upm or top("H") or m["cap"]   # −1 은 「모름」(하늘보리체) — 글자에서 잰다
                m["x"] = max(0, getattr(os2, "sxHeight", 0) or 0) / upm or top("x") or m["x"]
        except Exception:
            pass
        _ASC[key] = m
    return _ASC[key]


def _after(v):
    """텍스트 뒤 · 필드 뒤 글자 — 없으면 탭(인디자인 기본 ^t), "none" 이면 없음"""
    return "\t" if v is None else ("" if v == "none" else str(v))


def _list_text(st, ctx, a):
    """글머리 기호 및 번호 매기기(인디자인) — 단락 앞에 붙는 글(기호 · 번호 + 텍스트 뒤). 번호는 같은 목록(단락 스타일)끼리 이어 센다"""
    ls = st.get("list") or {}
    if ls.get("type") == "bullet":
        return esc(ls.get("char") or "•") + esc(_after(ls.get("after")))
    if ls.get("type") == "number":
        key = (id(a), ls.get("name") or "")
        nums = ctx.nums if ctx is not None else {}
        n = nums.get(key)
        n = int(ls.get("start") or 1) if (n is None or ls.get("restart")) else n + 1
        nums[key] = n
        f = ls.get("format") or "1."
        core = num_text(n, f.rstrip(".)") or "1")
        lead_ = "(" if f.startswith("(") else ""
        trail = "." if f.endswith(".") else ")" if f.endswith(")") and not f.startswith("(") else ")" if f.startswith("(") else ""
        return esc(lead_ + core + trail) + esc(_after(ls.get("after")))
    return ""


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
        css += f"line-height:{float(st.get('leading') or float(st['size']) * AUTO_LEAD) * PT:.3f}px;"
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


def _para_font(a, st, ctx):
    """단락 글꼴 · 크기 · 행간(mm) — 단락 스타일 값, 없으면 텍스트 프레임 값"""
    fam = st.get("font") or a.get("font") or ""
    if ctx is not None and str(fam).startswith("$"):
        fam = ctx._tok(fam, "font", "")
    size = float(st.get("size") or a.get("size") or 9)
    lead = float(st.get("leading") or a.get("leading") or size * AUTO_LEAD)
    return fam, int(st.get("weight") or a.get("weight") or 400), size, lead


def _line_metrics(a, st, ctx):
    """단락 첫 줄 위 끝 → 기준선, 끝 줄 기준선 → 아래 끝(mm) — 크롬 줄 상자(행간 반씩 위아래)"""
    fam, wt, size, lead = _para_font(a, st, ctx)
    m = font_metrics(fam, wt)
    S, L = size * PT, lead * PT
    half = (L - (m["asc"] + m["desc"]) * S) / 2
    return half + m["asc"] * S, half + m["desc"] * S, m, S, L


def _para(a, x, slot, slots, k, ctx, ovs=None, v0=None):
    """단락 하나(인디자인 단락) — 텍스트 프레임 단락 값 + 그 데이터 필드의 단락 스타일 + 재정의를 입힌 <p>.
    들여쓰기 · 단락 앞뒤 공백(더한다) · 동일한 스타일 단락 사이 간격 · 정렬 · 단락 음영 · 단락 테두리(잇닿은 같은 값 문단은 한 상자) ·
    단락 경계선 · 글머리 기호 및 번호 매기기 · 탭 · 분리 금지 옵션 · 균등 배치 · 고정 개체(데이터 필드 앞 · 뒤)."""
    n = len(slots)
    st = dict(para_attrs(a, slot, ctx), **((ovs or {}).get(k) or {}))
    css = "margin:0;" + _font_css(st, ctx)
    if st.get("align"):
        css += align_css(st["align"])
    look = lambda j: dict(para_attrs(a, slots[j], ctx), **((ovs or {}).get(j) or {})) if 0 <= j < n else None

    def grp(j):
        q = look(j)
        if not q or not (q.get("shade") or q.get("border")):
            return None
        return tuple(q.get(key) for key in ("shade", "shade_fit", "shade_r", "border", "border_color", "border_fit"))
    g0 = grp(k)
    first = not (g0 and grp(k - 1) == g0)
    last = not (g0 and grp(k + 1) == g0)
    ind, ind_r, indf = float(st.get("indent") or 0), float(st.get("indent_right") or 0), float(st.get("indent_first") or 0)
    shade, border = st.get("shade"), float(st.get("border") or 0)
    fit = bool((shade and st.get("shade_fit")) or (not shade and border and st.get("border_fit")))
    if fit:                                                            # 음영 · 테두리 너비 「텍스트」 — 문단 상자를 글 폭으로(들여쓰기는 바깥 여백)
        css += f"margin-left:{ind:.3f}px;margin-right:{ind_r:.3f}px;width:fit-content;max-width:calc(100% - {ind + ind_r:.3f}px);box-sizing:border-box;"
    else:
        if ind:
            css += f"padding-left:{ind:.3f}px;"
        if ind_r:
            css += f"padding-right:{ind_r:.3f}px;"
    if st.get("indent_first") is not None:
        css += f"text-indent:{indf:.3f}px;"
    # 단락 사이 = 앞 단락 「단락 뒤 공백」 + 이 단락 「단락 앞 공백」(인디자인은 더한다), 같은 스타일끼리는 「동일한 스타일 단락 사이 간격」이 있으면 그것
    prev = look(k - 1) if k else {}
    if k and slots[k - 1] == slot and st.get("space_same") is not None:
        gap = float(st["space_same"])
    else:
        gap = float(st.get("space_before") or 0) + float((prev or {}).get("space_after") or 0)
    if k and gap:
        css += f"margin-top:{gap:.3f}px;"
    deco = ""
    pl, pr = (ind, ind_r) if fit else (0.0, 0.0)                       # 문단 상자 바깥 여백 — 「열」 너비 장식은 단 가장자리에서
    il_frame = insets(a)[3]
    if shade or border or st.get("rule_above") or st.get("rule_below"):
        css += f"position:relative;z-index:0;--ax:{il_frame + pl:.3f}px;"   # 사용자 정의 고정 개체의 「텍스트 프레임 가장자리」 기준을 지킨다
    col = lambda c, d="#231f20": (ctx.color(c, d) if ctx else (c or d))

    def box(prefix, fitw):
        ot, ob = float(st.get(prefix + "_ot") or 0), float(st.get(prefix + "_ob") or 0)
        ol, orr = float(st.get(prefix + "_ol") or 0), float(st.get(prefix + "_or") or 0)
        top = ot if first else (gap if k else 0)                         # 잇닿은 상자 — 사이 간격도 칠한다
        bot = ob if last else 0
        left = ((0.0 if fit else ind) if fitw else -pl) - ol             # 너비 「텍스트」 = 글 왼쪽 끝에서, 「열」 = 단 가장자리에서
        right = ((0.0 if fit else ind_r) if fitw else -pr) - orr
        return f"position:absolute;z-index:-1;left:{left:.3f}px;right:{right:.3f}px;top:{-top:.3f}px;bottom:{-bot:.3f}px;"
    if shade:                                                          # 단락 음영 — 글 뒤에 깔릴 뿐 글 자리를 바꾸지 않는다
        sc = box("shade", bool(st.get("shade_fit"))) + f"background-color:{col(shade)};"
        if st.get("shade_r"):
            r_ = float(st["shade_r"])
            sc += (f"border-top-left-radius:{r_ if first else 0:.3f}px;border-top-right-radius:{r_ if first else 0:.3f}px;"
                   f"border-bottom-left-radius:{r_ if last else 0:.3f}px;border-bottom-right-radius:{r_ if last else 0:.3f}px;")
        deco += f'<span data-shade="1" style="{sc}"></span>'
    if border:                                                         # 단락 테두리 — 음영과 따로(제 오프셋 · 너비 · 모퉁이)
        bw = f"{border * PT:.3f}px solid {col(st.get('border_color') or '$ink')}"
        bc = box("border", bool(st.get("border_fit"))) + "box-sizing:border-box;" + f"border-left:{bw};border-right:{bw};" + (f"border-top:{bw};" if first else "") + (f"border-bottom:{bw};" if last else "")
        if st.get("border_r"):
            r_ = float(st["border_r"])
            bc += (f"border-top-left-radius:{r_ if first else 0:.3f}px;border-top-right-radius:{r_ if first else 0:.3f}px;"
                   f"border-bottom-left-radius:{r_ if last else 0:.3f}px;border-bottom-right-radius:{r_ if last else 0:.3f}px;")
        deco += f'<span data-shade="1" style="{bc}"></span>'
    for key, up in (("rule_above", True), ("rule_below", False)):       # 단락 경계선 — 위: 첫 줄 기준선에서 경계선 아래 끝까지, 아래: 끝 줄 기준선에서 경계선 위 끝까지(글을 밀지 않는다)
        r = st.get(key)
        if not (isinstance(r, dict) and r.get("w")):
            continue
        w_ = float(r["w"]) * PT
        fb, lb, _, _, _ = _line_metrics(a, st, ctx)
        off = float(r.get("offset") or 0)
        txt = r.get("width") == "text"
        left = (ind - pl if txt else -pl) + float(r.get("il") or 0)
        right = (ind_r - pr if txt else -pr) + float(r.get("ir") or 0)
        v = f"top:{fb - off - w_:.3f}px;" if up else f"bottom:{lb - off - w_:.3f}px;"
        deco += f'<span data-shade="1" style="position:absolute;z-index:-1;left:{left:.3f}px;right:{right:.3f}px;{v}height:{w_:.3f}px;background:{col(r.get("color"), "#000000")}"></span>'
    attrs = f' data-slot="{esc(slot)}"' if slot else ""
    if st.get("keep_next"):
        attrs += ' data-keep-next="1"'                                # 다음 행과 함께 유지 — 단 · 페이지 끝에 혼자 남지 않는다(units_compose.js thread)
    if st.get("keep_together"):
        attrs += ' data-keep="1"'                                     # 행 분리 금지 — 단락의 모든 행
    if st.get("keep_first"):
        attrs += f' data-keep-first="{int(st["keep_first"])}"'       # 단락의 시작 · 끝 — 시작 N행
    if st.get("keep_last"):
        attrs += f' data-keep-last="{int(st["keep_last"])}"'         # 끝 N행
    if st.get("tsume"):
        attrs += f' data-tsume="{float(st["tsume"]):g}"'
    just = str(st.get("align") or a.get("align") or "").startswith("justify")
    spec = jc_spec(dict(a, jc=st["jc"]) if st.get("jc") else a, font_metrics(*_para_font(a, st, ctx)[:2])["space"]) if just and a.get("compose") is not False else None
    if spec and "\u2028" not in x:                                    # 강제 줄 바꿈이 있으면 나뉜 조각마다(soft_breaks)
        attrs += f' data-jc="{spec}"'
    fm = a.get("slot_fmt") or {}
    x = _PSI_RE.sub(lambda m: f'<span data-psi="{m.group(1)}" style="text-indent:0;{_psi_css(fm.get(m.group(1)) or {}, ctx)}">', x)
    lt = _list_text(st, ctx, a) if st.get("list") else ""
    if lt:                                                             # 글머리 기호 및 번호 매기기 — 같은 단락에 이어 쓰는 필드(번호) 뒤에
        m = _PS_LEAD_RE.search(x)
        x = (x[:m.end()] + lt + x[m.end():]) if m else lt + x
    # 고정 개체(데이터 필드에 붙인 것) — 템플릿 단락에서 필드 앞(start) · 뒤(end). 레코드 값 하나가 여러 단락이면 그 값의 첫 · 끝 단락에만
    anc = st.get("anc") or {}
    before_p = after_p = ""
    if anc and (anc.get("part") or anc.get("text") is not None):
        starts = (v0[k] if v0 and any(v0) else (k == 0 or slots[k - 1] != slot))
        ends = (k + 1 == n or slots[k + 1] != slot or bool(v0 and any(v0) and v0[k + 1]))
        at_start = anc.get("at") == "start"
        if (at_start and starts) or (not at_start and ends):
            if (anc.get("pos") or "inline") == "above":                # 줄 위 — 제 줄(단락)에 놓인다. 정렬 · 앞 공백 · 뒤 공백
                o = anchor_obj(anc, ctx, a)
                if o:
                    al = {"center": "center", "right": "right"}.get(anc.get("align"), "left")
                    line = (f'<p style="margin:0;padding-top:{float(anc.get("before") or 0):.3f}px;padding-bottom:{float(anc.get("after") or 0):.3f}px;'
                            f'line-height:0;{f"height:{o[2]:.3f}px;box-sizing:content-box;" if o[2] else ""}text-align:{al};text-indent:0;'   # 줄 높이 = 개체 높이(글자 받침 자리를 더하지 않는다)
                            f'padding-left:{float(anc["x"]) if anc.get("x") is not None else ind:.3f}px;padding-right:{ind_r:.3f}px">'
                            f'<span style="display:inline-block">{o[0]}</span></p>')
                    if at_start:
                        before_p = line
                    else:
                        after_p = line
            else:
                h_ = anchored_html(anc, ctx, a)
                if at_start:
                    m = _PS_LEAD_RE.search(x)
                    x = (x[:m.end()] + h_ + x[m.end():]) if m else h_ + x
                else:
                    x += h_
    if "\t" in x:                                                      # 탭 — 탭 정지(단락 값) · 숨은 정지(첫 줄 내어쓰기) · 기본 탭 정지
        x = _tab_html(st.get("tabs"), x, ind + indf, ind if indf < 0 else None) or x
    return before_p + f'<p style="{css}"{attrs}>{deco}{soft_breaks(x, just, spec) or "&#160;"}</p>' + after_p


def _psi_css(f, ctx):
    """같은 단락에 이어 쓰는 필드의 글자 — 문자 스타일, 고정 텍스트 프레임에 넣었으면(인디자인 인라인 고정 텍스트 프레임) 칠 · 모퉁이 크기 · 인세트"""
    css = (ctx.cstyle_css(f["cs"]) if (ctx and f.get("cs")) else "")
    fr = f.get("frame") or {}
    if fr.get("fill") or fr.get("stroke"):
        ins = [float(v) for v in (fr.get("inset") if isinstance(fr.get("inset"), list) else [fr.get("inset") or 0] * 4)]
        css += (f"display:inline-block;line-height:1;padding:{ins[0]:.3f}px {ins[1]:.3f}px {ins[2]:.3f}px {ins[3]:.3f}px;"
                f"background:{ctx.color(fr['fill']) if (ctx and fr.get('fill')) else fr.get('fill') or 'transparent'};")
        if fr.get("r"):
            css += f"border-radius:{float(fr['r']):.3f}px;"
        if fr.get("y"):
            css += f"vertical-align:{float(fr['y']):.3f}px;"           # 인라인 고정 개체 Y 오프셋 — 위가 +
    return css


def _paras_html(a, html, ctx=None):
    """글 HTML → 단락(<p>)들. 단락마다 그 데이터 필드(한 줄기 여러 필드 — content.story_value 의 문단 표시) 또는 텍스트 프레임의 단락 값"""
    paras = (html or "").split("<br/>")
    ms = [_PS_RE.search(x) for x in paras]
    slots = [m.group(1) if m else None for m in ms]
    v0 = [bool(m and m.group(3)) for m in ms]
    ovs = {k: _ov_of(x) for k, x in enumerate(paras)}
    return "".join(_para(a, x, s_, slots, k, ctx, ovs, v0) for k, (x, s_) in enumerate(zip(paras, slots)))


def _first_baseline(a, html, ctx):
    """첫 번째 기준선 오프셋(인디자인 텍스트 프레임 옵션) — 첫 줄 기준선을 인세트 위 끝에서 어센트(「d」 높이) · 대문자 높이 · 행간 · x 높이 · 고정 만큼 아래에.
    최소를 주면 그보다 위로는 안 올린다. → 크롬이 그린 첫 줄 기준선과의 차이(mm, 상자 위 여백에 더한다)"""
    fb = a.get("fbo") or {}
    if a.get("valign") not in (None, "", "top"):                        # 가운데 · 아래쪽 · 양쪽 — 글 덩어리를 프레임 안에서 맞춘다
        return 0.0, 0.0
    m0 = _PS_RE.search((html or "").split("<br/>")[0] or "")
    b0 = str(a.get("bind") or "").split("+")[0] if (a.get("bind") and "+" in str(a.get("bind")) and not m0) else None   # 자리 표시자 글 — 첫 데이터 필드의 단락 스타일로
    st = para_attrs(a, m0.group(1) if m0 else b0, ctx)
    natural, _, m, S, L = _line_metrics(a, st, ctx)
    kind = fb.get("type") or "ascent"
    want = {"ascent": m["d"] * S, "cap": m["cap"] * S, "x": m["x"] * S, "leading": L, "fixed": float(fb.get("min") or 0)}.get(kind, m["d"] * S)
    if kind != "fixed" and fb.get("min") is not None:
        want = max(want, float(fb["min"]))
    return want - natural, natural


def _text_html(a, html, h, ctx=None):
    """텍스트 프레임 안 HTML — 단락은 _para, 프레임엔 인세트 · 세로 균등 배치 · 단 · 첫 번째 기준선 오프셋 · 가로 · 세로 비율."""
    dc = None if a.get("table") else a.get("drop_cap")
    if dc and int(dc.get("lines") or 0) >= 2:                          # 드롭 캡 — 첫 단락 첫 글자(들)을 줄 수만큼 크게
        paras = (html or "").split("<br/>")
        m = _PS_LEAD_RE.match(paras[0]) if paras else None
        pre, body = (paras[0][:m.end()], paras[0][m.end():]) if m else ("", paras[0] if paras else "")
        nch = int(dc.get("chars") or 1)
        head, rest = body[:nch], body[nch:]
        if head and "<" not in head and "&" not in head:
            lines = int(dc["lines"])
            lead = (a.get("leading") or float(a.get("size") or 9) * AUTO_LEAD) * PT
            cap = (f'<span style="float:left;font-size:{lead * lines * 0.86:.3f}px;line-height:{lead * lines:.3f}px;'
                   f'margin-right:{lead * 0.12:.3f}px">{head}</span>')
            paras[0] = pre + cap + rest
            html = "<br/>".join(paras)
    inner = _table_html(a, html, ctx) if a.get("table") else _paras_html(a, html, ctx)
    it, ir, ib, il = insets(a)
    sh = 0.0
    if not a.get("table"):
        sh, nat = _first_baseline(a, html, ctx)                      # 첫 번째 기준선 오프셋 — 첫 줄을 올리거나 내린다(인세트는 그대로)
        if a.get("_snap"):                                            # 기준선 격자에 정렬 — 첫 줄 기준선을 다음 격자 줄에
            start, step, top = a["_snap"]
            b0 = top + it + sh + nat
            sh += start + math.ceil((b0 - start) / step - 0.001) * step - b0
    cols = int(a.get("columns") or 1)
    if abs(sh) > 0.0005 and cols <= 1:
        inner = f'<div style="margin-top:{sh:.3f}px">{inner}</div>'     # 여러 단이면 단 묶음째 옮긴다(아래) — 단마다 첫 줄이 같은 기준선
    box = f"height:{h:.3f}px;box-sizing:border-box;padding:{it:.3f}px {ir:.3f}px {ib:.3f}px {il:.3f}px;display:flow-root;"
    fr, mode = a.get("frame") or {}, auto_size(a)
    if fr and mode != "off" and not a.get("story"):                   # 글 잇기 상자는 높이를 지킨다(넘친 줄을 다음 상자로)
        box = box.replace(f"height:{h:.3f}px;", "")                   # 바탕이 있으면 브라우저가 실제로 그린 글 높이 + 여백만큼(인디자인 자동 크기 조정 — 줄기도 한다)
    if mode in ("width", "both"):                                     # 너비만 · 높이 및 너비 — 글 폭 + 인세트만큼(줄을 바꾸지 않는다), 기준점 쪽을 지킨다
        ref = str(a.get("auto_ref") or "tl")
        box += "width:max-content;white-space:nowrap;"
        if ref[-1] == "r" or ref == "r":
            box += "position:relative;left:100%;transform:translateX(-100%);"
        elif ref in ("t", "c", "b"):
            box += "position:relative;left:50%;transform:translateX(-50%);"
    box += frame_css(fr, ctx)
    if a.get("valign") in ("center", "bottom", "justify"):              # 세로 균등 배치(인디자인 텍스트 프레임 옵션) — 가운데 · 아래쪽 · 양쪽(단락 사이를 벌린다)
        box += "display:flex;flex-direction:column;justify-content:" + {"center": "center", "bottom": "flex-end", "justify": "space-between"}[a["valign"]] + ";"
    if cols > 1:
        cr = a.get("column_rule")
        rule = ""
        if cr and cr.get("w"):
            rule = f";column-rule:{float(cr['w']) * PT:.3f}px solid {(ctx.color(cr.get('color'), '#000000') if ctx else (cr.get('color') or '#000000'))}"
        mt = sh if abs(sh) > 0.0005 else 0.0
        fill = "column-fill:balance" if a.get("col_balance") else f"column-fill:auto;height:{max(h - it - ib - mt, 1):.3f}px"   # 인디자인 기본 = 첫 단부터 상자 높이까지, 「단 균형 맞추기」를 켜면 단마다 같은 양(옛 col_seq 는 기본과 같다)
        inner = f'<div style="{f"margin-top:{mt:.3f}px;" if mt else ""}column-count:{cols};column-gap:{float(a.get("gutter") or 0):.3f}px;{fill}{rule}">{inner}</div>'
    hs, vs = float(a.get("h_scale") or 100), float(a.get("v_scale") or 100)
    if hs != 100 or vs != 100:                                   # 장평 — 글자는 늘리고 상자 폭은 지킨다
        inner = (f'<div style="width:{float(a["w"]) * 100.0 / hs:.3f}px;transform:scale({hs / 100.0:.4f},{vs / 100.0:.4f});'
                 f'transform-origin:0 0">{inner}</div>')
    if ctx is not None:
        inner = _wrap_floats(ctx, a, h) + inner                   # 감싸기 — 비울 자리를 먼저
    return f'<div style="{box}">{inner}</div>'


def _table_html(a, html, ctx=None):
    """텍스트 프레임 안 표(인디자인 표) — 칸이 왼쪽→오른쪽 · 위→아래(레코드만큼 행이 는다). 열 칠(교대 패턴) · 셀 인세트 · 행 높이 최소 · 셀 획.
    셀 획은 칸 경계 가운데(인디자인) — 칸 사이를 획 두께만큼 비우고 칸마다 바깥으로 반씩 그린다.
    행 높이는 그 행의 가장 긴 칸(같은 행 칸은 함께 늘어난다) — 브라우저가 그린 높이로 프레임이 자란다(units_compose grow)"""
    tb = a["table"]
    cols = max(int(tb.get("cols") or 1), 1)
    fills = tb.get("fills") or []
    t, r, b, l = insets({"inset": tb.get("inset")})
    rh = float(tb.get("row_h") or 0)
    sk = tb.get("stroke") or {}
    sw = float(sk.get("w") or 0) * PT
    rw = float(sk["row_w"]) * PT if sk.get("row_w") not in (None, "") else sw    # 행 획(행 사이) — 인디자인 표 옵션 > 행 획 · 열 획
    sc = (ctx.color(sk.get("color"), "#000000") if ctx else (sk.get("color") or "#000000")) if (sw or rw) else ""
    cells = []
    for k, c in enumerate((html or "").split(CELL)):
        body = _paras_html(a, c, ctx)                                  # 칸 안 단락 — 데이터 필드마다 단락 스타일
        f = fills[(k % cols) % len(fills)] if fills else None
        bg = f"background:{ctx.color(f) if ctx else f};" if f else ""
        if sw == rw:
            shadow = f"box-shadow:0 0 0 {sw / 2:.3f}px {sc};" if sw else ""
        else:                                                          # 행 · 열 획 두께가 다르면 칸 모양 그림자를 반 획씩 여덟 방향으로(번짐 하나로는 같은 두께뿐)
            hx, hy = sw / 2, rw / 2
            shadow = "box-shadow:" + ",".join(f"{dx:.3f}px {dy:.3f}px 0 0 {sc}" for dx in (-hx, 0, hx) for dy in (-hy, 0, hy) if dx or dy) + ";"
        cells.append(f'<div data-cell="{k}" style="{bg}{shadow}padding:{t:.3f}px {r:.3f}px {b:.3f}px {l:.3f}px;box-sizing:border-box;min-width:0;'
                     f'{f"min-height:{rh:.3f}px;" if rh else ""}">{body}</div>')
    return (f'<div style="display:grid;grid-template-columns:repeat({cols},minmax(0,1fr));gap:{rw:.3f}px {sw:.3f}px{";clip-path:inset(0)" if (sw or rw) else ""}">'   # 셀 사이 획만(표 바깥 테두리는 없다 — 바깥으로 나간 반쪽 획은 자른다)
            + "".join(cells) + "</div>")


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
    w = float(st.get("w") or 0.5)
    typ = st.get("type") or ("dashed" if st.get("dash") else "solid")    # 획 유형(인디자인) — 실선 · 파선(대시 · 간격 pt) · 점선(둥근 점)
    if typ == "dashed":
        s += ' stroke-dasharray="' + " ".join(f"{d * PT:.3f}" for d in (st.get("dash") or [w * 4, w * 2])) + '"'
    elif typ == "dotted":
        s += f' stroke-dasharray="0 {float(st.get("gap") or w * 2) * PT:.3f}" stroke-linecap="round"'
    if st.get("cap") in ("round", "square") and typ != "dotted":
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


CELL = '<div data-cell=""></div>'                      # 표 칸 나눔(그리기 HTML 안) — 글자 색 규칙이 문단 경계로 본다(칸 첫 줄에서 「^」 가 맞게)
CELL_SEP = "\x1e"                                       # 표 칸 나눔(높이 어림 글 안)


def table_cells(v):
    """표 칸 — 원고 값이 목록이면 하나가 한 칸, 글 하나면 빈 줄이 칸 나눔(인디자인 「텍스트를 표로」처럼 글에서 나눌 수도)"""
    if isinstance(v, list):
        return v
    if isinstance(v, str):
        return re.split(r"\n[ \t]*\n", v)
    return [v]


def _table_content(ctx, a, values):
    """표 글상자의 (html, plain) — 칸마다 원고 하나"""
    b = a.get("bind")
    v = values.get(b) if b else None
    if v is None and b and b.startswith("sys."):
        v = ctx.sys.get(b[4:])
    if v is None:
        v = a.get("text")
    if v is None:
        hint = " + ".join(_slot_label(x) for x in b.split("+")) if b else ""
        return f'<span style="color:#b0b0b0">‹{esc(hint)}›</span>', "‹" + hint + "›"
    cells = table_cells(v)
    if a.get("markup"):
        cells = [markup_runs(c) for c in cells]
    return CELL.join(rich_html(c, ctx) for c in cells), CELL_SEP.join(rich_plain(c) for c in cells)


def _text_content(ctx, a, values, types):
    """글 원자의 (html, plain). bind → 값 → 없으면 sys → 없으면 견본 글 → 없으면 {bind} 회색.

    번호 매기기(num)가 켜져 있으면 원고가 번호를 안 줘도 앞 번호 다음으로 저절로 매긴다.
    """
    b = a.get("bind")
    ctx.cur_atom = a                                                       # 조각의 윗주·옆 메모가 이 글상자 설정을 쓴다
    if a.get("table"):
        return _table_content(ctx, a, values)
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
                     "offset": (a.get("wrap") or {}).get("offset"), "o": {k: (a.get("wrap") or {}).get("o" + k) for k in "tblr"},
                     "to": (a.get("wrap") or {}).get("to")}
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
        html = ko_glyphs(keep_spaces(fixed_spaces(grep_html(html, a.get("grep"), ctx))), a, ctx)
        content[i] = html
        plains[i] = plain
        if a.get("story"):                                             # 첫 상자 — 자라지 않는다(넘침은 이어지는 상자가 받는다)
            continue
        need = story_h(ctx, a, values.get(a["bind"]) if a.get("bind") else None)    # 여러 자리 한 줄기 — 문단마다 그 자리 스타일로
        if need is None:
            need = text_h(plain, a["w"], a["size"], a.get("leading"), a)
        need = max(0.0, need + _first_baseline(a, html, ctx)[0])           # 첫 번째 기준선 오프셋만큼 첫 줄이 오르내린다
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
        lead = (t.get("leading") or t["size"] * AUTO_LEAD) * PT
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
        if a.get("t") == "image" and a.get("bind") and not str(a["bind"]).startswith("sys."):   # 그림 칸 원고 자리 — 값(그림 주소)이 있으면 그 그림, 없으면 빈 칸
            v = values.get(a["bind"])
            v = (v[0] if v else "") if isinstance(v, list) else v
            a = dict(a, _src=v if isinstance(v, str) and v.startswith(("data:image/", "http://", "https://", "/")) else "")
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
        lead = (a.get("leading") or a["size"] * AUTO_LEAD) * PT
        if a.get("snap_baseline") and getattr(ctx, "grid", None):
            step = float((ctx.grid or {}).get("step") or 0)
            if step > 0:
                lead = math.ceil(lead / step - 0.01) * step           # 행간을 격자 간격의 배수로
                start = float((ctx.grid or {}).get("start") or 0)
                off = float(getattr(ctx, "_item_y", 0) or 0)                       # 요소가 면 안에 놓인 자리
                a = dict(a, leading=lead / PT, _snap=(start, step, off + a["y"] + dy))   # 첫 줄 기준선을 격자 줄에(_text_html)
        style = (f"margin:0;font-family:{esc(ctx.font(a.get('font')))};font-size:{a['size'] * PT:.3f}px;"
                 f"line-height:{lead:.3f}px;color:{ctx.color(a.get('color'))};{align_css(a.get('align') or 'left')}"
                 f"word-break:break-word;white-space:normal")
        dm = 0.0                                                               # 단락 음영 · 테두리가 프레임 밖으로 나가는 만큼은 자르지 않는다(인디자인 — 「프레임에 클립」 꺼짐)
        for st_ in [a] + [slot_style(a, f, ctx) for f in (a.get("slot_fmt") or {})]:
            dm = max([dm] + [float(st_.get(k) or 0) for k in ("shade_ot", "shade_ob", "border_ot", "border_ob")])
        # 넘친 글만 자른다(아래 끝) — 위로는 첫 줄 글자가 프레임 위로 나와도 그린다(인디자인 — 첫 번째 기준선 「어센트」는 「d」 높이라 한글 · 대문자 윗부분이 위 끝을 넘는다),
        # 옆으로는 상자 밖까지(줄 끝 공백 밑줄이 단 끝을 넘는다). 단락 음영 · 테두리가 프레임 밖으로 나가는 만큼은 아래도 자르지 않는다(「프레임에 클립」 꺼짐)
        style += f";overflow:visible;clip-path:inset({-(a['size'] * PT + dm + 0.5):.3f}px -100000px {-(dm + 0.5) if dm else 0:.3f}px -100000px)"
        if a.get("tracking"):
            style += f";letter-spacing:{float(a['tracking']) / 1000.0:.4f}em"
            # 브라우저는 자간이 있으면 합자·문맥 대체 글자를 끈다 — 인디자인은 자간을 줘도 그대로 쓴다(fi 합자·영도체 이어지는 숫자)
            style += ";font-feature-settings:'liga' 1,'calt' 1"
        if a.get("kerning") == "none":
            style += ";font-kerning:none"
        if a.get("hyphenate"):
            style += ";hyphens:auto;-webkit-hyphens:auto"
        dec = _decor_css(a, ctx)
        if dec:
            style += ";" + dec
        if a.get("baseline"):
            style += f";position:relative;top:{-float(a['baseline']) * PT:.3f}px"
        if a.get("opsz"):                                                      # 광학 크기 — 가변 서체 opsz 축을 정한 값으로(자동 끔)
            style += f";font-optical-sizing:none;font-variation-settings:'opsz' {float(a['opsz']):g}"
        if a.get("weight"):                                                    # 굵기(100~900)가 굵게보다 먼저
            style += f";font-weight:{int(a['weight'])}"
        elif a.get("b"):
            style += ";font-weight:700"
        if a.get("i"):
            style += ";font-style:italic"
        # lang=en — 언어가 없으면 크롬이 한국어로 그려 Noto CJK 의 라틴 합자(ff·fi)가 꺼진다(인디자인은 쓴다). 글 언어(a.lang)의 공백·문장부호는 ko_glyphs 가 그 언어로 감쌌다
        # 글은 TEXT_ZOOM 배 해상도로 배치하고 그만큼 줄여 그린다 — 지면 1mm = CSS 1px 이라 브라우저가 줄 위치·글자 높이를
        # px 단위로 반올림하면 줄마다 최대 0.5mm 씩 어긋난다(행간 7.76mm 가 8·8·7·8mm 로). zoom 으로 반올림을 0.1mm 로.
        z = text_zoom(a, getattr(ctx, "zoom_out", 1))
        # 글 잇기 — 같은 이야기의 상자끼리 넘친 줄을 차례로 넘긴다(units_compose.js 의 thread)
        st = f' data-story="{esc(a["story"])}" data-seq="{story_seq(a)}"' if a.get("story") else ""
        if auto_size(a) != "off" and not a.get("story"):                       # 자동 크기 — 브라우저가 실제로 그린 글 높이로 상자를 다시 맞춘다(units_compose.js grow)
            st += f' data-grow="1" data-h0="{float(a["h"]):.3f}" data-hcur="{h:.3f}" data-tol="{below_tol(a):.3f}" data-ref="{esc(str(a.get("auto_ref") or "tl"))}" data-mode="{auto_size(a)}"'
            if a.get("bind") and not str(a["bind"]).startswith("sys."):          # 원고 자리 — 글 길이가 바뀌는 상자(틀 검사가 본다)
                st += f' data-slot="{esc(a["bind"])}"'
        elif a.get("bind") and not str(a["bind"]).startswith("sys.") and "+" not in str(a["bind"]):
            st += f' data-bind="{esc(a["bind"])}"'                             # 크기 고정 원고 자리(어휘 등) — 누른 자리를 알리는 지면(analysis_edit)만 본다
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
        if "_src" in a:                                         # 원고 그림(자리 값) — 맞춤 · 기준점대로, 틀 밖은 자른다
            if not a["_src"]:
                return ""
            cid = ctx.uid()
            par = _fit_align(a) + (" slice" if a.get("fit") == "cover" else " meet")
            return (f'<clipPath id="{cid}"><rect x="{a["x"]}" y="{a["y"] + dy:.3f}" width="{a["w"]}" height="{h:.3f}"/></clipPath>'
                    f'<image x="{a["x"]}" y="{a["y"] + dy:.3f}" width="{a["w"]}" height="{h:.3f}" href="{esc(a["_src"])}" '
                    f'preserveAspectRatio="{par}" clip-path="url(#{cid})"/>')
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
                par2 = _fit_align(a) + (" slice" if a.get("fit") == "cover" else " meet")
                return (f'<clipPath id="{cid2}"><path d="{path_d(a["clip"], a["x"], a["y"] + dy, a["w"], h)}"/></clipPath>'
                        f'<image x="{a["x"]}" y="{a["y"] + dy:.3f}" width="{a["w"]}" height="{h:.3f}" '
                        f'href="{href}" preserveAspectRatio="{par2}" clip-path="url(#{cid2})"/>')
            par = _fit_align(a) + (" slice" if a.get("fit") == "cover" else " meet")
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
                      f' data-s="{pl["s"]:.4f}"{" data-fixed=\"1\"" if pl["fixed"] else ""}{" data-atom=\"1\"" if it.get("atom") else ""}>{pl["frag"]}</g>')
    ctx.sys = old
    guides = "" if not zones or page.get("_noguides") else "".join(
        f'<rect class="zone" x="{z["x"]:.3f}" y="{z["y"]:.3f}" width="{z["w"]:.3f}" height="{z["h"]:.3f}" '
        f'fill="none" stroke="#c9b8ff" stroke-width="0.25" stroke-dasharray="1.5 1"/>' for z in zones)
    bg = ctx.color(page.get("background"), "#ffffff") if page.get("background") else "#ffffff"
    extra = f'data-page="{pno}" data-tpl="{esc(page["id"])}"' + (f' data-spare="{esc(page["_spare"])}"' if page.get("_spare") else "")
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
    return 0.3 * float(a.get("leading") or float(a.get("size") or 9) * AUTO_LEAD) * PT


def place_items(ctx, page, W, H, mirror=False):
    """자유 배치 요소를 놓는다 → [{fi, it, frag, w, h, h0, y, dy, fixed}] (그리는 순서).

    글이 길어 자리가 자라면(실제 높이 > 설계 높이) **그 아래, 가로로 겹치는** 요소를 그만큼 민다 — 부품 안 원자와 같은 규칙.
    콘텐츠 블록 자리는 캔버스(_canvas)에서만 그린다(실제 콘텐츠는 세트가 끼운다).
    """
    canvas = bool(page.get("_canvas"))
    ctx.nums = {}                        # 번호 매기기는 면마다 다시 1부터 (시작 번호는 원자의 num_start)
    placed = []
    for fi, it in enumerate(page.get("items") or []):
        if it.get("hide"):
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
             for p in placed if p["grow"] and p["h"] > p["h0"] + 0.01 and not p["it"].get("atom")]   # 블록 · 부품만 아래를 민다 — 텍스트 프레임은 자라도 남을 안 민다(인디자인)
    for p in placed:
        it = p["it"]
        p["dy"] = 0.0 if p["fixed"] else sum(d for gi, gx0, gx1, gb, d in grown
                                          if gi != p["fi"] and it["y"] >= gb - 0.01 and it["x"] < gx1 - 0.01 and it["x"] + p["w"] > gx0 + 0.01)
        p["y"] = it["y"] + p["dy"]
    return placed


def text_area(page, W):
    """본문 영역 가로(좌우 여백 안) — 쪽 「여백 및 단」, 없으면 20mm"""
    m = page.get("margins") or {}
    return float(m.get("left") or 20), float(W) - float(m.get("right") or 20)


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
