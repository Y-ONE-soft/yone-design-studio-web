"""면 대본 만들기 — 마우스·키보드만, 단축키 없음. 그릴 때마다 값이 들어갔는지 확인한다.

    from mkpage import *          # S · F · box · text · ellipse · head · tail · open_doc · add_page · done
각 요소는 ① 도구 누르고 빈 자리에서 끌어 그리고 ② 패널 숫자칸에 크기·자리를 치고 ③ 색을 번호로 친다.
"""
BLUE, BEIGE, BRICK, CREAM, INK, TAB = "#77a1c4", "#cfa76b", "#af9d81", "#f9f7ed", "#231f20", "#b4aa9a"
PURPLE, SKY, GRAYBOX, WHITE = "#8d7cba", "#e5f2f9", "#f5f4ef", "#ffffff"
SPOT = {"mm": [120, 250]}        # 임시로 끌어 그리는 빈 자리 (면 아래 오른쪽)
AWAY = {"mm": [205, 294]}        # 글 확정용 빈 구석
MM = 25.4 / 72                   # 1pt = mm
BODY_FAMILY = "Noto Sans CJK KR"       # 문서 기본 본문 글꼴($body)
_STYLE = {100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular", 500: "Medium", 600: "SemiBold", 700: "Bold", 800: "ExtraBold", 900: "Black"}
_FACES = {}


def face(family, weight=400):
    """서체 집·굵기 → (윗높이, 아랫높이, 글 폭 함수 em) — 편집기가 그리는 그 파일(시스템 서체·대본이 등록하는 서체)의 hhea·hmtx.
    시스템에 없는 서체만 fc-match 로 찾는다(검사가 「등록 안 된 서체」로 실패시킨다)"""
    import subprocess
    from fontTools.ttLib import TTFont
    key = (family, weight, font_file(family, weight))
    if key not in _FACES:
        got = (key[2], 0) if key[2] else None
        for q in ([] if got else [f"{family}:style={_STYLE.get(weight, 'Regular')}", family]):
            fam, path, idx = subprocess.check_output(["fc-match", "-f", "%{family}|%{file}|%{index}", q], text=True).split("|")
            if family.lower() in fam.lower():                                  # 그 집을 못 찾으면 굵기 없이 다시
                got = (path, idx)
                break
        if not got:
            raise RuntimeError(f"서체 없음: {family} — 설치할 것")
        f = TTFont(got[0], fontNumber=int(got[1] or 0))
        upm, hh, cmap, hm = f["head"].unitsPerEm, f["hhea"], f.getBestCmap(), f["hmtx"]
        adv = lambda s: sum(hm[cmap[ord(c)]][0] for c in s if ord(c) in cmap) / upm
        _FACES[key] = (hh.ascent / upm, -hh.descent / upm, adv)
    return _FACES[key]


_EXT = {}
REGISTERED = {}                  # 대본이 「＋ 서체」로 등록하는 서체 (집, 굵기) → 파일 — 재기도 그 파일로(register_font)


def font_file(family, weight):
    """그 서체·굵기를 편집기가 그릴 때 쓰는 파일 — 시스템 서체(core.units.fonts) 또는 대본이 등록하는 서체. 없으면 None"""
    import os, sys
    if (family, int(weight)) in REGISTERED:
        return REGISTERED[(family, int(weight))]
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from core.units.fonts import system_fonts
    return next((f["path"] for f in system_fonts() if f["family"] == family and f["weight"] == int(weight) and not f["italic"]), None)


def chrome_extent(family, weight, size, s, lang="ko", opsz=None):
    """브라우저에서 자간 없이 그린 글의 첫 글자 왼쪽 → 끝 글자 왼쪽 거리(mm) — 커닝·합자까지 들어간 실제 값.
    lang = 글 언어(편집기 글상자 「언어」, 기본 한국어) — 편집기처럼 공백·문장부호를 그 언어 꼴로(render.locl_html)
    opsz = 글상자 「광학 크기」(가변 서체) — 키워 그려 재면 브라우저가 광학 크기를 최대로 잡아 폭이 달라진다(배재1 포켓북 Bodoni Moda)"""
    import os, subprocess, tempfile, json as _j, sys
    key = (family, weight, size, s, lang, font_file(family, weight), opsz)
    zm = max(1, min(100, int(9000 / (size * MM))))                             # 편집기 글 배치 해상도와 같게(render.TEXT_ZOOM, 큰 글은 낮춤) — 크기마다 글자 폭 반올림이 다르다
    if key not in _EXT:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))   # 리포 뿌리 — 대본은 단위 폴더에서 돈다
        from core.units import render
        body = render.locl_html(render.esc(s), render.font_family(family), lang)
        ff = font_file(family, weight)                                         # 편집기와 같은 서체 파일로 잰다 — 컴퓨터에 깔린 서체는 판이 달라 커닝이 다를 수 있다(「BY」 0.23mm)
        face = (f"<style>@font-face{{font-family:'{family}';font-weight:{weight};src:url('file://{ff}')}}</style>" if ff else "")
        doc = (f"<!doctype html><html lang=en><meta charset=utf-8>{face}<body style='margin:0'><span id=t style=\"font-family:'{family}';font-weight:{weight};"
               f"font-size:{size * MM * zm:.3f}px;white-space:pre;font-feature-settings:'liga' 1,'calt' 1"
               + (f";font-optical-sizing:none;font-variation-settings:'opsz' {opsz:g}" if opsz else "") + f"\">{body}</span><pre id=o></pre><script>"
               "document.fonts.ready.then(()=>{const c=[],w=document.createTreeWalker(document.getElementById('t'),NodeFilter.SHOW_TEXT),r=document.createRange();"
               "let n;while((n=w.nextNode()))for(let i=0;i<n.data.length;i++)c.push([n,i]);"
               "const at=i=>{r.setStart(c[i][0],c[i][1]);r.setEnd(c[i][0],c[i][1]+1);return r.getBoundingClientRect().left};"
               f"document.getElementById('o').textContent=JSON.stringify(at({len(s) - 1})-at(0));}});</script>")
        fd, path = tempfile.mkstemp(suffix=".html")
        os.write(fd, doc.encode("utf-8")); os.close(fd)
        out = subprocess.run(["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--headless=new", "--disable-gpu",
                              "--virtual-time-budget=4000", "--dump-dom", "file://" + path], capture_output=True, text=True, timeout=60).stdout
        os.remove(path)
        px = float(_j.loads(out[out.find('<pre id="o">') + 12: out.find("</pre>")]))
        _EXT[key] = px / zm                                                    # 편집기와 같은 배율(1mm = zm px)로 그려 잰 px → mm
    return _EXT[key]


def track_from(pdf_page, box, s, family, weight, size):
    """원본 PDF 쪽의 글자 위치로 자간(‰) — (원본 첫~끝 글자 거리 - 브라우저 같은 거리) / 사이 수. 커닝은 양쪽 다 들어 있다.
    box = 원본 글자 상자(x, y, w, h mm, 재단 여백 뺀 지면 좌표)"""
    import pymupdf
    if len(s) < 2:
        return 0
    t = pdf_page.trimbox
    x, y, w, h = box
    R = pymupdf.Rect(t.x0 + (x - 0.3) / MM, t.y0 + (y - 0.3) / MM, t.x0 + (x + w + 0.3) / MM, t.y0 + (y + h + 0.3) / MM)
    y0, y1 = t.y0 + y / MM, t.y0 + (y + h) / MM                               # 글자 가운데가 상자 안인 것만 — 위아래 줄이 가까우면 옆 줄을 집는다
    ch = [c for b in pdf_page.get_text("rawdict", clip=R)["blocks"] for l in b.get("lines", []) for sp in l["spans"] for c in sp["chars"]
          if c["c"].strip() and y0 <= (c["bbox"][1] + c["bbox"][3]) / 2 <= y1]
    if len(ch) < 2:
        return 0
    orig = (ch[-1]["origin"][0] - ch[0]["origin"][0]) * MM
    return round((orig - chrome_extent(family, weight, size, s)) / (len(s) - 1) / (size * MM) * 1000)


def top_of(base, size, family, weight=400, leading=None):
    """원본 기준선(mm) → 편집기 글상자 위 끝(mm). 편집기 글줄 = CSS 줄 상자: 위 끝 + 반 행간 + 서체 윗높이 = 기준선.
    측정 보정 없이 첫 판에 맞추는 공식 — 어긋나면 덮지 말고 원인(서체·반올림·행간)을 찾는다."""
    asc, desc, _ = face(family, weight)
    s = size * MM
    lead = (leading or size * 1.45) * MM
    return base - ((lead - (asc + desc) * s) / 2 + asc * s)


def S(t, w=1700):
    return {"say": t, "wait": w}


def F(sel, v, w=420):
    return {"fill": {"at": sel, "value": v}, "wait": w}


def _place(x, y, w=None, h=None, awide=True):
    st = []
    if w is not None:
        st.append(F('#side input[data-a="w"]' if awide else '#side input[data-it="w"]', w))
    if h is not None:
        st.append(F('#side input[data-a="h"]', h))
    st += [F('#side input[data-it="x"]', x), F('#side input[data-it="y"]', y)]
    return st


def _color(key, v):
    return [{"pick": {"at": f'#side select[data-a="{key}"]', "value": "__raw"}, "wait": 650},
            F(f'#side input[type="text"][data-a="{key}"]', v, 750)]


def color_p(path, v):
    """인디자인 칸(data-p)의 색 — 「직접 고르기…」 → 색 번호"""
    return [{"pick": {"at": f'#side select[data-p="{path}"]', "value": "__raw"}, "wait": 650},
            F(f'#side input[type="text"][data-p="{path}"]', v, 750)]


def opacity(v):
    """불투명 % — 100 이면 아무것도 안 한다"""
    return [F('#side input[data-a="opacity"]', v)] if v is not None and v < 100 else []


def box(x, y, w, h, fill=None, label=None, radius=0, alpha=None):
    st = ([S(label)] if label else [])
    st += [{"draw": {"tool": "rect", "from": SPOT, "to": {"mm": [SPOT["mm"][0] + min(w, 60), SPOT["mm"][1] + min(h, 30)]}}, "wait": 750}]
    st += _place(x, y, w, h)
    st.append(F('#side input[data-a="radius"]', radius))                     # 둥글기도 늘 지정 (기본 1mm 가 남지 않게)
    if fill:
        st += _color("fill", fill)
    return st + opacity(alpha)


def fb_shift(family, weight, size, leading):
    """첫 번째 기준선 오프셋 「어센트」(인디자인 기본) — 크롬 줄 상자의 첫 줄 기준선(위 끝 + 반 행간 + 윗높이)과
    인디자인 어센트(「d」 높이) 차이 mm. 원본 첫 줄 위(top_of)에 놓던 프레임을 이만큼 내리면 첫 줄 기준선이 그대로다"""
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from core.units import render
    m = render.font_metrics(family or BODY_FAMILY, int(weight or 400))
    S_, L = size * MM, (leading or size * 1.45) * MM
    return (L - (m["asc"] + m["desc"]) * S_) / 2 + m["asc"] * S_ - m["d"] * S_


def P_(path, v, w=420):
    """오른쪽 패널의 인디자인 칸(data-p) 하나 — 숫자 · 글 칸"""
    return F(f'#side input[data-p="{path}"]', v, w)


def pick_p(path, value, w=550):
    return {"pick": {"at": f'#side select[data-p="{path}"]', "value": str(value)}, "wait": w}


def fstyle_of(weight=None, italic=False, bold=False):
    """글꼴 스타일 칸 값 — 굵기(+ i = 기울임꼴)"""
    w = int(weight or (700 if bold else 400))
    return f"{w}{'i' if italic else ''}"


def text(x, y, w, h, s, size, color, label=None, bind=None, leading=None, align=None, bold=False, font=None, track=None, weight=None, alpha=None, tsume=None,
         auto="height", first=None):
    """텍스트 프레임 — 문자 도구로 그리고 글 · 글꼴 · 크기 · 행간 · 정렬 · 자간 · 색 · 자리. y · h = 원본 첫 줄 위(top_of) 기준 —
    첫 번째 기준선 오프셋(어센트)만큼 프레임을 내린다(first = 첫 단락 (글꼴, 굵기, 크기, 행간)이 프레임 글과 다를 때).
    auto = 자동 크기 조정(height 높이만 · width 너비만 · both 높이 및 너비 · "" 끔) — 예전 편집기 기본(높이만)을 적어 둔다.
    leading 이 없으면 예전 자동 행간(크기의 145%)을 적어 둔다 — 지금 자동은 120%(인디자인)"""
    lead = leading or round(size * 1.45, 3)
    fam, wt, sz, ld = first or (font or BODY_FAMILY, weight or (700 if bold else 400), size, lead)
    sh = round(fb_shift(fam, wt, sz, ld), 3)
    y, h = round(y + sh, 3), round(h - sh, 3)
    st = ([S(label)] if label else [])
    tw, th = max(min(w, 60), 24), max(min(h, 24), 9)         # 임시 상자는 글을 치기 쉽게 넉넉히
    st += [{"draw": {"tool": "text", "from": SPOT, "to": {"mm": [SPOT["mm"][0] + tw, SPOT["mm"][1] + th]}}, "wait": 750},
           {"write": {"at": {"mm": [SPOT["mm"][0] + tw / 2, SPOT["mm"][1] + th / 2]}, "value": s, "away": AWAY}, "wait": 700},
           F('#side input[data-a="size"]', size), P_("leading", lead)]
    if align:
        st.append(pick_p("align", align))
    if font:                                                                   # 글꼴 — 시스템 글꼴 목록에서 고른다(없으면 register_font 로 먼저 등록)
        st.append({"pick": {"at": '#side select[data-a="font"]', "value": font}, "wait": 600})
    if track:
        st.append(P_("tracking", track))
    if tsume:                                                                  # 자간 축소 % (인디자인 문자 패널)
        st.append(P_("tsume", tsume))
    if bold or weight:                                                         # 글꼴 스타일 — 굵기(인디자인 글꼴 스타일)
        st.append(pick_p("fstyle", fstyle_of(weight, bold=bold)))
    st += _color("color", color)
    st += [F('#side input[data-it="w"]', w), F('#side input[data-a="h"]', h),
           F('#side input[data-it="x"]', x), F('#side input[data-it="y"]', y, 550)]
    if auto:
        st.append(pick_p("auto_size", auto))
    if bind:
        st.append({"pick": {"at": '#side select[data-a="bindsel"]', "value": bind}, "wait": 1000})
    return st + opacity(alpha)


def register_font(path, label=None):
    """서체 등록 — 글상자를 고른 채 「＋ 서체」를 눌러 뜬 파일 창에서 서체 파일을 고른다. 시스템 서체 목록에 든다
    (이 대본의 재기 — 자간 등 — 도 그 파일로 하게 REGISTERED 에 적는다)"""
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from core.units.fonts import _meta
    m = _meta(path)
    if m:
        REGISTERED[(m[0], int(m[1]))] = path
    return ([S(label)] if label else []) + [{"upload": {"at": "#side #font-file", "path": path}, "wait": 2500}]


def justify(word_min=100, word_max=133, letter_min=-8, letter_max=250, family=None, weight=400):
    """고른 텍스트 프레임의 균등 배치(인디자인) — 단어 간격 최소 · 최대 %, 문자 간격 최소 · 최대(원본에서 잰 ‰ em 을 공백 폭 % 로 바꿔 친다).
    기본값 = 이 출판사 책(인디자인 원본 5권 실측): 단어 100·133%, 문자 최소 −8‰, 늘림 250‰. 편집기 기본은 인디자인 공장 기본(80·133%, 0·0)."""
    sp = space_em(family or BODY_FAMILY, weight)
    out = []
    for k, v in (("word_min", word_min), ("word_max", word_max), ("letter_min", letter_min), ("letter_max", letter_max)):
        if v is None:
            continue
        out.append(P_(f"jc.{k}", round(v / sp / 10, 2) if k.startswith("letter") else v, 600))
    return out


def space_em(family, weight=400):
    """공백 폭(em) — 균등 배치 문자 간격 % 의 기준"""
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    from core.units import render
    return render.font_metrics(family or BODY_FAMILY, int(weight or 400))["space"]


# ── 스타일 · 데이터 필드(인디자인 칸 · 단위) ──
def shade_offsets(v):
    """원본에서 잰 음영 상자 값 → 인디자인 단락 음영 · 테두리. 원본 잼: pad = 글 왼쪽 − 상자 왼쪽, pad_top = 첫 줄 위 − 상자 위,
    pad_bottom = 상자 아래 − 끝 줄 아래, space_before = 앞 글 아래 → 상자 위(상자끼리 잰 간격), shade_ol · or = 너비 「열」의 단 가장자리 → 상자.
    인디자인 음영은 글을 밀지 않는다 — 음영은 오프셋 위쪽 · 아래쪽 · 왼쪽 · 오른쪽으로 넓히고, 글 자리는 들여쓰기 · 단락 앞뒤 공백으로 옮긴다.
    음영과 같이 그린 테두리는 같은 자리(단락 테두리 오프셋 = 음영 오프셋). _after = 같은 음영 상자 안에서 앞 단락을 잇는 단락"""
    if not any(k in v for k in ("pad", "pad_top", "pad_bottom")):
        return v
    v = dict(v)
    pad = float(v.pop("pad", 0) or 0)
    pt, pb = float(v.pop("pad_top", pad) or 0), float(v.pop("pad_bottom", pad) or 0)
    after = v.pop("_after", None)
    ol, orr = float(v.get("shade_ol") or 0), float(v.get("shade_or") or 0)
    if v.get("shade_fit"):
        v["indent"] = round(float(v.get("indent") or 0) + pad, 3)
        if "indent_right" in v:                                        # 오른쪽 상자 끝을 잰 단락만 — 안 잰 단락은 글 너비가 열 끝까지(음영은 글을 밀지 않는다, 상자가 열 밖으로 나간다 — 정본 영작 보기단어)
            v["indent_right"] = round(float(v.get("indent_right") or 0) + pad, 3)
        v["shade_ol"] = v["shade_or"] = round(pad, 3)
    else:
        v["indent"] = round(float(v.get("indent") or 0) + pad - ol, 3)
        v["indent_right"] = round(float(v.get("indent_right") or 0) + pad - orr, 3)
    v["shade_ot"], v["shade_ob"] = round(pt, 3), round(pb, 3)
    if after is None:
        v["space_before"] = round(float(v.get("space_before") or 0) + pt, 3)
    else:
        v["space_before"] = round(float(v.get("space_before") or 0) - float(after), 3)
    v["space_after"] = round(float(v.get("space_after") or 0) + pb, 3)
    v.setdefault("space_same", 0)                                      # 같은 필드 음영 단락끼리는 붙인다(동일한 스타일 단락 사이 간격 0)
    if v.get("border"):
        for k in ("ot", "ob", "ol", "or"):
            v["border_" + k] = v["shade_" + k] if v.get("shade_" + k) is not None else 0
        if v.get("shade_fit"):
            v["border_fit"] = True
        if v.get("shade_r"):
            v["border_r"] = v["shade_r"]
    return v


def pstyle_fields(name, v):
    """스타일 창이 열린 채 단락 스타일 하나의 칸들 — 옛 꼴 값(굵게 · 굵기 · 음영 여백 · 내림 mm · 문자 간격 ‰)은 인디자인 값으로 바꿔 친다"""
    v = shade_offsets(v)
    q = lambda k: f'[data-st="{name}:{k}"]'
    st = []
    fam = v.get("font") or BODY_FAMILY
    if v.get("font"):
        st.append({"pick": {"at": "select" + q("font"), "value": str(v["font"])}, "wait": 450})
    if v.get("weight") or v.get("b") or v.get("i"):
        st.append({"pick": {"at": "select" + q("fstyle"), "value": fstyle_of(v.get("weight"), v.get("i"), v.get("b"))}, "wait": 450})
    for k, val in v.items():
        if k in ("font", "weight", "b", "i", "__n"):
            continue
        if k in ("align", "start"):                                     # start = 단락 시작(분리 금지 옵션 — column · frame · page)
            st.append({"pick": {"at": "select" + q(k), "value": str(val)}, "wait": 450})
        elif k in ("shade_fit", "border_fit"):
            if val:
                st.append({"pick": {"at": "select" + q(k), "value": "1"}, "wait": 450})
        elif k in ("keep_next", "keep_together"):
            if val:
                st.append({"click": "input" + q(k), "wait": 450})
        elif k == "drop":                                               # 기준선 이동 pt(위가 +) — 원본 잼은 내림 mm
            st.append(F("input" + q(k), round(-float(val) / MM, 2), 450))
        elif k == "tabs":
            st.append(F("input" + q(k), ", ".join(" ".join(str(x) for x in (f"{float(t['at']):g}", t.get("align") or "left", t.get("leader") or "") if x != "") for t in val), 450))
        elif k == "jc":
            sp = space_em(fam, v.get("weight") or 400)
            for kk, vv in val.items():
                st.append(F("input" + q(f"jc.{kk}"), round(vv / sp / 10, 2) if kk.startswith("letter") else vv, 450))
        elif k == "list":
            for kk, vv in val.items():
                if kk in ("type", "format", "after"):
                    st.append({"pick": {"at": "select" + q(f"list.{kk}"), "value": {"\t": "\t", "": "none"}.get(vv, vv)}, "wait": 450})
                else:
                    st.append(F("input" + q(f"list.{kk}"), vv, 450))
        elif k in ("rule_above", "rule_below"):
            for kk, vv in val.items():
                st.append({"pick": {"at": "select" + q(f"{k}.{kk}"), "value": vv}, "wait": 450} if kk == "width" else F("input" + q(f"{k}.{kk}"), vv, 450))
        elif val is not None and val != "":
            st.append(F("input" + q(k), val, 450))
    return st


def pstyle_steps(styles, label="단락 스타일"):
    """단락 스타일 — 스타일 · 색상 견본 창 「＋ 새 단락 스타일」 → 이름 → 칸마다"""
    st = [S(label + " — 스타일 · 색상 견본 창", 1300), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}, {"click": "#side #s-skin-edit", "wait": 1200}]
    for name, v in styles:
        st += [S(f"단락 스타일 「{name}」", 800), {"answer": name}, {"click": "#st-new", "wait": 900}] + pstyle_fields(name, v)
    return st + [{"click": "#sheet-x", "wait": 900}]


def cstyle_id(c):
    """문자 스타일 옛 꼴(밑줄 굵기 · 내림 mm · 바탕 띠) → 인디자인 밑줄 옵션(두께 · 오프셋 pt)"""
    c = dict(c)
    if c.get("u") and any(k in c for k in ("line", "line_off", "line_color")):
        lw = float(c.pop("line", 0.18) or 0.18)
        c["u_w"] = round(lw / MM, 3)
        c["u_off"] = round((float(c.pop("line_off", 0.4) or 0.4) - lw / 2) / MM, 3)
        if c.get("line_color"):
            c["u_color"] = c.pop("line_color")
    if c.get("bg") and c.get("bg_band"):
        band, off = float(c.pop("bg_band")), float(c.pop("bg_off", 0) or 0)
        c.update(u=True, u_w=round(band / MM, 3), u_off=round(-(off + band / 2) / MM, 3), u_color=c.pop("bg"))
    if c.get("bg"):
        raise ValueError("문자 스타일 바탕 상자는 인디자인에 없다 — 밑줄(띠)이나 고정 개체로")
    return c


def cstyle_fields(name, c):
    c = cstyle_id(c)
    sel = lambda k: f'#sbody [data-cs="{name}:{k}"]'
    st = []
    if c.get("font"):
        st.append({"pick": {"at": sel("font"), "value": str(c["font"])}, "wait": 600})
    if c.get("weight") or c.get("b") or c.get("i"):
        st.append({"pick": {"at": sel("fstyle"), "value": fstyle_of(c.get("weight"), c.get("i"), c.get("b"))}, "wait": 600})
    if c.get("u"):
        st.append({"click": sel("u"), "wait": 900})                     # 밑줄을 켜야 밑줄 칸이 나온다
    for k, v in c.items():
        if k in ("font", "weight", "b", "i", "u"):
            continue
        if k in ("u_style", "case"):
            st.append({"pick": {"at": sel(k), "value": str(v)}, "wait": 600})
        elif k == "nobreak":
            if v:
                st.append({"click": sel(k), "wait": 600})
        elif v is not None and v != "":
            st.append(F(sel(k), v, 600))
    return st


def cstyle_steps(styles, label="문자 스타일"):
    """문자 스타일 — 스타일 · 색상 견본 창 「＋ 새 문자 스타일」 → 이름 → 칸마다"""
    st = [S(label + " — 스타일 · 색상 견본 창", 1200), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}, {"click": "#side #s-skin-edit", "wait": 1200}]
    for name, props in styles:
        st += [S(f"문자 스타일 「{name}」", 800), {"answer": name}, {"click": "#cs-new", "wait": 1200}] + cstyle_fields(name, props)
    return st + [{"click": "#sheet-x", "wait": 900}]


def slot_style(field, style, w=450):
    """데이터 필드 단락 스타일 — 고른 텍스트 프레임의 데이터 병합 칸"""
    return {"pick": {"at": f'#side select[data-p="slot_fmt.{field}.style"]', "value": style}, "wait": w}


def slot_inline(field, cs=None, sep="\t"):
    """「다음 필드와 같은 단락」 — 템플릿 단락 「«이 필드»⇥«다음 필드»」. 필드 뒤 글자(탭 · 공백 · 없음) · 문자 스타일"""
    st = [{"click": f'#side input[data-p="slot_fmt.{field}.inline"]', "wait": 800}]
    st.append({"pick": {"at": f'#side select[data-p="slot_fmt.{field}.sep"]', "value": {"\t": "\t", "": "none"}.get(sep, sep)}, "wait": 600})
    if cs:
        st.append({"pick": {"at": f'#side select[data-p="slot_fmt.{field}.cs"]', "value": cs}, "wait": 600})
    return st


def slot_anchor(field, part, pos="inline", at="end", **o):
    """데이터 필드 고정 개체(인디자인) — 그룹 · 위치(inline 인라인 · above 줄 위 · custom 사용자 정의) · 필드 앞(start) · 뒤(end) · 옵션(x · y · space · align · before · after · xref · yref)"""
    F_ = lambda k: f"slot_fmt.{field}.anc.{k}"
    st = [{"pick": {"at": f'#side select[data-p="{F_("part")}"]', "value": part}, "wait": 900},
          {"pick": {"at": f'#side select[data-p="{F_("pos")}"]', "value": pos}, "wait": 800},
          {"pick": {"at": f'#side select[data-p="{F_("at")}"]', "value": at}, "wait": 600}]
    for k, v in o.items():
        if v is None:
            continue
        if k in ("xref", "yref", "align"):
            st.append({"pick": {"at": f'#side select[data-p="{F_(k)}"]', "value": v}, "wait": 600})
        elif k == "space":
            if v:
                st.append({"click": f'#side input[data-p="{F_(k)}"]', "wait": 600})
        else:
            st.append(F(f'#side input[data-p="{F_(k)}"]', v, 600))
    return st


def slot(name, label=None):
    """고른 글상자에 자리 이름 — 「원고 자리」에서 「직접 적기…」 → 이름. 원고가 이 이름으로 글을 보낸다(원고자리_규약.md)"""
    st = ([S(label)] if label else [])
    return st + [{"pick": {"at": '#side select[data-a="bindsel"]', "value": "__other"}, "wait": 800},
                 F('#side input[data-a="bind"]', name, 800)]


def put_content(obj, label="원고 넣기 — 바깥 시스템이 보내는 꼴(자리 이름 → 글)"):
    """문서 패널의 「원고 넣기」에 원고 JSON 을 치고 넣는다 — Esc 로 선택을 풀면 문서 패널이 나온다
    (빈 곳 누르기는 지면 전체를 덮은 바탕 면이 있으면 그 면이 골라져서 안 된다 — 간지)"""
    import json as _json
    return [S(label, 1800), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 900},
            F("#side #s-content", _json.dumps(obj, ensure_ascii=False), 900),
            {"click": "#side #s-content-put", "wait": 2500},
            {"js": "(() => { const t = document.querySelector('#st').textContent; if (/저장 실패/.test(t)) throw new Error('원고 저장 실패 — ' + t); return '원고 저장 확인'; })()"},
            {"js": "(() => document.querySelector('#s-content-rep') ? document.querySelector('#s-content-rep').textContent : '보고 없음')()"}]


def columns(n, gutter, label=None):
    """지면 「여백 및 단」의 단 — Esc 로 선택을 풀고 쪽 패널의 단 수·단 간격을 친다. 원고는 단 순서로 들어간다(content.slots)"""
    return [S(label or f"여백 및 단 — {n}단 · 간격 {gutter}mm (원고는 왼쪽 단 → 오른쪽 단)", 1300), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
            F("#side #s-col-n", n, 800), F("#side #s-col-g", gutter, 900),
            {"js": f"(() => {{ const c = page.columns || {{}}; if (c.n !== {n} || c.gutter !== {gutter}) throw new Error('단 지정 실패 ' + JSON.stringify(c)); return '단 ' + c.n + ' · ' + c.gutter + 'mm'; }})()"}]


def grep(n, pattern, cs, label=None):
    """GREP 스타일 하나(인디자인) — 고른 텍스트 프레임의 「＋ 새 GREP 스타일」 → 대상 텍스트 · 스타일 적용(문자 스타일).
    n = 이 프레임의 몇 번째(0부터). 문자 스타일은 미리 만들어 둔다(cstyle_steps)"""
    st = ([S(label)] if label else [])
    return st + [{"click": "#side #s-grep-add", "wait": 700}, F(f'#side input[data-a="grep.{n}.re"]', pattern, 700),
                 {"pick": {"at": f'#side select[data-a="grep.{n}.cs"]', "value": cs}, "wait": 700}]


def ref_image(doc, xref, path):
    """원본 PDF 에 박힌 그림을 화면에 보이는 색 그대로 PNG 로. CMYK 는 문서의 출력 색 프로필(OutputIntent)로 바꾼다 —
    원본 쪽도 그 프로필로 그려진다. 기본 변환은 밝기가 6~7 어둡게 나와 위의 글 잉크까지 틀리게 쟀다(2026-10-12 배재1 포켓북 바탕)"""
    import io
    import re
    import pymupdf
    from PIL import Image, ImageCms
    pix = pymupdf.Pixmap(doc, xref)
    oi = re.search(r"/OutputIntents\s*\[\s*(\d+) 0 R", doc.xref_object(doc.pdf_catalog()))
    if pix.n - pix.alpha == 4 and oi:
        prof = re.search(r"/DestOutputProfile (\d+) 0 R", doc.xref_object(int(oi.group(1))))
        im = Image.frombytes("CMYK", (pix.width, pix.height), pix.samples if not pix.alpha else pymupdf.Pixmap(pix, 0).samples)
        ImageCms.profileToProfile(im, ImageCms.ImageCmsProfile(io.BytesIO(doc.xref_stream(int(prof.group(1))))),
                                  ImageCms.createProfile("sRGB"), outputMode="RGB").save(path)
        return path
    if pix.n - pix.alpha >= 4:
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    pix.save(path)
    return path


def image(x, y, w, h, path, label=None):
    """그림 — 「그림」 도구로 자리를 끌고, 속성에서 파일을 골라 넣는다"""
    st = ([S(label)] if label else [])
    st += [{"draw": {"tool": "image", "from": SPOT, "to": {"mm": [SPOT["mm"][0] + min(w, 60), SPOT["mm"][1] + min(h, 30)]}}, "wait": 750}]
    st += _place(x, y, w, h)
    st += [{"upload": {"at": "#side #img-file", "path": path}, "wait": 2500}]
    return st


SHAPES = {"화살표 →": "M0 0.3 L0.6 0.3 L0.6 0 L1 0.5 L0.6 1 L0.6 0.7 L0 0.7 Z",
          "삼각형": "M0.5 0 L1 1 L0 1 Z", "마름모": "M0.5 0 L1 0.5 L0.5 1 L0 0.5 Z",
          "육각형": "M0.25 0 L0.75 0 L1 0.5 L0.75 1 L0.25 1 L0 0.5 Z",
          "평행사변형": "M0.12 0 L1 0 L1 1 L0 1 Z", "모서리 자른 띠": "M0 0 L1 0 L0.88 1 L0 1 Z"}


def shape(x, y, w, h, fill, name="평행사변형", label=None, d=None):
    """모양 — 다각형 도구로 그린 뒤 「기준점 경로」(펜 도구로 찍는 기준점 — 0~1 비율)에 원본 꼭짓점을 친다"""
    st = ([S(label)] if label else [])
    st += [{"draw": {"tool": "path", "from": SPOT, "to": {"mm": [SPOT["mm"][0] + min(w, 60), SPOT["mm"][1] + min(h, 30)]}}, "wait": 750},
           F('#side input[data-a="d"]', d or SHAPES[name], 800)]
    st += _place(x, y, w, h)
    st += _color("fill", fill)
    return st


def ellipse(x, y, d, fill=None, stroke=None, sw=None, h=None, alpha=None):
    """원 — 채움 없이 테두리만도 된다. 테두리를 안 주면 「획 없음」으로 (기본 검은 획이 남지 않게)"""
    st = [{"draw": {"tool": "ellipse", "from": SPOT, "to": {"mm": [SPOT["mm"][0] + d, SPOT["mm"][1] + (h or d)]}}, "wait": 700}]
    st += _place(x, y, d, h or d)
    if fill:
        st += _color("fill", fill)
    else:
        st.append({"pick": {"at": '#side select[data-a="fill"]', "value": ""}, "wait": 550})      # 채움 없음
    if stroke:
        st += _color("stroke.color", stroke)
        if sw:
            st.append(F('#side input[data-a="stroke.w"]', sw))
    else:
        st.append({"pick": {"at": '#side select[data-a="stroke.color"]', "value": ""}, "wait": 550})   # 획 없음
    return st + opacity(alpha)


def open_doc(name=None):
    """문서 열기 — 없으면 새로 만든다"""
    if name:
        return [S("＋ 새 문서", 1300), {"answer": name},                       # 뜨는 묻는 창(문서 이름)에 칠 글 — 창이 뜨면 거기에 친다(rec.py · cdp.py)
                {"click": "#pcards .pcard.new", "wait": 5000},
                {"until": "docPages().length > 0 && page", "wait": 500},             # 서버가 바쁘면(기동 직후 구성 계산) 5초로 모자라다
                {"clickif": {"at": "#tg-side", "when": "!document.querySelector('#side') || !document.querySelector('#side').offsetParent"}, "wait": 1000}]
    return [{"click": "#pcards .pcard:not(.new)", "wait": 4800},
            {"clickif": {"at": "#tg-side", "when": "!document.querySelector('#side') || !document.querySelector('#side').offsetParent"}, "wait": 1000}]


def expect_pages(n):
    """녹화 시작 전 — 문서가 딱 이만큼이어야 한다. 아니면 거기서 멈춘다(찌꺼기 위에 찍지 않게)."""
    return [{"js": f"(() => {{ const k = docPages().length; if (k !== {n}) throw new Error('시작 쪽 수가 {n} 이 아니라 ' + k); return '시작 쪽 {n} 확인'; }})()", "wait": 500}]


def add_page(label):
    return [S(label),
            {"clickif": {"at": "#tg-strip", "when": "!view.strip"}, "wait": 1100},
            {"js": "(() => { window.__np = docPages().length; return '쪽 ' + window.__np; })()"},
            {"click": "#rail .addpg", "wait": 900},
            {"click": '#rail .addpg .menu [data-new="blank"]', "wait": 2800},
            {"until": "docPages().length === window.__np + 1 && page && !(page.items || []).length"},   # 새 빈 쪽이 열릴 때까지 — 서버가 바쁘면 늦게 열려 앞 쪽에 그렸다(2026-10-15)
            {"js": "(() => { if (docPages().length !== window.__np + 1 || (page.items || []).length) throw new Error('새 쪽이 안 열림 — 지금 ' + (idx() + 1) + '/' + docPages().length); return '쪽 ' + docPages().length + ' · 지금 ' + (idx()+1); })()"}]


def head(code, title, step=1):
    st = [S(f"공통 머리 — {code} {title}", 1900)]
    st += box(0, 0, 210, 29, CREAM)
    st += box(11.2, 0, 2.2, 29, BLUE)
    st += text(20, 6.8, 34, 4, f"STEP 0{step}   FRAME", 8, TAB)
    st += text(20, 15.2, 12, 11, code, 25, BLUE)
    st += text(29.5, 16.7, 46, 6, title, 13, INK)
    for k, x in enumerate((55.5, 66.5, 77.5)):
        st += ellipse(x, 16.1, 5.4, BLUE if k == 0 else "#eceae2")
    return st


def tail(pno):
    return [S("꼬리", 1400)] + text(15.2, 282, 40, 3, f"{pno}   STEP BY STEP", 6, "#3b4247")


def done(name, shot):
    """면 끝 — 덜 쓴 글상자가 없는지 스스로 센다"""
    return [S(f"{name} 완성", 2000),
            {"js": "(() => { if (/^저장 실패/.test(document.querySelector('#st').textContent)) throw new Error(document.querySelector('#st').textContent); return '저장 확인'; })()", "wait": 300},
            {"js": "(() => { const bad = page.items.filter(i => (i.atom||{}).t === 'text' && /^(텍스트 프레임|글상자) —/.test((i.atom||{}).text || '')); "
                   "return '요소 ' + page.items.length + '개 · 자리 ' + page.items.filter(i => (i.atom||{}).bind).length + "
                   "'개 · 덜 쓴 글상자 ' + bad.length + '개'; })()"},
            {"shot": shot, "wait": 700}, {"hide": True, "wait": 500}]
