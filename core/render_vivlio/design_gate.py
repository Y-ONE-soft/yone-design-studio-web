"""디자인 게이트 — 디자인 규칙을 문서가 아니라 **기계**에 둔다.

## 왜 필요한가

"디자인을 여러 번 고친다"의 원인은 두 종류인데 해법이 다르다.

- **취향 조정**("칙칙하다", "톤을 올려라", 헤더 시안 A/B/C)
  → 손잡이(config)로 **사용자가 직접** 돌린다. 이건 게이트의 일이 아니다.
- **컨셉 오류**("네모 하나 라인 하나는 빈약하다", "미러링 하지 마라",
  "글리프 쓰지 마라", "손가락 같다", "흰 글자가 안 읽힌다")
  → 값이 아니라 **구성**이 틀린 것이라 손잡이로 못 고친다.

두 번째 부류가 시안 왕복의 대부분이었는데, 지금까지 이 규칙들은 **매번 사후
지적으로만** 전달됐다. 그래서 계열을 새로 만들 때마다 같은 실수를 반복했다.
규칙을 여기 굳혀 두면 1차 시안 품질이 올라가고 왕복이 줄어든다.

## 판정 세기 — 기본은 경고다

**기존 납품 교재는 고치지 않는다.** 납품 중이라 지면이 바뀌면 이미 나간 책과
새 원고로 만든 책이 달라진다. 그래서 여기 검사는 기본이 `report.warn` 이고,
책 config 가 `verify.design.strict: true` 를 켜야 결함이 된다.
**신규 조판은 strict 를 켜고 시작할 것.** 그게 이 파일의 존재 이유다.

## 무엇을 재는가 — 전부 **결과 PDF** 에서 잰다

config 의 색 이름만 봐서는 그 색이 어디에 얼마나 쓰였는지 알 수 없다. 실제로
지면에 찍힌 픽셀과 글자를 재야 "흰 글자가 파스텔 위에 있다" 같은 것이 잡힌다.

    G-크기    본문 최소 글자 크기        (7pt 미만은 인쇄물에서 읽기 어렵다)
    G-대비    글자 ↔ 그 자리 배경 대비   ("흰 글자는 deep 위에만"이 여기서 잡힌다)
    G-색면    면마다 유채색 면적 비율    (학습면 3~8% · 문제면 1~3%)
    G-글리프  장식 글리프를 머리 기호로  (■ ● ✓ ❖ · 금지 — 도형·배지·배지로)
    G-미러    좌우 면 장식이 거울상인가  (좌우는 '무엇을 넣는지'가 달라야 한다)

## 첫 판에서 걸러낸 오탐 넷 (전부 실제로 나왔다)

① **엔진 표식**(`§A1§`·`DAYOPEN`)이 0.1pt 글자로 잡혔다 → 표식은 글자가 아니다.
② **머리말·꼬리말 6pt** 가 "본문 7pt 미만"으로 잡혔다 → 러닝 요소는 원래 작다.
   판면(`verify.frame`) 밖은 본문이 아니다. frame 이 없는 책은 위아래 8% 로 본다.
③ **대비 272곳**은 사실 헤더가 매 면 반복된 것이라 **서로 다른 결함은 2개**였다
   → 색 조합으로 묶어서 보고한다. 안 묶으면 목록만 길고 못 읽는다.
④ **좌우 여백이 비어 있으면** 미러 유사도가 1.0 이 나온다 → 견주는 **띠 안에
   장식이 실제로 있을 때만** 따진다.

⚠ 서체 **이름**으로 판정하지 말 것 — Vivliostyle 출력은 전부 `Type3 (n 0 R)` 라
  이름으로 찾는 검사는 아무것도 못 찾고 **조용히 통과**한다.
"""
import collections
import math
import re

from core.render_vivlio import probe

# 조판 표식 — 눈에 안 보이는 자리표(2패스가 면을 찾는 데 쓴다). 글자가 아니다.
RE_MARKER = re.compile(r"^\s*§[^§]*§\s*$")

# 기본 장식 글리프 — 사용자 지시로 머리 기호 사용 금지(도형·색면·배지·괘선으로).
# ★ ◆ ▣ 는 중등부가 뜻을 담아 쓰고 있어 기본 목록에서 뺀다(책이 추가할 수 있다).
BULLET_GLYPHS = "■□●○◎✓✔❖◇▪▫※·"

DEFAULTS = {
    "strict": False,        # True 면 경고가 결함이 된다 (신규 조판은 켤 것)
    # ⚠ **본문 최소 크기는 책마다 다르다.** 7pt 는 A4 중등부 규칙이고, A5 단어장은
    #   본문이 원래 6pt 다 — 7 을 기본으로 두면 상일보카 한 권에서 34,241건이 나온다
    #   (실제로 그랬다). 그래서 기본은 **끔**이고, 분포는 언제나 적어 둔다.
    #   책이 자기 바닥값을 정해 넣는다(A4 학습서는 7.0 권장).
    "min_pt": None,
    "max_warn": 8,          # 검사 하나가 내는 경고 줄 상한(나머지는 한 줄로 요약)
    # 대비는 **두 단**이다. 아래를 하나로 두면(WCAG 4.5 일괄) 하우스 색이 흰
    # 바탕에 얹힌 것까지 전부 걸려 목록이 수십 줄이 되고, 정작 "흰 글자가
    # 파스텔 위에" 같은 진짜 결함이 묻힌다.
    "contrast_hard": 3.0,   # 이 아래 = 경고. 인쇄물에서 실제로 읽기 어렵다
    "contrast_soft": 4.5,   # hard~soft 사이 = 참고 한 줄만(판단은 사람이)
    "mirror_edge": 0.02,    # 바깥 띠가 '장식'인지 — 이 미만이면 평평한 색면
    "chroma_max": 0.35,     # 면 유채색 면적 상한(간지·전면 색면은 제외 목록으로)
    "chroma_pages_skip": [],
    "bullets": BULLET_GLYPHS,
    "bullets_allow": "",    # 이 책에서 허용하는 글리프
    "mirror_sim": 0.93,     # 좌우 장식 유사도가 이 값을 넘으면 거울상 의심
    "dpi": 72,              # 면 렌더 해상도(면적·대비용). 낮아도 충분하다.
    "running_frac": 0.08,   # frame 이 없는 책의 러닝 요소 띠(위·아래 비율)
    "sample_pages": 0,      # >0 이면 그만큼만 골라 본다(빠른 확인용)
}


def settings(cfg):
    d = dict(DEFAULTS)
    d.update(((cfg.section("verify") or {}).get("design") or {}))
    return d


# ── 색 계산 ──────────────────────────────────────────────────────────
def _lin(c):
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb):
    r, g, b = (_lin(v) for v in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(rgb1, rgb2):
    """WCAG 대비비 1.0~21.0."""
    a, b = luminance(rgb1), luminance(rgb2)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def chroma(rgb):
    """0~1. 무채색이면 0. HSV 채도와 같다 (max-min)/max."""
    mx, mn = max(rgb), min(rgb)
    return 0.0 if mx == 0 else (mx - mn) / mx


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(rgb)


def _near(a, b, tol):
    return all(abs(int(a[i]) - int(b[i])) <= tol for i in range(3))


# ── 본문 영역 ────────────────────────────────────────────────────────
def body_test(cfg, page_h_mm, s):
    """`bbox, pageno → 본문인가?` 판정 함수.

    러닝 요소(머리말·꼬리말·쪽번호)는 원래 본문보다 작다 — 6pt 꼬리말을 "본문
    7pt 미만"으로 잡으면 게이트가 거짓말을 한다. **판면 밖은 본문이 아니다.**
    `verify.frame` 이 있으면 그걸 쓰고(넘침 검사와 같은 자), 없으면 위·아래
    `running_frac` 만큼을 러닝 띠로 본다.
    """
    frame = (cfg.section("verify") or {}).get("frame")
    if frame:
        def inside(bbox, pageno):
            top, bottom = frame["top"], frame["bottom"]
            return top - 1.0 <= bbox[1] <= bottom + 1.0
        return inside, "판면 %.0f~%.0fmm" % (frame["top"], frame["bottom"])
    band = page_h_mm * s["running_frac"]

    def inside(bbox, pageno):
        return band <= bbox[1] <= page_h_mm - band
    return inside, "위·아래 %.0f%% 제외" % (s["running_frac"] * 100)


MARKER_PT = 1.0     # 이보다 작으면 읽으라고 넣은 글자가 아니다


def _usable(sp):
    """글자로 칠 스팬인가 — 조판 표식·빈 문자열 제외.

    표식은 이름이 제각각이라(`§A1§`·`DAYOPEN`·`PARTOPEN`) 목록으로 못 막는다.
    **크기로 가른다** — 1pt 미만은 사람이 읽으라고 넣은 글자가 아니다.
    """
    t = sp["text"]
    if not t.strip() or sp["size"] < MARKER_PT:
        return False
    return not RE_MARKER.match(t)


# ── 면 렌더 캐시 ─────────────────────────────────────────────────────
class PageInk(object):
    """면 하나를 한 번만 렌더해 여러 검사가 나눠 쓴다."""

    def __init__(self, page, dpi):
        self.pm = page.get_pixmap(dpi=dpi, alpha=False)
        self.dpi = dpi
        self.w, self.h = self.pm.width, self.pm.height
        self.n = self.pm.n
        self.buf = self.pm.samples

    def px(self, x, y):
        i = (y * self.w + x) * self.n
        b = self.buf
        return (b[i], b[i + 1], b[i + 2])

    def rect_px(self, bbox_mm, pad=0.0):
        s = self.dpi / 25.4
        x0 = max(0, int((bbox_mm[0] - pad) * s))
        y0 = max(0, int((bbox_mm[1] - pad) * s))
        x1 = min(self.w, int(math.ceil((bbox_mm[2] + pad) * s)))
        y1 = min(self.h, int(math.ceil((bbox_mm[3] + pad) * s)))
        return x0, y0, x1, y1

    def mode_color(self, bbox_mm, exclude=None, pad=0.6):
        """bbox 언저리의 **최빈색** = 배경.

        글자 픽셀을 빼려고 글자색과 가까운 것은 제외한다. 글자가 차지하는 면적이
        배경보다 작으므로 최빈색은 거의 언제나 배경이다.
        """
        x0, y0, x1, y1 = self.rect_px(bbox_mm, pad)
        if x1 <= x0 or y1 <= y0:
            return None
        cnt = collections.Counter()
        xs = max(1, (x1 - x0) // 40)
        ys = max(1, (y1 - y0) // 12)
        for y in range(y0, y1, ys):
            for x in range(x0, x1, xs):
                c = self.px(x, y)
                if exclude is not None and _near(c, exclude, 60):
                    continue
                cnt[c] += 1
        return cnt.most_common(1)[0][0] if cnt else None

    def chroma_ratio(self, thresh=0.12, step=3, box=None):
        """유채색 픽셀 비율(0~1). `box` = (x0,y0,x1,y1) 픽셀 범위."""
        x0, y0, x1, y1 = box or (0, 0, self.w, self.h)
        tot = hit = 0
        for y in range(y0, y1, step):
            for x in range(x0, x1, step):
                tot += 1
                if chroma(self.px(x, y)) >= thresh:
                    hit += 1
        return (hit / tot) if tot else 0.0


# ── 검사 ────────────────────────────────────────────────────────────
def _brief(v, k=12):
    return ", ".join(map(str, v[:k])) + (f" …외 {len(v) - k}개" if len(v) > k else "")


def _edge_density(ink, box, tol=24, step=2):
    """띠 안에 **모양**이 있는가 — 이웃 픽셀이 확 달라지는 비율.

    단색 띠(광문보카 위아래 분홍)는 0 에 가깝고, 그림·글자·도형이 있으면 커진다.
    "장식이 있는가"를 채도로 재면 단색 색면도 장식으로 세어 버린다.
    """
    x0, y0, x1, y1 = box
    tot = hit = 0
    for y in range(y0, y1 - step, step):
        for x in range(x0, x1 - step, step):
            tot += 1
            if not _near(ink.px(x, y), ink.px(x + step, y), tol):
                hit += 1
            elif not _near(ink.px(x, y), ink.px(x, y + step), tol):
                hit += 1
    return (hit / tot) if tot else 0.0


def check_min_size(pages_spans, is_body, s, report):
    """G-크기 — 본문 글자 크기. 러닝 요소는 따로 적어만 둔다.

    바닥값(`min_pt`)이 없으면 **분포만 적는다.** 책마다 본문 크기가 다르므로
    (A4 학습서 9~10pt / A5 단어장 6pt) 한 숫자를 모두에게 들이대면 거짓말이 된다.
    """
    lo = s["min_pt"]
    bad = collections.defaultdict(list)     # 크기 → [(면, 글자)]
    sizes = collections.Counter()
    small_body = small_run = None
    for pno, spans in pages_spans:
        for sp in spans:
            if not _usable(sp):
                continue
            key = (sp["size"], pno, sp["text"].strip()[:24])
            if is_body(sp["bbox"], pno):
                sizes[round(sp["size"], 1)] += len(sp["text"].strip())
                if small_body is None or sp["size"] < small_body[0]:
                    small_body = key
                if lo and sp["size"] < lo - 0.05:
                    bad[round(sp["size"], 1)].append((pno, sp["text"].strip()[:20]))
            else:
                if small_run is None or sp["size"] < small_run[0]:
                    small_run = key
    if sizes:
        top = ", ".join("%.1fpt %d%%" % (sz, 100 * n / sum(sizes.values()))
                        for sz, n in sizes.most_common(4))
        report.note("[G-크기] 본문 크기 분포(글자 수 기준) %s · 최소 %.1fpt"
                    % (top, min(sizes)))
    if small_run:
        report.note("[G-크기] 러닝 요소 최소 %.1fpt (%d면 “%s”) — 검사 대상 아님"
                    % small_run)
    if not lo:
        report.note("[G-크기] 바닥값 없음 — 판정 안 함 "
                    "(`verify.design.min_pt` 를 정하면 검사한다)")
        return
    for size, hits in sorted(bad.items()):
        ps = sorted(set(p for p, _ in hits))
        sample = "; ".join(dict.fromkeys(t for _, t in hits if t))
        report.design(
            "[G-크기] 본문에 %.1fpt 글자 %d개 (기준 %.1fpt) — %d개 면: %s"
            % (size, len(hits), lo, len(ps), _brief(ps))
            + (" — 예: %s" % sample[:70] if sample else ""), s)


def check_contrast(pages_spans, inks, is_body, s, report):
    """G-대비 — 글자 ↔ 그 자리 배경. "흰 글자는 deep 위에만"이 여기서 잡힌다.

    ⚠ **색 조합으로 묶는다.** 헤더는 매 면 반복되므로 안 묶으면 결함 2개가
      "272곳"으로 보인다 — 길기만 하고 무엇을 고쳐야 할지 안 보인다.
    ⚠ **두 단으로 가른다.** 하우스 색(분홍·보라 번호 따위)이 흰 바탕에 얹히면
      3~4.5:1 인데, 이걸 전부 경고로 내면 광문보카 한 권에서만 20줄이 나오고
      정작 흰 글자가 파스텔 위에 얹힌 1.8:1 이 그 속에 묻힌다.
    """
    hard, soft = s["contrast_hard"], s["contrast_soft"]
    groups = collections.defaultdict(
        lambda: {"n": 0, "pages": set(), "min": 99.0, "sample": ""})
    mid = {"n": 0, "pages": set(), "min": 99.0, "sample": "", "combos": set()}
    worst = None
    for pno, spans in pages_spans:
        ink = inks.get(pno)
        if ink is None:
            continue
        for sp in spans:
            if not _usable(sp) or len(sp["text"].strip()) < 2:
                continue
            bg = ink.mode_color(sp["bbox"], exclude=sp["rgb"])
            if bg is None:
                continue
            c = contrast(sp["rgb"], bg)
            if worst is None or c < worst[0]:
                worst = (c, pno, sp["text"].strip()[:20], sp["color"], _hex(bg))
            if c >= soft:
                continue
            if c < hard:
                g = groups[(sp["color"], _hex(bg))]
            else:
                g = mid
                g["combos"].add((sp["color"], _hex(bg)))
            g["n"] += 1
            g["pages"].add(pno)
            g["min"] = min(g["min"], c)
            if not g["sample"]:
                g["sample"] = sp["text"].strip()[:24]
    if worst:
        report.note("[G-대비] 최저 %.2f:1 (%d면 “%s” %s 위 %s)" % worst)
    ranked = sorted(groups.items(), key=lambda kv: kv[1]["min"])
    cap = s["max_warn"]
    for (fg, bg), g in ranked[:cap]:
        report.design(
            "[G-대비] %s 글자 위 %s 배경 = %.1f:1 (기준 %.1f) — %d곳 / %d개 면: %s"
            % (fg, bg, g["min"], hard, g["n"], len(g["pages"]),
               _brief(sorted(g["pages"])))
            + (" — 예: “%s”" % g["sample"] if g["sample"] else ""), s)
    if len(ranked) > cap:
        rest = ranked[cap:]
        report.design(
            "[G-대비] …그 밖에 %.1f:1 미만 색 조합 %d가지 더 (%s 등) — "
            "심한 순으로 위 %d가지만 폈다"
            % (hard, len(rest),
               ", ".join("%s/%s" % (f, b) for (f, b), _ in rest[:4]), cap), s)
    if mid["n"]:
        report.note(
            "[G-대비] %.1f~%.1f:1 구간 %d곳 / 색 조합 %d가지 / %d개 면 — "
            "하우스 색을 흰 바탕에 얹은 자리들이다. 판단은 사람이 (예: “%s”)"
            % (mid["min"], soft, mid["n"], len(mid["combos"]),
               len(mid["pages"]), mid["sample"]))


def check_chroma(inks, s, report):
    """G-색면 — 유채색 면적 비율. 간지 같은 전면 색면은 제외 목록으로."""
    skip = set(s["chroma_pages_skip"])
    vals = [(p, ink.chroma_ratio()) for p, ink in sorted(inks.items())
            if p not in skip]
    if not vals:
        return
    rs = sorted(v for _, v in vals)
    med = rs[len(rs) // 2]
    top = sorted(vals, key=lambda t: -t[1])[:5]
    report.note("[G-색면] 유채색 면적 중앙 %.1f%% · 상위 %s"
                % (med * 100,
                   ", ".join("%d면 %.0f%%" % (p, v * 100) for p, v in top)))
    over = [(p, v) for p, v in vals if v > s["chroma_max"]]
    if over:
        report.design("[G-색면] 상한 %.0f%% 초과 %d개 면: %s — 간지·전면 색면이면 "
                      "`verify.design.chroma_pages_skip` 에 넣을 것"
                      % (s["chroma_max"] * 100, len(over),
                         _brief([p for p, _ in over])), s)


def check_bullets(pages_lines, s, report):
    """G-글리프 — 장식 글리프를 머리 기호로 쓴 줄."""
    glyphs = set(s["bullets"]) - set(s["bullets_allow"])
    if not glyphs:
        return
    hits = collections.defaultdict(list)
    for pno, lines in pages_lines:
        for t, _ in lines:
            t = t.strip()
            if not t or t[0] not in glyphs:
                continue
            # 머리 기호로 쓴 것만 — 글자에 바로 붙은 것은 본문 기호일 수 있다
            if len(t) > 1 and t[1] not in " \t   ":
                continue
            hits[t[0]].append(pno)
    for g, pnos in sorted(hits.items()):
        ps = sorted(set(pnos))
        report.design(
            "[G-글리프] ‘%s’ 를 머리 기호로 %d번 (%d개 면: %s) — "
            "도형·색면·배지·괘선으로 바꿀 것" % (g, len(pnos), len(ps), _brief(ps)), s)


def check_mirror(inks, s, report, margin_mm=18.0):
    """G-미러 — 왼쪽 면 장식을 좌우 반전해 오른쪽에 쓴 것.

    본문 글자가 섞이면 판정이 흐려지므로 **바깥 여백 띠**만 본다(머리·날개 장식이
    사는 자리). 펼침면(짝수=왼쪽, 홀수=오른쪽) 짝끼리 견준다.

    ⚠ 여백이 비어 있으면 유사도는 당연히 1.0 이다 → **띠 안에 장식이 실제로
      있을 때만** 따진다. 이걸 빼면 흰 여백뿐인 책이 전부 걸린다.
    ⚠ 그리고 **평평한 색 띠는 장식이 아니다.** 광문보카는 위아래에 단색 분홍 띠를
      두는데, 단색이니 좌우가 같은 게 당연하다 — 이걸 미러링이라고 하면 64개
      펼침면이 전부 걸린다(실제로 그랬다). 규칙이 말하는 것은 '무엇을 넣는지'가
      같은 **그림**이므로, 띠 안에 **모양**(경계선)이 있을 때만 따진다.
    """
    pairs = [(p, p + 1) for p in sorted(inks) if p % 2 == 0 and p + 1 in inks]
    sims = []
    for lp, rp in pairs:
        a, b = inks[lp], inks[rp]
        if (a.w, a.h) != (b.w, b.h):
            continue
        band = max(1, int(margin_mm * a.dpi / 25.4))
        if min(_edge_density(a, (0, 0, band, a.h)),
               _edge_density(b, (b.w - band, 0, b.w, b.h))) < s["mirror_edge"]:
            continue
        tot = same = 0
        for y in range(0, a.h, 3):
            for x in range(0, band, 2):
                tot += 1
                if _near(a.px(x, y), b.px(b.w - 1 - x, y), 18):
                    same += 1
        if tot:
            sims.append((same / tot, lp, rp))
    if not sims:
        report.note("[G-미러] 바깥 여백에 장식이 있는 펼침면 없음 — 검사 없음")
        return
    sims.sort(reverse=True)
    report.note("[G-미러] 장식 있는 펼침면 %d개 · 좌우 유사도 최고 %.2f (%d–%d면)"
                % (len(sims), sims[0][0], sims[0][1], sims[0][2]))
    over = [t for t in sims if t[0] >= s["mirror_sim"]]
    if over:
        report.design(
            "[G-미러] 좌우 바깥 장식이 거울상으로 보이는 펼침면 %d개: %s — "
            "좌우는 '무엇을 넣는지'가 달라야 한다"
            % (len(over), ", ".join("%d–%d" % (l, r) for _, l, r in over[:6])), s)


# ── 진입점 ──────────────────────────────────────────────────────────
def run(cfg, pdf, report, log=None, skip_pages=()):
    """책 한 권의 디자인 게이트. `report` 에 note/design 을 쌓는다."""
    s = settings(cfg)
    doc = probe.open_pdf(pdf)
    try:
        total = doc.page_count
        nos = [i + 1 for i in range(total) if (i + 1) not in set(skip_pages)]
        if s["sample_pages"] and len(nos) > s["sample_pages"]:
            step = max(1, len(nos) // s["sample_pages"])
            nos = nos[::step][:s["sample_pages"]]
        page_h = doc[0].rect.height / probe.PT
        is_body, how = body_test(cfg, page_h, s)
        pages_spans, pages_lines, inks = [], [], {}
        for pno in nos:
            pg = doc[pno - 1]
            pages_spans.append((pno, probe.spans_style(pg)))
            pages_lines.append((pno, probe.lines_mm(pg)))
            inks[pno] = PageInk(pg, s["dpi"])
        report.note("[디자인] %d면 검사 (%s · 본문 판정 %s)"
                    % (len(nos), "엄격" if s["strict"] else "경고만", how))
        check_min_size(pages_spans, is_body, s, report)
        check_contrast(pages_spans, inks, is_body, s, report)
        check_chroma(inks, s, report)
        check_bullets(pages_lines, s, report)
        check_mirror(inks, s, report)
    finally:
        doc.close()
    return report
