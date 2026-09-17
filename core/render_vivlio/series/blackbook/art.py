"""간지·MEMO·뒤 간지 — **코드로 만든다.** 인디자인 완성본 PDF 의 면을 빌리지 않는다.

예전에는 `finish.art_pdf`(nhj 맥의 `블랙북_1_v2_9.pdf`)에서 면을 통째로 잘라 끼웠다.
그래서 그 파일이 없는 기기에서는 간지 자리가 빈 채로 나왔고, 뒤 간지에 박힌
"ONLY FOR PAICHAI HIGH SCHOOL" 이 다른 학교 책에도 그대로 들어갔다.

여기서는 같은 네 면을 HTML/CSS 로 그려 `build/art.pdf` 를 만들고, `bleed.finish` 가
그 면들을 끼운다(끼우는 기계는 그대로). 학교 이름은 config 에서 온다.

치수는 인계본 완성 PDF(`배재1_블랙북01_내지_인쇄.pdf`) 1·7·82·116면을 PyMuPDF 로
실측한 값(mm, 도련 포함 216×303 원점). 글자 상자는 PyMuPDF bbox(어센더~디센더)
그대로 두고 `line-height:1` 로 같은 상자를 만든다 — 상자 높이가 글자 크기와 다른
서체(한글)는 그 차이의 절반만큼 top 을 보정한다(`_text`).

art.pdf 면 순서(0부터): FRONT 앞 간지 · MEMO · BACK 뒤 간지 · DIV2 정답 간지(왼쪽 면).
config `finish` 의 `page` 값은 이 순서를 가리킨다.

로고·문장(方牌)·장식은 디자인 폴더 `assets/` 의 png 다(`assets.jobs` 로 완성본에서
한 번 잘라 둔다). 없으면 그 조각만 빠지고 면은 만들어진다.
정답 간지의 흰 문장 워터마크는 완성본에서도 바탕 사각형 **아래에 깔려 안 보이는**
인디자인 잔재라 옮기지 않았다.
"""
import os

from core.render_vivlio import cli

FRONT, MEMO, BACK, DIV2 = 0, 1, 2, 3
PAGES = {"front": FRONT, "memo": MEMO, "back": BACK, "div2": DIV2}

PT_MM = 25.4 / 72.0
INK = "#231f20"          # 본문 먹 (0.137, 0.122, 0.125)
GRAY = "#bcbec0"         # 로고·가는 선 (0.737, 0.744, 0.753)
PANEL = "#c2cfdd"        # 정답 간지 왼쪽 띠 (0.760, 0.814, 0.867)
PANEL2 = "#dee6ee"       # 정답 간지 바탕 (0.871, 0.903, 0.933)
MEMO_INK = "#5ea1d7"     # MEMO 제목
RULE = "#908400"         # 정답 간지 띠 경계의 가는 선 (C0 M3 Y100 K53)
GRID = "#cccccc"         # MEMO 모눈
# 인쇄 CMYK(%) — 완성본 PDF 의 색 연산자 값 그대로(ICC 변환을 타지 않는다)
CMYK = {PANEL: [17, 7, 3, 7], PANEL2: [8.3, 3.4, 1.5, 3.4],
        MEMO_INK: [61, 25, 0, 0], RULE: [0, 3, 100, 53]}
LETTER_PT = 36.0         # BLACK BOOK 세로 글자
LETTER_STEP = 14.82      # 글자 상자 간격(mm)
UNDERLINE_W = 11.93      # 글자 밑줄 길이(mm)

# 서체 — config `fonts` 에 같은 파일명이 있어야 build/fonts 로 들어온다
FONTS = [
    {"family": "Academy", "file": "Academy Engraved LET Fonts.ttf"},
    {"family": "RIDIBatang", "file": "RIDIBatang.otf"},
    {"family": "Jamsil", "file": "The Jamsil OTF 4 Medium.otf"},
    {"family": "PyeongChang", "file": "PyeongChang-Regular.otf"},
    {"family": "PyeongChang", "file": "PyeongChang-Bold.otf", "weight": 700},
]


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# 서체별 세로 보정(mm/pt) — 완성본과 새 PDF 의 잉크 상자를 재서 맞춘 값.
# Academy Engraved 는 어센더 표가 커서 같은 top 에 놓으면 글자가 4.87mm(36pt) 위로 간다.
DY_PER_PT = {"Academy": 0.1353}


def _text(x, y0, h, pt, txt, family, color=INK, extra=""):
    """PyMuPDF 상자(x, y0, 높이 h[mm]) 에 pt 크기 글자를 같은 자리에 놓는다."""
    size = pt * PT_MM
    top = y0 + (h - size) / 2.0 + DY_PER_PT.get(family, 0) * pt
    return (f'<span class="t" style="left:{x:.2f}mm;top:{top:.2f}mm;'
            f'font:{pt:g}pt/1 {family};color:{color};{extra}">{esc(txt)}</span>')


def _letters(word, cx, y0, underline=False):
    """세로로 늘어선 대문자 — 한 글자씩 x 중심 cx 에 가운데 맞춤."""
    o = []
    for i, ch in enumerate(word):
        y = y0 + i * LETTER_STEP
        o.append(f'<span class="t L" style="left:{cx - 10:.2f}mm;'
                 f'top:{y + DY_PER_PT["Academy"] * LETTER_PT:.2f}mm">{ch}</span>')
        if underline:
            o.append(f'<i class="ul" style="left:{cx - UNDERLINE_W / 2:.2f}mm;'
                     f'top:{y + LETTER_PT * PT_MM + 0.06:.2f}mm"></i>')
    return "".join(o)


def _img(name, x, y, w, h, assets):
    """디자인 자산 png — 없으면 빈 자리."""
    if name not in assets:
        return ""
    return (f'<img src="assets/{name}.png" style="left:{x:.2f}mm;top:{y:.2f}mm;'
            f'width:{w:.2f}mm;height:{h:.2f}mm">')


def _cover(cfg):
    """간지 글귀 — config `cover`, 없으면 `book` 에서 짐작."""
    cov = cfg.section("cover") or {}
    book = cfg.book
    school = cov.get("school_ko") or "".join(
        ch for ch in (book.get("school") or "") if not ch.isdigit()).strip()
    return {
        "title": cov.get("title") or book.get("title", "블랙북").split()[0],
        "word": cov.get("word") or ["BLACK", "BOOK"],
        "school_ko": school,
        "school_en": cov.get("school_en") or "",
        "line": cov.get("line") or (f"오직 {school}만을 위한 데일리 학습서" if school else ""),
        "slogan": cov.get("slogan") or "최소시간 x 최대학습",
        "ghost": cov.get("ghost_color") or "#f6fbfe",   # 완성본대로 — 흰 바탕에 거의 안 보이는 글귀
    }


def front_html(cov, assets):
    w1, w2 = cov["word"][0], cov["word"][1] if len(cov["word"]) > 1 else ""
    o = ['<section class="pg front">',
         # 이중 테두리 — 바깥 (67.09,37.78)-(148.99,235.87) · 안쪽 (70.61,41.31)-(145.47,232.34)
         '<i class="fr" style="left:67.09mm;top:37.78mm;width:81.90mm;height:198.09mm"></i>',
         '<i class="fr" style="left:70.61mm;top:41.31mm;width:74.86mm;height:191.03mm"></i>',
         # 제목 — 테두리 윗선 위에 흰 바탕을 깔고 "✦ 블랙북 ✦"
         '<i class="knock" style="left:90.5mm;top:36.5mm;width:35mm;height:7.2mm"></i>',
         _img("art_orn", 93.27, 38.10, 3.43, 3.43, assets),
         _text(99.45, 36.85, 6.44, 15, cov["title"], "RIDIBatang", INK, "letter-spacing:1.06mm"),
         _img("art_orn", 119.45, 38.10, 3.43, 3.43, assets),
         _letters(w1, 108.0, 52.49),
         '<i class="vl" style="left:108.04mm;top:127.69mm;height:9.43mm"></i>',
         _img("art_emblem", 96.06, 138.48, 25.15, 16.54, assets),
         '<i class="vl" style="left:108.04mm;top:154.91mm;height:9.43mm"></i>',
         _letters(w2, 108.0, 162.58),
         ]
    if cov["line"]:
        o.append(_text(77.02, 242.93, 5.14, 12, cov["line"], "RIDIBatang", cov["ghost"],
                       "left:0;width:216mm;text-align:center"))
    if cov["slogan"]:
        o.append(_text(90.11, 255.92, 3.89, 10, cov["slogan"], "Jamsil", cov["ghost"],
                       "left:0;width:216mm;text-align:center"))
    o.append(_img("art_logo", 97.80, 275.21, 21.56, 5.52, assets))
    o.append('</section>')
    return "".join(o)


def memo_html():
    return ('<section class="pg memo">'
            '<i class="tab"></i>'
            '<span class="t mt" style="left:0;top:18.04mm;width:216mm;text-align:center">'
            '<span class="bar">|</span>&nbsp; M E M O &nbsp;<span class="bar">|</span></span>'
            '</section>')


def back_html(cov, assets):
    w1, w2 = cov["word"][0], cov["word"][1] if len(cov["word"]) > 1 else ""
    o = ['<section class="pg back">',
         _letters(w1, 29.08, 39.75, underline=True),
         _letters(w2, 187.12, 201.84, underline=True)]
    if cov["school_en"]:
        o.append(_text(0, 264.01, 3.53, 10, f"ONLY FOR {cov['school_en']} HIGH SCHOOL",
                       "Academy", INK, "width:220mm;text-align:center"))
    o.append(_img("art_logo_back", 93.06, 275.17, 29.56, 5.97, assets))
    o.append('</section>')
    return "".join(o)


def div2_html(cov, assets):
    w1, w2 = cov["word"][0], cov["word"][1] if len(cov["word"]) > 1 else ""
    return ('<section class="pg div2">'
            '<i class="band"></i><i class="rule"></i>'
            + _letters(w1, 39.02, 24.18, underline=True)
            + _letters(w2, 38.92, 102.91, underline=True)
            + '</section>')


def css(pw, ph):
    ff = "\n".join(
        f'@font-face{{font-family:{f["family"]};'
        + (f'font-weight:{f["weight"]};' if f.get("weight") else "")
        + f'src:url("fonts/{f["file"]}");}}' for f in FONTS)
    return f"""{ff}
@page {{ size: {pw}mm {ph}mm; margin: 0; }}
html, body {{ margin:0; padding:0; }}
.pg {{ position:relative; width:{pw}mm; height:{ph}mm; overflow:hidden; break-after:page; background:#fff; }}
.pg:last-child {{ break-after:auto; }}
.t {{ position:absolute; white-space:nowrap; }}
.L {{ width:20mm; text-align:center; font:{LETTER_PT:g}pt/1 Academy; color:{INK}; }}
.ul {{ position:absolute; width:{UNDERLINE_W}mm; height:0; border-top:0.35mm solid {INK}; }}
.fr {{ position:absolute; box-sizing:border-box; border:0.35mm solid {INK}; }}
.vl {{ position:absolute; width:0; border-left:0.35mm solid {GRAY}; }}
img {{ position:absolute; }}
.knock {{ position:absolute; background:#fff; }}
.memo {{ background:
  linear-gradient(to right, {GRID} 0.2mm, transparent 0.2mm) 2.96mm 0 / 5.53mm 100% repeat-x,
  linear-gradient(to bottom, {GRID} 0.2mm, transparent 0.2mm) 0 4.91mm / 100% 5.53mm repeat-y,
  #fff; }}
.memo .tab {{ position:absolute; left:0; top:0; width:3mm; height:23mm; background:{PANEL}; }}
.mt {{ font:700 9pt/1 PyeongChang; color:{MEMO_INK}; letter-spacing:0.12em; }}
.mt .bar {{ font:400 10pt/1 PyeongChang; }}
.div2 {{ background:{PANEL2}; }}
.div2 .band {{ position:absolute; left:0; top:0; width:70mm; height:{ph}mm; background:{PANEL}; }}
.div2 .rule {{ position:absolute; left:73.5mm; top:0; height:{ph}mm; width:0; border-left:0.35mm solid {RULE}; }}
"""


def html(cfg, assets):
    pg = cfg.page
    pw = pg["width"] + 2 * pg["bleed"]
    ph = pg["height"] + 2 * pg["bleed"]
    cov = _cover(cfg)
    body = "".join([front_html(cov, assets), memo_html(), back_html(cov, assets), div2_html(cov, assets)])
    return (f'<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>art</title>'
            f'<style>{css(pw, ph)}</style></head><body>{body}</body></html>')


def build(cfg, build_dir, log=print):
    """→ build/art.pdf. 서체·자산은 `_stage` 가 이미 build_dir 에 놓았다."""
    adir = os.path.join(build_dir, "assets")
    assets = {os.path.splitext(f)[0] for f in os.listdir(adir)} if os.path.isdir(adir) else set()
    hp = os.path.join(build_dir, "art.html")
    with open(hp, "w", encoding="utf-8") as f:
        f.write(html(cfg, assets))
    out = os.path.join(build_dir, "art.pdf")
    secs = cli.run_build(hp, out, log=log, extra=["-f", "pdf"], final=False)
    miss = [n for n in ("art_emblem", "art_orn", "art_logo", "art_logo_back") if n not in assets]
    log(f"[간지] art.pdf {secs:.1f}s — 앞·MEMO·뒤·정답 4면"
        + (f" · 자산 없음: {', '.join(miss)}" if miss else ""))
    return out
