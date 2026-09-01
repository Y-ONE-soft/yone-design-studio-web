"""빈 지면 → MEMO 면.

지면이 흐르다 보면 머리말만 남고 판면이 비는 면이 생긴다. 그대로 두면 "조판이
덜 된 면"으로 보이므로 **MEMO 면**으로 쓴다(사용자 규칙).

면 수는 조판이 끝나야 알 수 있어서 HTML 단계에서는 못 만든다. 그래서 마감에서
PDF 를 열어 **판면에 잉크가 없는 면**을 찾아 그 위에 MEMO 판을 얹는다.
머리말·꼬리말·사이드 탭은 그대로 둔다 — 그 면이 어느 스텝인지 알아야 하니까.

⚠ MEMO 판의 생김새는 완성본에 전례가 없다(워크북 165권을 훑어 MEMO 면 0건).
   지금은 책의 토큰(스텝 색·괘선 색)만 써서 절제해서 그렸다 — **디자인 확정 전**
   이므로 사용자 승인을 받고 고칠 것.
"""
import os

MM = 72 / 25.4

BODY_TOP = 34.0        # 판면 위 (머리말 26.5 + 여유)
BODY_BOTTOM = 276.0
BODY_LEFT = 23.0
BODY_RIGHT = 191.0
LINE_PITCH = 9.0       # 메모 괘선 간격


def _fitz():
    try:
        import pymupdf as f
    except ImportError:
        import fitz as f
    return f


def empty_body_pages(pdf, top=30.0, bottom=280.0):
    """판면에 글자도 큰 색면도 없는 면(1-based). 간지는 뺀다."""
    fitz = _fitz()
    doc = fitz.open(pdf)
    out = []
    for i in range(doc.page_count):
        pg = doc[i]
        # ⚠ 사이드 탭(오른쪽 끝 세로 글자)은 본문이 아니다 — x 로 걸러야 한다.
        #   안 그러면 판면이 빈 면도 '내용 있음' 으로 잡힌다(실측).
        has_text = any(
            top < l["bbox"][1] / MM < bottom and l["bbox"][0] / MM < 195
            for b in pg.get_text("dict")["blocks"] if b.get("type") == 0
            for l in b["lines"])
        big = False
        for dr in pg.get_drawings():
            r = dr["rect"]
            f = dr.get("fill")
            if f and min(f[:3]) < 0.93 and r.width / MM > 150 and r.height / MM > 150:
                big = True
                break
        if not has_text and not big:
            out.append(i + 1)
    doc.close()
    return out


def apply(pdf, pages, step_color=(0.47, 0.63, 0.77), rule=(0.71, 0.67, 0.60),
          font=None, log=None):
    """`pages` 면에 MEMO 판을 얹는다. 제자리 저장."""
    fitz = _fitz()
    doc = fitz.open(pdf)
    n = 0
    for p in pages:
        if p < 1 or p > doc.page_count:
            continue
        pg = doc[p - 1]
        kw = {}
        if font and os.path.exists(font):
            kw = {"fontfile": font, "fontname": "memoft"}
        try:
            pg.insert_text((BODY_LEFT * MM, (BODY_TOP + 4) * MM), "M E M O",
                           fontsize=11, color=step_color, **kw)
        except Exception:
            pg.insert_text((BODY_LEFT * MM, (BODY_TOP + 4) * MM), "M E M O",
                           fontsize=11, color=step_color)
        y = BODY_TOP + 12
        while y < BODY_BOTTOM:
            pg.draw_line((BODY_LEFT * MM, y * MM), (BODY_RIGHT * MM, y * MM),
                         color=rule, width=0.3, dashes="[1 2] 0")
            y += LINE_PITCH
        n += 1
    if n:
        doc.saveIncr()
    doc.close()
    if log:
        log(f"  [MEMO] 빈 지면 {n}개를 메모 면으로 — {pages}")
    return n
