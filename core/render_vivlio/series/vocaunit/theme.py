"""UNIT형 단어장 테마 생성 — 팔레트/치수(③) + 계열 스타일시트(②) → build/theme.css.

치수는 전부 **재단선 기준 mm** 다. 도련은 "옮기는 게 아니라 늘리는 것"이라
(→ `docs/vivliostyle_엔진.md`) 여백에 도련을 더하고, 재단선에 닿는 색면만 도련만큼
더 그린다. 원본 완성본 PDF(광문1_광문보카_내지(샘플).pdf)에서 실측한 값이
`DEFAULT_METRICS` 이고, 책이 다르면 config 의 `metrics` 로 덮는다.

도형은 예외 없이 배경 SVG 다(마진 박스 제약 → `core/render_vivlio/svg.py` 주석).
글자가 들어가는 도형만 "배경 SVG + 러닝 요소 글자"로 나눈다.

4면 체계
  ① Unit 시작(왼쪽) = 모눈 헤더 + 큰 원 + UNIT NN     ← 인플로우 `.unit-head`
  ② 이어지는 오른쪽 = 모눈 헤더 + 로고                ← 2패스 `@page :nth()`
  ③ 이후 왼쪽       = 상단 띠 + 둥근 탭(UNIT NN)
  ④ 이후 오른쪽     = 상단 띠 + 로고
"""
import os

from core.render_vivlio import svg
from core.render_vivlio.series.vocaunit import art

HERE = os.path.dirname(os.path.abspath(__file__))
THEME_SRC = os.path.join(os.path.dirname(os.path.dirname(HERE)),
                         "themes", "vocaunit.css")
ASSETS_SRC = os.path.join(os.path.dirname(os.path.dirname(HERE)),
                          "assets", "vocaunit")

# 계열 기본 치수 — 광문보카 완성본 실측(재단선 기준 mm). config `metrics` 로 덮는다.
DEFAULT_METRICS = {
    "mgn_out": 15.0,        # 바깥(책배) 여백
    "mgn_in": 18.0,         # 안쪽(책등) 여백
    "margin_top": 20.09,    # ③④ 본문 상단
    "margin_top_open": 25.09,   # ①② 모눈 헤더 면의 본문 상단
    "margin_bottom": 17.0,

    "col_w": 43.33,         # 표제어 열
    "col_gap": 0.95,        # 뜻 열 왼쪽 안여백

    "band_h": 3.75,         # 위·아래 띠(재단선 안쪽 높이)
    "band_rule": 0.353,     # 띠 안쪽 가장자리 1pt 선

    "grid_h": 20.0,         # ①② 모눈 헤더 높이(재단선 기준)
    "grid_pitch": 2.794,
    "grid_width": 0.11,   # 완성본의 잉크량에 맞춘 값(더 얇으면 인쇄에서 날아간다)

    "tab": {"x": 14.0, "y": 3.2, "w": 29.15, "h": 10.65, "r": 3.0},
    "circle": {"cx": 37.13, "cy": -7.06, "r": 25.29},

    "logo": {"crest_w": 10.753, "crest_h": 9.941,
             "crest_right": 9.935, "crest_top": 6.598,   # 재단선 기준
             "pill_w": 8.8, "pill_h": 3.0,
             "pill_right": 10.7, "pill_top": 10.55,
             "text_right": 21.29, "text_top": 10.93,
             "text_size": 7.0, "track": 0.109},

    # MEMO 탭 — 오른쪽은 **도련 끝에 붙는다**(재단 후 페이지 밖으로 나감)
    "memo": {"w": 11.8, "h": 23.9, "right": 0.0, "top": 26.48},

    # 항목(표제어 블록) 세로 리듬 — 완성본 베이스라인 실측에서 역산한 CSS 값
    "rule_w": 0.176,        # 괘선 0.5pt
    "w_pad_t": 2.05,
    "w_pad_b": 3.84,
    "no_w": 4.73,           # 번호 열 폭(회독칸 시작점을 고정한다)
    "chk": 1.82, "chk_gap": 0.73, "chk_mt": 0.25,
    "word_mt": 1.15, "pron_mt": 0.84,
    "deriv_mt": 1.37, "deriv_lh": 4.18,
    "def_slot": 11.0, "def_lh": 4.23, "def_hang": 3.75, "def_mb": 1.06,
    # 품사 네모 배지 (라인형)
    "pos_box": 2.75, "pos_gap": 1.0, "pos_size": 5.2, "pos_r": 0.5,
    "pos_va": 0.45, "pos_va_deriv": 0.22, "pos_line_w": 0.15,
    "en_lh": 3.39, "kr_lh": 3.52, "kr_mt": 0.94, "pair_mt": 2.62,

    "tab_txt_mt": 9.21,     # ③ 탭 글자
    # ① 헤더 글자는 `.unit-head` 안(=페이지 왼쪽 위 원점)이라 **도련 포함 좌표**다
    "unit_ttl": {"x": 27.52, "y": 8.40},        # "UNIT"
    "unit_num": {"x": 40.01, "y": 8.06},        # 큰 번호
    "cover": {"mark_x": 44.18, "mark_y": 66.99, "mark_w": 67.36, "mark_h": 62.275,
              "ttl_x": 31.95, "ttl_y": 135.39, "ttl_size": 30, "ttl_track": -0.035},
    # 판권면(맨 뒤) — 완성본 66쪽 실측. 좌표는 페이지 왼쪽 위(도련 포함) 원점.
    "colophon": {"mark_x": 17.997, "mark_y": 186.999,
                 "mark_w": 27.843, "mark_h": 5.197,
                 "txt_x": 18.0, "txt_y": 195.579, "txt_size": 6.6},

    "pg_out": 5.33,         # 쪽번호 — 판면 바깥쪽으로 내미는 양
    "pg_mt": 5.50,
    "tight": "-.005em",
}


def metrics_of(cfg):
    m = {k: (dict(v) if isinstance(v, dict) else v)
         for k, v in DEFAULT_METRICS.items()}
    for k, v in (cfg.section("metrics") or {}).items():
        if isinstance(v, dict) and isinstance(m.get(k), dict):
            m[k].update(v)
        else:
            m[k] = v
    return m


def _c(cfg, key, default=""):
    return (cfg.section("palette") or {}).get(key, default)


# ── 대단원별 팔레트 ─────────────────────────────────────────────────────
# 색상만 돌리는 키 = "분홍 계열" 전부. 버터(큰 원·둥근 탭)와 연하늘(크레스트·
# MEMO 탭), 예문 강조 주황, 무채색은 대단원이 바뀌어도 그대로 둔다 — 그래야
# 지면이 "같은 책의 다른 단원"으로 읽히지, 다른 책처럼 보이지 않는다.
HUE_KEYS = ("accent", "sense", "rule", "chk", "band", "rule2", "logo", "pill",
            "unitnum", "grid", "cover_bg", "mark", "headtxt")


def part_palettes(cfg):
    """{대단원 번호: 팔레트}. 색상각(`parts[].hue`)이 없으면 기본 팔레트 그대로."""
    from core.render_vivlio import color

    base = cfg.section("palette") or {}
    parts = cfg.section("parts") or []
    if not parts:
        return {1: base}
    base_hue = parts[0].get("hue")
    out = {}
    for i, spec in enumerate(parts, 1):
        hue = spec.get("hue")
        if hue is None or hue == base_hue:
            out[i] = dict(base)
            continue
        pal = dict(base)
        for k in HUE_KEYS:
            if isinstance(base.get(k), str) and base[k].startswith("#"):
                pal[k] = color.rotate(base[k], hue)
        out[i] = pal
    return out


# ── 배경 SVG ────────────────────────────────────────────────────────────
def band(pale, rule, PW, h, rule_h, bleed, at_top=True):
    """위/아래 띠 — 재단선 밖(도련)까지 채우고, 안쪽 가장자리에 1pt 선."""
    H = h + bleed
    if at_top:                      # 띠는 페이지 위 → 선은 아래 가장자리
        body = svg.rect(0, 0, PW, H - rule_h, pale) + \
            svg.rect(0, H - rule_h, PW, rule_h, rule)
    else:                           # 아래 띠 → 선은 위 가장자리
        body = svg.rect(0, rule_h, PW, H - rule_h, pale) + \
            svg.rect(0, 0, PW, rule_h, rule)
    return svg.data_uri(PW, H, body)


def grid(color, PW, h, pitch, width, bleed, phase_right=False):
    """①② 모눈 헤더 — 위상은 **책등 쪽 재단선**에 맞춘다(펼침면에서 이어지도록).
    왼쪽 면은 책등이 오른쪽이므로 오른쪽 재단선부터, 오른쪽 면은 왼쪽부터."""
    H = h + bleed
    body, ys = [], []
    for i in range(int(H / pitch) + 2):
        y = round(bleed + i * pitch, 3)
        if 0 <= y <= H:
            ys.append(y)
            body.append(svg.line(0, y, PW, y, color, width))
    # ⚠ 세로선을 상자 끝(H)까지 그리면 **마지막 가로선 아래로 꼬리가 삐져나온다**
    #    (칸 크기가 높이를 딱 나누지 않으므로). 마지막 가로선에서 끊는다.
    bottom = ys[-1] if ys else H
    n = int(PW / pitch) + 2
    for i in range(n):
        x = round((PW - bleed - i * pitch) if phase_right else (bleed + i * pitch), 3)
        if 0 <= x <= PW:
            body.append(svg.line(x, 0, x, bottom, color, width))
    return svg.data_uri(PW, H, "".join(body))


def grid_full(color, PW, PH, pitch, width, bleed=0.0, phase_right=False):
    """MEMO 면 전면 모눈 — 위상은 재단선 기준(원본과 같은 자리에 선이 오게)."""
    body = []
    for i in range(int(PH / pitch) + 2):
        y = round(bleed + i * pitch, 3)
        if 0 <= y <= PH:
            body.append(svg.line(0, y, PW, y, color, width))
    n = int(PW / pitch) + 2
    for i in range(n):
        x = round((PW - bleed - i * pitch) if phase_right else (bleed + i * pitch), 3)
        if 0 <= x <= PW:
            body.append(svg.line(x, 0, x, PH, color, width))
    return svg.data_uri(PW, PH, "".join(body))


def tab(main, t, bleed, mirror=False):
    """③ 둥근 탭 — 위 모서리는 각지고 아래만 둥글다(띠에서 흘러내린 모양)."""
    W, H = t["w"] + 2, t["h"] + 2
    x, y, w, h, r = 1.0, 1.0, t["w"], t["h"], t["r"]
    d = (f"M{x} {y} L{x + w} {y} L{x + w} {y + h - r} "
         f"C{x + w} {y + h - r * .45:.3f} {x + w - r * .45:.3f} {y + h} "
         f"{x + w - r} {y + h} L{x + r} {y + h} "
         f"C{x + r * .45:.3f} {y + h} {x} {y + h - r * .45:.3f} {x} {y + h - r} Z")
    body = svg.path(d, fill=main)
    if mirror:
        body = svg.mirror(body, W)
    return svg.data_uri(W, H, body)


def circle(main, c, bleed, PW):
    """① 큰 원 — 재단선 위로 넘어간다. 박스는 도련까지 키워 잘리지 않게."""
    cx, cy, r = c["cx"] + bleed, c["cy"] + bleed, c["r"]
    W, H = PW, cy + r + 1
    body = (f"<circle cx='{cx}' cy='{cy}' r='{r}' fill='{svg.h(main)}'/>")
    return svg.data_uri(W, H, body)


def crest(color, w, h):
    return svg.data_uri(w, h, art.crest(color), viewbox=art.CREST_VIEWBOX)


def mark(color, w, h):
    """판권면 로고 — 크레스트와 같이 벡터로 뽑아 색만 바꿔 쓴다."""
    return svg.data_uri(w, h, art.mark(color), viewbox=art.MARK_VIEWBOX)


# ── 프렐류드 ────────────────────────────────────────────────────────────
def prelude(cfg):
    m = metrics_of(cfg)
    p = cfg.page
    bleed, PW, PH = p["bleed"], p["media_w"], p["media_h"]
    pal = cfg.section("palette") or {}
    o = ["/* ---------- 서체 (로컬 설치본을 build/fonts 로 복사해 임베드) ---------- */"]
    for f in cfg.get("fonts") or []:
        st = f" font-style: {f['style']};" if f.get("style") else ""
        # 한글 파일명은 build/fonts 에 ASCII 별칭(`as`)으로 놓인다 (→ __init__._stage_fonts)
        fn = f.get("as") or os.path.basename(f["file"])
        o.append(f'@font-face {{ font-family: "{f["family"]}"; '
                 f'src: url("fonts/{fn}"); '
                 f'font-weight: {f.get("weight", 400)};{st} }}')

    o.append("\n:root {")
    for k, v in pal.items():
        if isinstance(v, str):
            # config 는 `cover_mark`, CSS 는 `--c-cover-mark` — 밑줄을 하이픈으로
            o.append(f"    --c-{k.replace('_', '-')}: {v};")
    if not pal.get("headtxt"):
        o.append("    --c-headtxt: #fff;"
                 "                 /* ①③ 헤더 글자 — 따로 안 정하면 흰색 */")
    if not pal.get("sense"):
        o.append("    --c-sense: var(--c-accent);"
                 "     /* 의미 번호 — 따로 안 정하면 주색상 */")
    mm_vars = [
        ("bleed", bleed), ("media-w", PW), ("media-h", PH),
        ("mgn-out", m["mgn_out"] + bleed), ("mgn-in", m["mgn_in"] + bleed),
        ("margin-top", m["margin_top"] + bleed),
        ("head-h", m["margin_top_open"] + bleed),
        ("col-w", m["col_w"]), ("col-gap", m["col_gap"]),
        ("rule-w", m["rule_w"]),
        ("w-pad-t", m["w_pad_t"]), ("w-pad-b", m["w_pad_b"]),
        ("no-w", m["no_w"]), ("chk", m["chk"]), ("chk-gap", m["chk_gap"]),
        ("chk-mt", m["chk_mt"]),
        ("word-mt", m["word_mt"]), ("pron-mt", m["pron_mt"]),
        ("deriv-mt", m["deriv_mt"]), ("deriv-lh", m["deriv_lh"]),
        ("def-slot", m["def_slot"]), ("def-lh", m["def_lh"]),
        ("def-hang", m["def_hang"]), ("def-mb", m["def_mb"]),
        ("pos-box", m["pos_box"]), ("pos-gap", m["pos_gap"]),
        ("pos-r", m["pos_r"]), ("pos-va", m["pos_va"]),
        ("pos-line-w", m["pos_line_w"]), ("pos-va-deriv", m["pos_va_deriv"]),
        ("en-lh", m["en_lh"]), ("kr-lh", m["kr_lh"]), ("kr-mt", m["kr_mt"]),
        ("pair-mt", m["pair_mt"]),
        ("tabtxt-mt", m["tab_txt_mt"]),
        ("tab-x", m["tab"]["x"] + bleed), ("tab-w", m["tab"]["w"]),
        ("pg-out", m["pg_out"]), ("pg-mt", m["pg_mt"]),
        ("logo-pr", m["logo"]["text_right"] + bleed),
        ("logo-pt", m["logo"]["text_top"] + bleed),
    ]
    for k, v in mm_vars:
        o.append(f"    --{k}: {round(v, 3)}mm;")
    o.append(f"    --pos-size: {m['pos_size']}pt;")
    o.append(f"    --logo-size: {m['logo']['text_size']}pt;")
    o.append(f"    --logo-track: {m['logo']['track']}em;")
    for k in ("unit_ttl", "unit_num"):
        g = m[k]
        n = k.replace("_", "-")
        o.append(f"    --{n}-x: {g['x']}mm; --{n}-y: {g['y']}mm;")
    cp = m["colophon"]
    o.append(f"    --colo-mark-x: {cp['mark_x']}mm; --colo-mark-y: {cp['mark_y']}mm;")
    o.append(f"    --colo-mark-w: {cp['mark_w']}mm; --colo-mark-h: {cp['mark_h']}mm;")
    o.append(f"    --colo-txt-x: {cp['txt_x']}mm; --colo-txt-y: {cp['txt_y']}mm;")
    o.append(f"    --colo-txt-size: {cp['txt_size']}pt;")
    cv = m["cover"]
    o.append(f"    --cover-mark-x: {cv['mark_x']}mm; --cover-mark-y: {cv['mark_y']}mm;")
    o.append(f"    --cover-mark-w: {cv['mark_w']}mm; --cover-mark-h: {cv['mark_h']}mm;")
    o.append(f"    --cover-ttl-x: {cv['ttl_x']}mm; --cover-ttl-y: {cv['ttl_y']}mm;")
    o.append(f"    --cover-ttl-size: {cv['ttl_size']}pt; "
             f"--cover-ttl-track: {cv['ttl_track']}em;")
    o.append(f"    --tight: {m['tight']};")
    o.append("}")

    # ── 페이지 ──
    band_top = band(pal["band"], pal["rule2"], PW, m["band_h"], m["band_rule"],
                    bleed, at_top=True)
    band_bot = band(pal["band"], pal["rule2"], PW, m["band_h"], m["band_rule"],
                    bleed, at_top=False)
    bh = m["band_h"] + bleed
    bg_bands = (f"{band_bot} bottom left / {PW}mm {bh}mm, "
                f"{band_top} top left / {PW}mm {bh}mm")
    o.append("\n/* ---------- 페이지 ---------- */")
    o.append("@page {")
    o.append(f"    size: {PW}mm {PH}mm;"
             f"          /* {p['width']}×{p['height']} + 도련 {bleed}mm */")
    o.append(f"    margin: {m['margin_top'] + bleed}mm "
             f"{m['mgn_in'] + bleed}mm {m['margin_bottom'] + bleed}mm "
             f"{m['mgn_out'] + bleed}mm;")
    o.append(f"    background: {bg_bands};")
    # ⚠ @top-right 는 폭이 좁아 러닝 요소가 잘린다 → 좌우 다 @top-left 슬롯을 쓴다
    o.append("    @top-left     { content: element(hdrL); vertical-align: top; }")
    o.append("    @bottom-left  { content: element(footL); vertical-align: top; }")
    o.append("    @bottom-right { content: element(footR); vertical-align: top; }")
    o.append("}")
    o.append(f"@page :left  {{ margin-left: {m['mgn_out'] + bleed}mm; "
             f"margin-right: {m['mgn_in'] + bleed}mm;")
    o.append("               @bottom-right { content: none; } }")
    o.append(f"@page :right {{ margin-left: {m['mgn_in'] + bleed}mm; "
             f"margin-right: {m['mgn_out'] + bleed}mm;")
    o.append("               @top-left { content: element(hdrR); } "
             "@bottom-left { content: none; } }")

    # 본문 페이지(이름 있는 규칙) — `@page :nth()` 는 이름과 **함께** 써야 먹는다
    o.append("\n@page p-body { }")
    o.append("@page p-cover {")
    o.append(f"    background: {pal['cover_bg']};")
    o.append("    margin: 0; @top-left { content: none; }")
    o.append("    @bottom-left { content: none; } @bottom-right { content: none; } }")

    # MEMO 면 — 강제 개행으로 생긴 빈 면
    g_full_r = grid_full(pal["grid"], PW, PH, m["grid_pitch"], m["grid_width"],
                         bleed=bleed)
    memo = m["memo"]
    memo_bg = (f"url(\"assets/memotab.png\") "
               f"right {memo['right']}mm top {memo['top'] + bleed}mm / "
               f"{memo['w']}mm {memo['h']}mm no-repeat, {bg_bands}, "
               f"{g_full_r} top left / {PW}mm {PH}mm")
    off = ("    @top-left { content: none; }\n"
           "    @bottom-left { content: none; } @bottom-right { content: none; }")
    o.append("\n/* 강제 개행으로 생긴 빈 페이지 = MEMO 면 */")
    o.append("@page p-body:blank {")
    o.append(off)
    o.append(f"    background: {memo_bg};")
    o.append("}")
    # 맨 뒤 MEMO 면 — `break-before: left` 로 붙이므로 **총 쪽수가 언제나 짝수**가 된다
    o.append("\n/* 맨 뒤 MEMO 면 (마지막 면을 왼쪽으로 맞춘다) */")
    o.append("@page p-memo {")
    o.append(off)
    o.append(f"    background: {memo_bg};")
    o.append("}")

    # ── 대단원 ──
    # 글자·괘선 색은 **CSS 변수**로 갈아끼운다(`.p2` 안에서 --c-accent 가 바뀌면
    # 그 아래 전부가 따라온다). 배경 SVG 는 색이 구워져 들어가므로 변수로는
    # 못 바꾼다 → `generated()` 가 대단원마다 규칙을 따로 낸다.
    pp = part_palettes(cfg)
    if len(pp) > 1:
        o.append("\n/* ---------- 대단원 ---------- */")
        for n, ppal in sorted(pp.items()):
            if n > 1:
                o.append(f".p{n} {{ " + " ".join(
                    f"--c-{k.replace('_', '-')}: {ppal[k]};" for k in HUE_KEYS
                    if isinstance(ppal.get(k), str)) + " }")
            o.append(f"@page p-part{n}, p-part{n}b {{ margin: 0;"
                     f" background: {ppal['cover_bg']};")
            o.append("    @top-left { content: none; } "
                     "@bottom-left { content: none; } "
                     "@bottom-right { content: none; } }")
    return "\n".join(o)


# ── 생성 규칙(배경 SVG) ─────────────────────────────────────────────────
def generated(cfg):
    o = ["/* ▼▼ 생성 규칙 — series/vocaunit/theme.py 가 만든다. 직접 고치지 말 것 ▼▼ */"]
    pp = part_palettes(cfg)
    for n, ppal in sorted(pp.items()):
        # 1번 대단원은 셀렉터 없이(기본), 나머지는 `.pN` 안에서만
        o += _shapes(cfg, ppal, "" if n == 1 else f".p{n} ", n)
    o.append("/* ▲▲ 생성 규칙 끝 ▲▲ */")
    return "\n".join(o)


def _shapes(cfg, pal, pre, n):
    m = metrics_of(cfg)
    p = cfg.page
    bleed, PW, PH = p["bleed"], p["media_w"], p["media_h"]
    lg = m["logo"]
    o = []

    # ③ 탭 (왼쪽 면) — 배경 SVG + 러닝 요소 글자
    t = m["tab"]
    o.append(f"{pre}.hdr-l {{ background: {tab(pal['tab'], t, bleed)} "
             f"{t['x'] + bleed - 1}mm {t['y'] + bleed - 1}mm / "
             f"{t['w'] + 2}mm {t['h'] + 2}mm; }}")
    o.append(f"{pre}.hdr-l.mir {{ background: {tab(pal['tab'], t, bleed, mirror=True)} "
             f"{PW - t['x'] - bleed - t['w'] - 1}mm {t['y'] + bleed - 1}mm / "
             f"{t['w'] + 2}mm {t['h'] + 2}mm; }}")
    # ④ 로고 (오른쪽 면) — 크레스트 SVG + 알약 PNG + 라이브 글자
    o.append(f"{pre}.hdr-r {{ background: "
             f"url(\"assets/pill2026.png\") "
             f"no-repeat right {lg['pill_right'] + bleed}mm "
             f"top {lg['pill_top'] + bleed}mm / "
             f"{lg['pill_w']}mm {lg['pill_h']}mm, "
             f"{crest(pal['crest'], lg['crest_w'], lg['crest_h'])} "
             f"right {lg['crest_right'] + bleed}mm top {lg['crest_top'] + bleed}mm / "
             f"{lg['crest_w']}mm {lg['crest_h']}mm; }}")
    # ① Unit 시작 면 — 모눈 + 큰 원 (인플로우 `.unit-head` 안에서 그린다)
    gh = m["grid_h"]
    g_l = grid(pal["grid"], PW, gh, m["grid_pitch"], m["grid_width"], bleed,
               phase_right=True)
    g_r = grid(pal["grid"], PW, gh, m["grid_pitch"], m["grid_width"], bleed,
               phase_right=False)
    o.append(f"/* 모눈 헤더 ①②: 왼쪽면 {g_l} top left / {PW}mm {gh + bleed}mm */")
    o.append(f"/* 모눈 헤더 ①②: 오른쪽면 {g_r} top left / {PW}mm {gh + bleed}mm */")
    o.append(f"{pre}.unit-head {{ background: {circle(pal['circle'], m['circle'], bleed, PW)} "
             f"top left / {PW}mm {m['circle']['cy'] + bleed + m['circle']['r'] + 1}mm"
             f", {g_l} top left / {PW}mm {gh + bleed}mm; }}")
    o.append(f"{pre}.unit-head.mir {{ background: "
             f"{circle(pal['circle'], m['circle'], bleed, PW)} "
             f"top left / {PW}mm {m['circle']['cy'] + bleed + m['circle']['r'] + 1}mm"
             f", {g_r} top left / {PW}mm {gh + bleed}mm; }}")

    # 대단원 간지 로고 — 면 색 위에 흰 마크
    o.append(f"{pre}.part-cover .mark {{ background: "
             f"{mark(pal.get('cover_mark') or '#fff', 27.843, 5.197)} "
             f"center / contain; }}")
    if n > 1:
        return o
    # 간지 크레스트
    o.append(f".cover .crest {{ background: "
             f"{crest(pal['cover_mark'], 67.36, 62.275)} center / contain; }}")
    # 판권면 로고 — 색을 안 정하면 주색상(accent)을 따른다
    cp = m["colophon"]
    o.append(f".colophon .mark {{ background: "
             f"{mark(pal.get('mark') or pal['accent'], cp['mark_w'], cp['mark_h'])} "
             f"center / contain; }}")
    return o


def open_page_css(cfg, m=None):
    """2패스가 쓰는 ①② 면 배경 — (왼쪽면 배경, 오른쪽면 배경, ② 상단여백)."""
    m = m or metrics_of(cfg)
    p = cfg.page
    bleed, PW = p["bleed"], p["media_w"]
    pal = cfg.section("palette") or {}
    gh = m["grid_h"]
    band_bot = band(pal["band"], pal["rule2"], PW, m["band_h"], m["band_rule"],
                    bleed, at_top=False)
    bh = m["band_h"] + bleed

    def bg(phase_right):
        g = grid(pal["grid"], PW, gh, m["grid_pitch"], m["grid_width"], bleed,
                 phase_right=phase_right)
        return (f"{band_bot} bottom left / {PW}mm {bh}mm, "
                f"{g} top left / {PW}mm {gh + bleed}mm")

    return bg(True), bg(False), m["margin_top_open"] + bleed


def build_css(cfg):
    src = open(THEME_SRC, encoding="utf-8").read()
    return (src.replace("/*@PRELUDE@*/", prelude(cfg))
               .replace("/*@GENERATED@*/", generated(cfg)))


def write(cfg, path, log=None):
    css = build_css(cfg)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(css)
    if log:
        m = metrics_of(cfg)
        log(f"[테마] {len(css.splitlines())}줄 생성 "
            f"(띠 {m['band_h']}mm · 모눈 {m['grid_h']}mm/{m['grid_pitch']}mm) "
            f"→ {os.path.basename(path)}")
    return path
