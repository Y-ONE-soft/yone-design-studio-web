"""단어장 계열 테마 생성 — 팔레트/치수(③) + 계열 스타일시트(②) → build/theme.css.

색을 바꾸면 **반드시 이걸 다시 돌려야 한다**. 배경 SVG 안에는 CSS 변수를 못 쓰기
때문에 색이 구워져 들어간다 — 재생성을 빼먹으면 4mm 띠·밴드만 옛 색으로 남는다
(상일보카에서 두 번 발생). 그래서 색의 단일 소스는 config 의 `palette` 이고,
생성은 빌드마다 자동으로 돈다.

생성 대상은 전부 배경 SVG 다. 마진 박스에서는 position/transform/clip-path 가
통하지 않고, 본문에서도 border-radius 가 자식을 자르지 않는다(→ `svg.py` 주석).
  1. @page <이름>        4mm 상단 띠(연톤 + 보조색 라인)
  2. @page <이름>:blank  MEMO 면(괘선 + 4mm 띠)
  3. .s-* .day-head .band  ① 시작 면 상단 밴드 (+ ②용 미러 버전은 주석으로 흘림)
  4. .s-* .day-head .dia   ① 큰 마름모(밴드 앞에 뜸)
  5. .s-* .tab-l           ③ 작은 마름모 탭
"""
import os

from core.render_vivlio import svg

HERE = os.path.dirname(os.path.abspath(__file__))
THEME_SRC = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "themes", "vocabook.css")

# 계열 기본 치수 — 배재보카03 완성본 PDF/AI 실측. 책이 필요하면 metrics 로 덮는다.
DEFAULT_METRICS = {
    "mgn_x": 22.0,          # 좌우 여백 (19mm + 도련 3mm)
    "margin_top": 23.0,     # 20 + 도련
    "margin_bottom": 14.0,  # 11 + 도련
    "lab_w": 25.25,         # 라벨 열
    "tight": "-.012em",
    "band_h": 15.27,        # ① 시작면 밴드 높이(재단선 기준)
    "band_r": 15.27,        # 좌하단 사분원 반지름
    "band_x": 3.99,         # 밴드 왼쪽 시작 x
    "tag": {"x": 16.44, "y": 6.43, "w": 16.78, "h": 17.86, "r": 3.49},
    "tag_small": {"x": 1.2, "y": 2.2, "w": 10.6, "h": 11.3, "r": 2.2},
    "fold_w": 2.23,         # 오른쪽 접힌 꼬리 폭
    "fold_w_small": 1.5,
    "strip_h": 5.5,         # ③④ 4mm 띠(도련 재단 후 여백 확보용으로 키움)
    "tint_w": 46.0,         # 시작 면 밴드의 보조색 길이
    "diag": 52.34,          # 보조색 톤이 45°로 끝나는 x
    "page_margin_top": {},  # {"p-ans": 12} 처럼 페이지별 상단 여백 덮어쓰기
    "memo": {"w": 110, "h": 152, "pitch": 9.5, "color": "#e4e8ec",
             "width": 0.25, "x": 22, "y": 33},
}


def metrics_of(cfg):
    m = dict(DEFAULT_METRICS)
    for k, v in (cfg.section("metrics") or {}).items():
        if isinstance(v, dict) and isinstance(m.get(k), dict):
            d = dict(m[k])
            d.update(v)
            m[k] = d
        else:
            m[k] = v
    return m


def sections_of(cfg):
    """[(클래스, 페이지이름, main, pale, sub)] — config 팔레트 순서 그대로."""
    pal = cfg.section("palette") or {}
    out = []
    for cls, v in (pal.get("sections") or {}).items():
        out.append((cls, v.get("page") or cls.replace("s-", "p-"),
                    v["main"], v["pale"], v["sub"]))
    return out


# ── 배경 SVG (전부 재단선 원점 기준, 도련만큼 늘려 그린다) ──────────────────
def strip(pale, sub, PW, strip_h, bleed):
    """상단 4mm 띠 — 위·좌우 도련까지 채운다."""
    h = strip_h + bleed
    return svg.data_uri(PW, h,
                        svg.rect(0, 0, PW, h - .7, pale)
                        + svg.rect(0, h - .7, PW, .7, sub)) + " 0 0"


def band(pale, sub, PW, m, bleed, tint=True, h=None, mirror=False):
    """상단 밴드 — 좌하단(미러면 우하단) 사분원 + 45°로 끝나는 보조색 톤."""
    H0 = h or m["band_h"]
    H = H0 + bleed
    R = min(m["band_r"], H0)
    x, w = m["band_x"] + bleed, PW
    body = svg.path(
        f"M{w} {H} L{x + R:.2f} {H} "
        f"C{x + R * .55:.2f} {H} {x} {H - R * .55:.2f} {x} 0 L{w} 0 Z", fill=pale)
    if tint:
        diag = m["diag"] + bleed
        body += svg.path(
            f"M{diag:.2f} {H} L{x + R:.2f} {H} "
            f"C{x + R * .55:.2f} {H} {x} {H - R * .55:.2f} {x} 0 "
            f"L{diag - H0:.2f} 0 Z", fill=sub, opacity=".28")
    if mirror:
        body = svg.mirror(body, w)
    return svg.data_uri(PW, H, body)


def gem(main, w, h, t, fold_w, band_bottom, bleed):
    """흰 라벨 태그 + 오른쪽 접힌 꼬리 — 위 모서리는 각지고 아래만 둥글다.
    꼬리는 태그 위에서 뾰족하게 시작해 아래로 넓어지며 **띠 하단에서 끝난다**."""
    x, y, tw, th, r = t["x"] + bleed, t["y"] + bleed, t["w"], t["h"], t["r"]
    bb = band_bottom + bleed
    x1 = x + tw
    tag = (f"M{x1 - r:.2f} {y + th:.2f} L{x + r:.2f} {y + th:.2f} "
           f"C{x + r * .45:.2f} {y + th:.2f} {x:.2f} {y + th - r * .45:.2f} "
           f"{x:.2f} {y + th - r:.2f} L{x:.2f} {y:.2f} L{x1:.2f} {y:.2f} "
           f"L{x1:.2f} {y + th - r:.2f} C{x1:.2f} {y + th - r * .45:.2f} "
           f"{x1 - r * .45:.2f} {y + th:.2f} {x1 - r:.2f} {y + th:.2f} Z")
    fold = (f"M{x1 + .17:.2f} {y - .17:.2f} L{x1 + fold_w:.2f} {bb:.2f} "
            f"L{x1 + .17:.2f} {bb:.2f} Z")
    return svg.data_uri(w, h, svg.path(fold, fill=main)
                        + svg.path(tag, fill="#fff", stroke=main, width=".35"))


def memo_bg(m):
    mm = m["memo"]
    return (svg.hrules(mm["w"], mm["h"], mm["pitch"], mm["color"], mm["width"])
            + f" {mm['x']}mm {mm['y']}mm")


# ── 프렐류드 ────────────────────────────────────────────────────────────
def prelude(cfg):
    m = metrics_of(cfg)
    p = cfg.page
    bleed = p["bleed"]
    PW = p["media_w"]
    pal = cfg.section("palette") or {}
    o = ["/* ---------- 서체 (로컬 설치본을 build/fonts 로 복사해 임베드) ---------- */"]
    for f in cfg.get("fonts") or []:
        w = f.get("weight", 400)
        st = f" font-style: {f['style']};" if f.get("style") else ""
        o.append(f'@font-face {{ font-family: "{f["family"]}"; '
                 f'src: url("fonts/{os.path.basename(f["file"])}"); '
                 f'font-weight: {w};{st} }}')

    o.append("\n:root {")
    o.append("    /* ── 공통색상 (전 파트 공유 — 여기 한 곳에만 둔다) ── */")
    for k, v in (pal.get("common") or {}).items():
        o.append(f"    --c-{k}: {v};")
    first = next(iter((pal.get("sections") or {}).values()), None)
    if first:
        o.append("\n    /* ── 주색상 / 보조색상 (섹션이 덮어씀) ── */")
        o.append(f"    --main: {first['main']};")
        o.append(f"    --main-pale: {first['pale']};")
        o.append(f"    --sub: {first['sub']};")
    o.append("\n    /* ── 치수 ── */")
    o.append(f"    --bleed: {bleed}mm;")
    o.append(f"    --mgn-x: {m['mgn_x']}mm;")
    o.append(f"    --lab-w: {m['lab_w']}mm;")
    o.append(f"    --tight: {m['tight']};")
    o.append("}")

    o.append("\n/* 섹션별 톤 — 주/보조색상만 바꾼다 */")
    for cls, v in (pal.get("sections") or {}).items():
        note = f"  /* {v['label']} */" if v.get("label") else ""
        o.append(f".{cls} {{ --main: {v['main']}; --main-pale: {v['pale']}; "
                 f"--sub: {v['sub']}; }}{note}")

    o.append("\n/* ---------- 페이지 ---------- */")
    o.append("@page {")
    o.append(f"    size: {p['media_w']}mm {p['media_h']}mm;"
             f"                 /* {p['width']}×{p['height']} + 도련 {bleed}mm */")
    o.append(f"    margin: {m['margin_top']}mm var(--mgn-x) "
             f"{m['margin_bottom']}mm var(--mgn-x);")
    o.append("    @top-left     { content: element(tabL); vertical-align: top; }")
    o.append("    @bottom-left  { content: element(footL); vertical-align: top; }")
    o.append("    @bottom-right { content: element(footR); vertical-align: top; }")
    o.append("    @right-top { content: element(idx); }")
    o.append("}")
    o.append("@page :left  { @bottom-right { content: none; } "
             "@right-top { content: none; } }")
    o.append("@page :right { @top-left { content: none; } "
             "@bottom-left { content: none; } }")
    for name, top in (m["page_margin_top"] or {}).items():
        o.append(f"@page {name}  {{ margin-top: {top}mm; }}"
                 f"    /* 4mm 띠만 있는 면 → 내용을 위로 */")

    o.append("\n/* 강제 개행으로 생긴 빈 페이지 = MEMO 면 */")
    o.append("@page :blank {")
    o.append("    @top-left  { content: none; } @top-right { content: none; }")
    o.append("    @top-center { content: none; } @right-top { content: none; }")
    o.append("    @bottom-left { content: none; } @bottom-right { content: none; }")
    o.append('    @top-center { content: "M E M O"; font: 700 7pt "Elice"; '
             'color: #b9bfc7;')
    o.append("                  letter-spacing: .18em; vertical-align: bottom; "
             "padding-bottom: 3mm; }")
    o.append(f"    background: {memo_bg(m)};")
    o.append("}")
    return "\n".join(o)


# ── 생성 규칙(배경 SVG) ─────────────────────────────────────────────────
def generated(cfg):
    m = metrics_of(cfg)
    p = cfg.page
    bleed, PW = p["bleed"], p["media_w"]
    memo = memo_bg(m)
    o = ["/* ▼▼ 생성 규칙 — series/vocabook/theme.py 가 만든다. 직접 고치지 말 것 ▼▼ */"]
    for cls, page, main, pale, sub in sections_of(cfg):
        st = strip(pale, sub, PW, m["strip_h"], bleed)
        o.append(f"@page {page} {{ background: {st}; }}")
        o.append(f"@page {page}:blank {{ background: {memo}, {st}; }}")
    o.append("")
    for cls, page, main, pale, sub in sections_of(cfg):
        # ② 밴드는 pages.css(2패스)가 페이지 배경으로 깐다 — 마진 박스 높이 제한 회피.
        o.append(f"/* {page} ②밴드: "
                 f"{band(pale, sub, PW, m, bleed, h=m['band_h'], mirror=True)} */")
        o.append(f".{cls} .day-head .band "
                 f"{{ background: {band(pale, sub, PW, m, bleed)}; }}")
        o.append(f".{cls} .day-head .dia {{ background: "
                 f"{gem(main, 40 + bleed, 26 + bleed, m['tag'], m['fold_w'], m['band_h'], bleed)}; }}")
        o.append(f".dh-right.{cls} .day-head .band "
                 f"{{ background: {band(pale, sub, PW, m, bleed, mirror=True)}; }}")
        o.append(f".{cls} .tab-l {{ background: "
                 f"{gem(main, 17, 15 + bleed, m['tag_small'], m['fold_w_small'], m['strip_h'], bleed)}; }}")
    o.append("/* ▲▲ 생성 규칙 끝 ▲▲ */")
    return "\n".join(o)


def build_css(cfg):
    """계열 스타일시트 + 생성부 → 완성 theme.css 텍스트."""
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
            f"(밴드 {m['band_h']}mm · 띠 {m['strip_h']}mm · "
            f"섹션 {len(sections_of(cfg))}) → {os.path.basename(path)}")
    return path
