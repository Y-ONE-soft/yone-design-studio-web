# -*- coding: utf-8 -*-
import re
"""포켓북 **간지**(첫 면 · 마지막 면) — 표지 느낌으로, 간단하게.

표지(`디자인/표지/2026_리뉴얼_…/광문1_포켓북_표지.pdf`)를 그대로 베끼지 않는다.
표지는 굵은 3D 오브제와 큰 `2026` 이 들어가 화려한데, 간지는 **책을 여는 숨** 이라
같은 공기만 나눠 갖고 조용해야 한다(사용자 지시: "표지랑 완전 똑같이가 아니라
표지 느낌과 비슷하게 간단하게").

표지에서 가져오는 것:
    · 민트 그러데이션 바탕
    · 자주색 `POCKET` 소제목 + 가는 밑줄
    · 짙은 녹색 세리프 `Pocket Book.`
    · 아래쪽 테두리 띠 — 학교 이름 · 시험 이름
    · 로고 자리

가져오지 않는 것: 3D 리본, 큰 `2026`, 옆구리 탭. 간지가 표지를 흉내 내면
책을 펼쳤을 때 표지를 두 번 보는 꼴이 된다.

⚠ 판형은 본문과 같아야 한다(도련 포함 154×216). 표지 PDF 는 437×612pt
  (154.2×216mm) 라 사실상 같지만, 여기서는 **본문 치수를 그대로 쓴다** —
  섞으면 마지막 면만 0.2mm 어긋난다.
"""

# 표지에서 뽑은 색
INK = {
    "bg_top": "#DFF2E8",       # 민트 그러데이션 위
    "bg_bottom": "#CFEADF",    # 아래
    "plum": "#7B2E86",         # POCKET · 테두리 · 학교 이름
    "forest": "#1E4D3B",       # Pocket Book.
    "slate": "#4A6B60",        # 부제 · 시험 이름
    "rule": "#B58BC0",
}

CSS = """
.cvr{position:relative;width:__media_w__;height:__media_h__;overflow:hidden;
  background:__bg_top__;
  font-family:PBBody,sans-serif;break-after:page}
/* ⚠ 표지에 없는 그러데이션을 지어 넣지 않는다 — 표지 짜임 그대로다. 한 색
   표지는 평평하게, 두 색 표지(광문2)는 표지와 같은 높이에서 아래 블록이
   시작한다. **평평한 채움**이어야 인쇄본에서 표지 CMYK 로 못 박힌다
   (그러데이션은 ICC 로 다시 바뀌어 광문1 이 표지보다 분홍빛으로 나갔다). */
.cvr::before{content:"";position:absolute;left:0;right:0;bottom:0;
  top:__split__;background:__bg_bottom__}
.cvr .in{position:absolute;left:__pad__;right:__pad__;top:0;bottom:0}
.cvr .kicker{position:absolute;top:__kick_y__;left:0;font-size:7.5pt;
  font-weight:700;letter-spacing:.42em;color:__plum__}
.cvr .krule{position:absolute;top:__rule_y__;left:0;right:0;height:0;
  border-top:.5pt solid __rule__}
.cvr .ttl{position:absolute;top:__ttl_y__;left:0;font-family:PBTitle,serif;
  font-size:__ttl_size__;line-height:1.02;color:__forest__;letter-spacing:-.01em}
.cvr .sub{position:absolute;top:__sub_y__;left:0;font-size:8pt;font-weight:700;
  letter-spacing:.18em;color:__slate__}
.cvr .bar{position:absolute;left:0;right:0;bottom:__bar_y__;height:__bar_h__;
  border:.7pt solid __plum__;border-radius:1.2mm;display:flex;
  align-items:center;justify-content:space-between;padding:0 3.5mm;
  box-sizing:border-box}
.cvr .bar b{font-size:10pt;color:__plum__;font-weight:700}
.cvr .bar span{font-size:7.5pt;color:__slate__}
.cvr .logo{position:absolute;left:0;bottom:__logo_y__;font-size:7pt;
  letter-spacing:.05em;color:__slate__;font-weight:700}
/* 마지막 면 — 만든 사람들. 표지와 같은 공기에서 조용히 */
.cvr .credit{position:absolute;left:0;right:0;top:__cred_y__;
  display:flex;flex-wrap:wrap;gap:__cred_row__ __cred_gap__;
  align-items:flex-start}
.cvr .credit section{width:__cred_col__}
.cvr .credit h4{margin:0 0 1.2mm;font-family:PBTitle,serif;font-size:9pt;
  color:__forest__;font-weight:700}
.cvr .credit p{margin:0 0 .6mm;font-size:7.5pt;color:__slate__}
"""

# 정본은 워크북 D버전 `LastP.pdf` 의 명단이다 — 차례까지 그대로 따른다.
CREDITS = [
    ("Writer", ["노윤기", "신현규", "이재훈", "윤지수", "안재희", "김지윤"]),
    ("Teacher", ["함태환", "송아영", "박세희", "표슬미", "김태림", "이우솔",
                 "정다니엘", "최아인"]),
    ("Assistant", ["박소원", "전민정", "정우주"]),
    ("Design", ["노혜진"]),
    ("Production", ["서동일", "김완중"]),
]


def _hex3(c):
    return "#%02X%02X%02X" % tuple(round(max(0.0, min(1.0, x)) * 255)
                                   for x in c[:3])


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _mix(a, b, t):
    """a 에서 b 쪽으로 t 만큼(0~1)."""
    x, y = _rgb(a), _rgb(b)
    return "#%02X%02X%02X" % tuple(round(x[i] + (y[i] - x[i]) * t)
                                   for i in range(3))


def _lum(h):
    r, g, b = _rgb(h)
    return 0.299 * r + 0.587 * g + 0.114 * b


def _cmyk_ops(page):
    """면 내용에 쓰인 채움 CMYK 값(0~1) — 나온 차례대로, 겹치지 않게."""
    raw = page.read_contents().decode("latin-1", "replace")
    out = []
    for m in re.finditer(r"(?<![\w.])([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)"
                         r"\s+k(?![A-Za-z])", raw):
        v = tuple(float(x) for x in m.groups())
        if v not in out:
            out.append(v)
    return out


def _shown(vals):
    """CMYK 값들 → 표지를 그릴 때와 **같은 방식**으로 그린 화면색(sRGB)."""
    import fitz
    if not vals:
        return []
    doc = fitz.open()
    pg = doc.new_page(width=10, height=10 * len(vals))
    for i, v in enumerate(vals):
        pg.draw_rect(fitz.Rect(0, 10 * i, 10, 10 * i + 10), color=None, fill=v)
    px = pg.get_pixmap(dpi=72)
    return ["#%02X%02X%02X" % px.pixel(5, 10 * i + 5)[:3] for i in range(len(vals))]


def _dist(a, b):
    x, y = _rgb(a), _rgb(b)
    return max(abs(x[i] - y[i]) for i in range(3))


def ink_from_cover(pdf):
    """**그 학교 표지 PDF** 에서 간지 색을 뽑는다 → `INK` 꼴 dict, 못 읽으면 None.

    간지는 표지를 따라 학교마다 색이 달라야 한다(사용자 지적 — 광문1·2 가
    같은 민트로 나갔다). 색표를 따로 적으면 표지를 고칠 때마다 두 벌이 어긋나므로
    표지에서 바로 읽는다.

    ⚠ **벡터 값을 그대로 쓰면 안 된다.** 표지는 CMYK 다(`0 .114 .169 .071 k`).
      PyMuPDF 가 돌려주는 채움값은 그걸 거칠게 RGB 로 바꾼 것이라(`#ECD4C2`)
      실제 보이는 색(`#F1E0CD`)보다 분홍빛이 돈다 — 간지가 표지와 달라졌다
      (사용자 지적). 그래서 **그린 모양에서** 바탕·제목 색을 읽고, 그 색을 낸
      표지의 **CMYK 연산을 그대로** 짝지어 둔다(인쇄본에서 같은 잉크로 찍으려고).
    ⚠ 한 색 표지는 **평평하게** 둔다. 없는 그러데이션을 지어 넣지 않는다.
    """
    try:
        import fitz
        doc = fitz.open(pdf)
        pg = doc[0]
    except Exception:
        return None
    W, H = pg.rect.width, pg.rect.height
    # ① 바탕 — 그려진 면에서 넓게 차지한 색
    px = pg.get_pixmap(dpi=24)
    from collections import Counter
    cnt = Counter("#%02X%02X%02X" % px.pixel(x, y)[:3]
                  for y in range(px.height) for x in range(px.width))
    tot = px.width * px.height
    fills = []
    for h, n in cnt.most_common(12):
        if n / tot < 0.12:
            break
        if all(_dist(h, f) > 6 for f in fills):
            fills.append(h)
    if not fills:
        doc.close()
        return None
    # ② 제목 — 큰 글자 자리를 곱게 그려 바탕이 아닌 가장 흔한 색
    boxes = [fitz.Rect(sp["bbox"]) for b in pg.get_text("dict")["blocks"]
             for ln in b.get("lines", ()) for sp in ln["spans"]
             if sp["text"].strip() and sp["size"] > 18]
    ink = None
    if boxes:
        clip = boxes[0]
        for r in boxes[1:]:
            clip |= r
        tp = pg.get_pixmap(dpi=150, clip=clip)
        tc = Counter("#%02X%02X%02X" % tp.pixel(x, y)[:3]
                     for y in range(tp.height) for x in range(tp.width))
        for h, _n in tc.most_common(40):
            if all(_dist(h, f) > 40 for f in fills):
                ink = h
                break
    ops = _cmyk_ops(pg)
    doc.close()
    if not ink:
        return None
    # ③ 보이는 색 ↔ 표지의 CMYK 연산 짝짓기 — **가장 가까운 것**.
    # ⚠ 새 면에 그려 본 CMYK 색은 표지를 그린 색과 몇 단계 어긋난다(투명 그룹·
    #   겹침 설정 차이) — 6 이내로 묶었더니 광문1·상일1·강동2 가 하나도 안
    #   짝지어졌다. 표지의 CMYK 연산은 몇 개뿐이고 서로 멀리 떨어져 있어(바탕 ·
    #   제목 · 부제 · 로고) 가장 가까운 것이 곧 그 색이다. 40 넘게 멀면 버린다.
    # 열쇠는 **보이는 색**이다 — 간지가 화면에 그리는 바로 그 색이라 인쇄 고정표가 걸린다.
    shown = _shown(ops)
    cmyk = {}
    for want in fills + [ink]:
        best = min(zip(shown, ops), key=lambda so: _dist(so[0], want),
                   default=None)
        if best and _dist(best[0], want) <= 40:
            cmyk[want] = [round(v * 100, 1) for v in best[1]]
    split = None
    if len(fills) >= 2:                  # 위 바탕 + 아래 블록(광문2 형)
        paper, block = sorted(fills[:2], key=_lum, reverse=True)
        # 글자가 없는 왼쪽 가장자리 세로줄을 위에서부터 훑어 블록이 시작하는
        # 줄을 찾는다(끝까지 블록 색이 이어지는 첫 줄).
        col = [px.pixel(max(1, px.width // 20), y)[:3] for y in range(px.height)]
        col = ["#%02X%02X%02X" % c for c in col]
        for y in range(px.height):
            if all(_dist(c, block) <= 8 for c in col[y:]):
                split = y / float(px.height)
                break
    else:                                # 한 색 표지 — 평평하게
        paper = block = fills[0]
    return {
        "bg_top": paper, "bg_bottom": block,
        "plum": ink,                                  # POCKET · 테두리 · 학교
        "forest": ink,                                # Pocket Book.
        "slate": _mix(ink, "#3A3A3A", 0.35),          # 부제·시험·명단 — 읽히게
        "rule": _mix(ink, block, 0.55),
        "cmyk": cmyk,                                 # 인쇄본에서 표지와 같은 잉크로
        "split": split,                               # 아래 블록 시작(두 색 표지만)
    }


def _tok(css, **kw):
    for k, v in kw.items():
        css = css.replace("__%s__" % k, str(v))
    return css


def css(M, ink=None):
    """간지 CSS. 본문과 같은 판형·도련을 쓴다. `ink` 로 학교 표지 색을 덮는다."""
    bl = M["bleed"]
    tok = dict(INK, **(ink or {}))
    sp = tok.pop("split", None)          # 아래 블록이 시작하는 높이(0~1)
    tok.pop("cmyk", None)                # 인쇄 고정표 — CSS 에는 안 쓴다
    return _tok(CSS,
                media_w="%gmm" % (M["page_w"] + 2 * bl),
                media_h="%gmm" % (M["page_h"] + 2 * bl),
                pad="%gmm" % (M["margin_l"] + bl),
                kick_y="%gmm" % (bl + 22.0),
                rule_y="%gmm" % (bl + 27.5),
                ttl_y="%gmm" % (bl + 46.0),
                ttl_size="34pt",
                sub_y="%gmm" % (bl + 78.0),
                bar_y="%gmm" % (bl + 24.0),
                bar_h="8.5mm",
                logo_y="%gmm" % (bl + 12.0),
                # 명단이 다섯 갈래(20명)라 두 단으로 세 줄이 된다 —
                # 96mm 에서 시작하면 마지막 줄이 아래 띠에 닿았다.
                cred_y="%gmm" % (bl + 82.0),
                cred_gap="9mm", cred_row="7mm",
                cred_col="34mm",
                split=("%.2f%%" % (sp * 100)) if sp else "100%",
                **tok)


def first_page(school="", term=""):
    """첫 면 — 표지의 공기만 남긴 조용한 속표지."""
    return (
        '<section class="cvr"><div class="in">'
        '<div class="kicker">POCKET</div><div class="krule"></div>'
        '<div class="ttl">Pocket<br>Book.</div>'
        '<div class="sub">포켓북 · 핵심 암기 노트</div>'
        '<div class="bar"><b>%s</b><span>%s</span></div>'
        '<div class="logo">세희영어연구소 · 각인Books</div>'
        '</div></section>' % (_esc(school), _esc(term)))


def last_page(school="", term=""):
    """마지막 면 — 만든 사람들. 지금 쓰는 판권면과 같은 내용이다."""
    cols = "".join(
        '<section><h4>%s</h4>%s</section>'
        % (_esc(t), "".join("<p>%s</p>" % _esc(n) for n in names))
        for t, names in CREDITS)
    return (
        '<section class="cvr"><div class="in">'
        '<div class="kicker">POCKET</div><div class="krule"></div>'
        '<div class="ttl">Pocket<br>Book.</div>'
        '<div class="credit">%s</div>'
        '<div class="bar"><b>%s</b><span>%s</span></div>'
        '<div class="logo">COPYRIGHT ⓒ 2026 GAKINBOOKS</div>'
        '</div></section>' % (cols, _esc(school), _esc(term)))


def _esc(s):
    import html
    return html.escape(str(s or ""))


def term_text(term):
    """`26-2-중간` → `2학기 중간고사` (표지가 쓰는 말)."""
    import re
    m = re.match(r"^\d{2}-(\d)-(중간|기말)$", str(term or ""))
    if not m:
        return str(term or "")
    return "%s학기 %s고사" % (m.group(1), m.group(2))
