"""면 대본 만들기 — 마우스·키보드만, 단축키 없음. 그릴 때마다 값이 들어갔는지 확인한다.

    from mkpage import *          # S · F · box · text · ellipse · head · tail · open_doc · add_page · done
각 요소는 ① 도구 누르고 빈 자리에서 끌어 그리고 ② 패널 숫자칸에 크기·자리를 치고 ③ 색을 번호로 친다.
"""
BLUE, BEIGE, BRICK, CREAM, INK, TAB = "#77a1c4", "#cfa76b", "#af9d81", "#f9f7ed", "#231f20", "#b4aa9a"
PURPLE, SKY, GRAYBOX, WHITE = "#8d7cba", "#e5f2f9", "#f5f4ef", "#ffffff"
SPOT = {"mm": [120, 250]}        # 임시로 끌어 그리는 빈 자리 (면 아래 오른쪽)
AWAY = {"mm": [205, 294]}        # 글 확정용 빈 구석
MM = 25.4 / 72                   # 1pt = mm
_STYLE = {100: "Thin", 200: "ExtraLight", 300: "Light", 400: "Regular", 500: "Medium", 600: "SemiBold", 700: "Bold", 800: "ExtraBold", 900: "Black"}
_FACES = {}


def face(family, weight=400):
    """서체 집·굵기 → (윗높이, 아랫높이, 글 폭 함수 em) — 브라우저가 쓰는 그 파일의 hhea·hmtx (fc-match 로 찾는다)"""
    import subprocess
    from fontTools.ttLib import TTFont
    key = (family, weight)
    if key not in _FACES:
        got = None
        for q in (f"{family}:style={_STYLE.get(weight, 'Regular')}", family):
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


def chrome_extent(family, weight, size, s):
    """브라우저에서 자간 없이 그린 글의 첫 글자 왼쪽 → 끝 글자 왼쪽 거리(mm) — 커닝·합자까지 들어간 실제 값"""
    import os, re, subprocess, tempfile, json as _j, html as _h
    key = (family, weight, size, s)
    zm = max(1, min(100, int(9000 / (size * MM))))                             # 편집기 글 배치 해상도와 같게(render.TEXT_ZOOM, 큰 글은 낮춤) — 크기마다 글자 폭 반올림이 다르다
    if key not in _EXT:
        body = _h.escape(s)
        if "CJK" in family:                                                    # 편집기처럼 공백·문장부호는 한국어 꼴(render.ko_glyphs)
            from core.units import render
            body = re.sub("&#?\\w+;|[" + render.KO_LOCL + "]+", lambda m: m.group(0) if m.group(0).startswith("&") and m.group(0) not in ("&#160;", "&quot;", "&#x27;")
                          else f'<span lang="ko">{m.group(0)}</span>', body)
        doc = (f"<!doctype html><html lang=en><meta charset=utf-8><body style='margin:0'><span id=t style=\"font-family:'{family}';font-weight:{weight};"
               f"font-size:{size * MM * zm:.3f}px;white-space:pre;font-feature-settings:'liga' 1,'calt' 1\">{body}</span><pre id=o></pre><script>"
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


def text(x, y, w, h, s, size, color, label=None, bind=None, leading=None, align=None, bold=False, font=None, track=None, weight=None, alpha=None):
    st = ([S(label)] if label else [])
    tw, th = max(min(w, 60), 24), max(min(h, 24), 9)         # 임시 상자는 글을 치기 쉽게 넉넉히
    st += [{"draw": {"tool": "text", "from": SPOT, "to": {"mm": [SPOT["mm"][0] + tw, SPOT["mm"][1] + th]}}, "wait": 750},
           {"write": {"at": {"mm": [SPOT["mm"][0] + tw / 2, SPOT["mm"][1] + th / 2]}, "value": s, "away": AWAY}, "wait": 700},
           F('#side input[data-a="size"]', size)]
    if leading:
        st.append(F('#side input[data-a="leading"]', leading))
    if align:
        st.append({"pick": {"at": '#side select[data-a="align"]', "value": align}, "wait": 550})
    if font:                                                                   # 글꼴 — 「직접 입력…」 뒤 이름을 친다
        st.append({"pick": {"at": '#side select[data-a="font"]', "value": "__raw"}, "wait": 600})
        st.append(F('#side input[type="text"][data-a="font"]', font, 600))
    if track:
        st.append(F('#side input[data-a="tracking"]', track))
    if bold:
        st.append({"click": '#side input[data-a="b"]', "wait": 500})           # 굵게
    if weight:                                                                 # 굵기 — 「굵기」 칸에서 고른다 (500·600 …)
        st.append({"pick": {"at": '#side select[data-a="weight"]', "value": str(weight)}, "wait": 550})
    st += _color("color", color)
    st += [F('#side input[data-it="w"]', w), F('#side input[data-a="h"]', h),
           F('#side input[data-it="x"]', x), F('#side input[data-it="y"]', y, 550)]
    if bind:
        st.append({"pick": {"at": '#side select[data-a="bindsel"]', "value": bind}, "wait": 1000})
    return st + opacity(alpha)


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


def grep(n, pattern, color=None, bold=True, label=None, size=None, bshift=None, underline=False,
         blank=None, line=None, line_off=None, line_color=None, weight=None, hide=False):
    """GREP 스타일 규칙 하나 — 고른 글상자의 「＋ GREP 규칙」 → 패턴 · 굵게 · 색 · 크기 · 기준선 · 밑줄 · 칸으로 바꾸기.
    n = 이 글상자의 몇 번째 규칙(0부터). blank = 맞은 글 대신 이 폭(mm)의 밑줄 칸(원고의 ____ 빈칸) — line·line_off·line_color 로 선"""
    st = ([S(label)] if label else [])
    st += [{"click": "#side #s-grep-add", "wait": 700}, F(f'#side input[data-a="grep.{n}.re"]', pattern, 700)]
    if not bold:                                                               # 새 규칙은 굵게가 켜진 채로 생긴다
        st.append({"click": f'#side input[data-a="grep.{n}.b"]', "wait": 500})
    if color:
        st += _color(f"grep.{n}.color", color)
    for key, v in (("size", size), ("bshift", bshift), ("blank", blank), ("line", line), ("line_off", line_off)):
        if v is not None:
            st.append(F(f'#side input[data-a="grep.{n}.{key}"]', v, 600))
    if underline:                                                              # 밑줄 — line·line_off·line_color 로 굵기·내림(기준선→가운데)·색
        st.append({"click": f'#side input[data-a="grep.{n}.u"]', "wait": 500})
    if weight:                                                                 # 굵기 100~900 (굵게보다 먼저)
        st.append({"pick": {"at": f'#side select[data-a="grep.{n}.weight"]', "value": str(weight)}, "wait": 550})
    if hide:                                                                   # 표시 감추기 — 원고의 {…} 같은 약속 표시는 지우고 묶음 1 만
        st.append({"click": f'#side input[data-a="grep.{n}.hide"]', "wait": 500})
    if line_color:
        st += _color(f"grep.{n}.line_color", line_color)
    return st


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
    """도형 — 「도형」 도구로 그린 뒤 오른쪽 「모양」 칸에서 고른다. d 를 주면 「경로 d」 칸에 원본 꼭짓점 그대로 친다"""
    st = ([S(label)] if label else [])
    st += [{"draw": {"tool": "path", "from": SPOT, "to": {"mm": [SPOT["mm"][0] + min(w, 60), SPOT["mm"][1] + min(h, 30)]}}, "wait": 750},
           F('#side input[data-a="d"]', d, 800) if d else {"pick": {"at": '#side select[data-a="d"]', "value": SHAPES[name]}, "wait": 800}]
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
        return [{"js": f"window.prompt=(m,d)=>window.__p||d; window.confirm=()=>true; window.__p={name!r}; true", "wait": 300},
                S("＋ 새 문서", 1300), {"click": "#pcards .pcard.new", "wait": 5000},
                {"clickif": {"at": "#tg-side", "when": "!document.querySelector('#side') || !document.querySelector('#side').offsetParent"}, "wait": 1000}]
    return [{"js": "window.prompt=(m,d)=>window.__p||d; window.confirm=()=>true; true", "wait": 300},
            {"click": "#pcards .pcard:not(.new)", "wait": 4800},
            {"clickif": {"at": "#tg-side", "when": "!document.querySelector('#side') || !document.querySelector('#side').offsetParent"}, "wait": 1000}]


def expect_pages(n):
    """녹화 시작 전 — 문서가 딱 이만큼이어야 한다. 아니면 거기서 멈춘다(찌꺼기 위에 찍지 않게)."""
    return [{"js": f"(() => {{ const k = docPages().length; if (k !== {n}) throw new Error('시작 쪽 수가 {n} 이 아니라 ' + k); return '시작 쪽 {n} 확인'; }})()", "wait": 500}]


def add_page(label):
    return [S(label),
            {"clickif": {"at": "#tg-strip", "when": "!view.strip"}, "wait": 1100},
            {"click": "#rail .addpg", "wait": 900},
            {"click": '#rail .addpg .menu [data-new="blank"]', "wait": 2800},
            {"js": "(() => '쪽 ' + docPages().length + ' · 지금 ' + (idx()+1))()"}]


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
            {"js": "(() => { const bad = page.items.filter(i => (i.atom||{}).t === 'text' && /^글상자 —/.test((i.atom||{}).text || '')); "
                   "return '요소 ' + page.items.length + '개 · 자리 ' + page.items.filter(i => (i.atom||{}).bind).length + "
                   "'개 · 덜 쓴 글상자 ' + bad.length + '개'; })()"},
            {"shot": shot, "wait": 700}, {"hide": True, "wait": 500}]
