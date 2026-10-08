"""면 대본 만들기 — 마우스·키보드만, 단축키 없음. 그릴 때마다 값이 들어갔는지 확인한다.

    from mkpage import *          # S · F · box · text · ellipse · head · tail · open_doc · add_page · done
각 요소는 ① 도구 누르고 빈 자리에서 끌어 그리고 ② 패널 숫자칸에 크기·자리를 치고 ③ 색을 번호로 친다.
"""
BLUE, BEIGE, BRICK, CREAM, INK, TAB = "#77a1c4", "#cfa76b", "#af9d81", "#f9f7ed", "#231f20", "#b4aa9a"
PURPLE, SKY, GRAYBOX, WHITE = "#8d7cba", "#e5f2f9", "#f5f4ef", "#ffffff"
SPOT = {"mm": [120, 250]}        # 임시로 끌어 그리는 빈 자리 (면 아래 오른쪽)
AWAY = {"mm": [205, 294]}        # 글 확정용 빈 구석


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
            {"js": "(() => { const bad = page.items.filter(i => (i.atom||{}).t === 'text' && /^글상자 —/.test((i.atom||{}).text || '')); "
                   "return '요소 ' + page.items.length + '개 · 자리 ' + page.items.filter(i => (i.atom||{}).bind).length + "
                   "'개 · 덜 쓴 글상자 ' + bad.length + '개'; })()"},
            {"shot": shot, "wait": 700}, {"hide": True, "wait": 500}]
