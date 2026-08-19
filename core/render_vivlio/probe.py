"""PDF 계측 원자 — paged / measure / verify 가 공유하는 최소 단위.

전부 **mm 단위**로 돌려준다(포인트는 이 파일 밖으로 새지 않는다). 조판이
InDesign 이 아니라 코드라서, indd 덤프 기반 게이트를 못 쓰는 자리를 PDF 계측이
대신 메운다 — 그 계측의 바닥이 여기다.

⚠ Vivliostyle 출력의 서체 이름은 `Type3 (n 0 R)` 로 바뀐다. 서체 **이름으로**
찾는 검사는 아무것도 못 찾고 조용히 통과한다 — 크기(pt)와 위치로 판정할 것.
"""
import re

PT = 72 / 25.4          # 1mm = PT 포인트


def _fitz():
    import fitz
    return fitz


def open_pdf(path):
    """fitz.Document — 호출자가 닫는다(with 문 권장)."""
    return _fitz().open(path)


def page_count(path):
    try:
        with open_pdf(path) as doc:
            return len(doc)
    except Exception:
        return None


def page_texts(path):
    """쪽별 원본 텍스트 목록."""
    with open_pdf(path) as doc:
        return [p.get_text() for p in doc]


def norm(s):
    """공백 제거 — 조판 결과의 줄바꿈·자간 차이를 무시하고 대조하기 위한 정규화."""
    return re.sub(r"\s+", "", s or "")


# ── 마커 ────────────────────────────────────────────────────────────────
def pages_with_marker(path_or_texts, marker):
    """마커 문자열이 있는 쪽번호(1-based) 목록.

    마커는 **보이지 않게 심은 텍스트**다(흰색·투명). 글자 크기·서체로 특정 면을
    찾던 방식은 정답 면처럼 서체가 다르면 놓쳤다 — 마커는 그런 실패가 없다.
    """
    texts = (path_or_texts if isinstance(path_or_texts, list)
             else page_texts(path_or_texts))
    m = norm(marker)
    return [i + 1 for i, t in enumerate(texts) if m in norm(t)]


def marker_map(path_or_texts, pattern):
    """정규식 마커 → {캡처값: [쪽번호…]} (1-based). 해설 §A12§ 같은 끝 마커용."""
    texts = (path_or_texts if isinstance(path_or_texts, list)
             else page_texts(path_or_texts))
    out = {}
    rx = re.compile(pattern)
    for i, t in enumerate(texts):
        for m in rx.finditer(t):
            out.setdefault(m.group(1), []).append(i + 1)
    return out


# ── 기하 ────────────────────────────────────────────────────────────────
def text_blocks_mm(page):
    """[(x0, y0, x1, y1)] mm — 텍스트 블록 bbox."""
    out = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        out.append(tuple(v / PT for v in b["bbox"]))
    return out


def spans_mm(page):
    """[(text, size_pt, (x0,y0,x1,y1) mm)] — 스팬 단위."""
    out = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        for ln in b["lines"]:
            for sp in ln["spans"]:
                out.append((sp["text"], sp["size"],
                            tuple(v / PT for v in sp["bbox"])))
    return out


def lines_mm(page):
    """[(text, (x0,y0,x1,y1) mm)] — 줄 단위(스팬 합침)."""
    out = []
    for b in page.get_text("dict")["blocks"]:
        if b["type"] != 0:
            continue
        for ln in b["lines"]:
            t = "".join(sp["text"] for sp in ln["spans"])
            out.append((t, tuple(v / PT for v in ln["bbox"])))
    return out


def drawings_mm(page):
    """[(rect mm, fill, color, width)] — 도형. 색면·괘선 검사용.

    ⚠ `get_drawings()` 의 rect 는 **클리핑 전 bbox** 다. "좌표는 맞는데 안 보이는"
    상황이 생기므로 좌표 확인만으로 끝내지 말고 고해상도 렌더로 눈으로 볼 것.
    """
    out = []
    for d in page.get_drawings():
        r = d["rect"]
        out.append(((r.x0 / PT, r.y0 / PT, r.x1 / PT, r.y1 / PT),
                    d.get("fill"), d.get("color"), d.get("width")))
    return out


def ink_bottom(page, top=0.0, bottom=None, include_drawings=True):
    """머리·꼬리를 뺀 띠(top~bottom mm) 안에서 **가장 아래 잉크의 y (mm)**.

    한 면에 한 항목만 조판해 자연 높이를 재는 measure 의 핵심 원자.
    잉크가 없으면 0.0 (빈 면).
    """
    b = float("inf") if bottom is None else bottom
    y = 0.0
    for x0, y0, x1, y1 in text_blocks_mm(page):
        if y0 > top and y1 < b:
            y = max(y, y1)
    if include_drawings:
        for rect, _f, _c, _w in drawings_mm(page):
            if rect[1] > top and rect[3] < b:
                y = max(y, rect[3])
    return y


def blank_pages(path_or_texts, ignore_chars=""):
    """뜻하지 않게 비어 있는 쪽(1-based). ignore_chars 는 머리·꼬리 상투구."""
    texts = (path_or_texts if isinstance(path_or_texts, list)
             else page_texts(path_or_texts))
    rx = re.compile(f"[{re.escape(ignore_chars)}]") if ignore_chars else None
    out = []
    for i, t in enumerate(texts):
        s = norm(t)
        if rx:
            s = rx.sub("", s)
        if len(s) < 4:
            out.append(i + 1)
    return out


def is_left(pageno):
    """쪽번호(1-based) → 왼쪽(짝수) 면인가. 1쪽 = 오른쪽."""
    return pageno % 2 == 0


def boxes(page):
    """PDF 상자 — (MediaBox, CropBox, TrimBox) mm."""
    def r(b):
        return (b.x0 / PT, b.y0 / PT, b.x1 / PT, b.y1 / PT) if b else None
    return r(page.mediabox), r(page.cropbox), r(page.trimbox)
