"""조판 결과 자체 검수 — 원고 ↔ PDF 대조 게이트.

InDesign 경로는 indd 덤프로 43종 게이트를 돌리지만, 코드 조판에는 덤프가 없다.
그 자리를 **PDF 계측**이 메운다. 여기 있는 검사는 전부 계열 무관이고, 계열
고유 검사(대화문 바탕, 해설 펼침면 넘김 …)는 계열 모듈이 `extra` 로 넘긴다.

⚠ Vivliostyle 출력의 서체 이름은 `Type3 (n 0 R)` 로 바뀐다. 서체 **이름으로**
찾는 검사는 아무것도 못 찾고 **조용히 통과**한다 — 크기(pt)·위치로 판정할 것.
"""
import re

from core.render_vivlio import probe


class Report(object):
    """결함 모음. 하나라도 있으면 게이트 실패."""

    def __init__(self, title=""):
        self.title = title
        self.fails = []
        self.warns = []
        self.notes = []

    def fail(self, msg):
        self.fails.append(msg)
        return self

    def note(self, msg):
        self.notes.append(msg)
        return self

    def warn(self, msg):
        """게이트를 떨어뜨리지는 않지만 사람이 봐야 하는 것."""
        self.warns.append(msg)
        return self

    def design(self, msg, s):
        """디자인 게이트 판정 — `strict` 면 결함, 아니면 경고.

        기존 납품 교재는 고치지 않는다(납품 중이라 지면이 바뀌면 안 된다) →
        기본이 경고다. 신규 조판은 `verify.design.strict: true` 로 켤 것.
        """
        return self.fail(msg) if (s or {}).get("strict") else self.warn(msg)

    @property
    def ok(self):
        return not self.fails

    def merge(self, other):
        self.fails += other.fails
        self.warns += getattr(other, "warns", [])
        self.notes += other.notes
        return self

    def print(self, log=None):
        log = log or print
        if self.title:
            log(f"■ {self.title}")
        for n in self.notes:
            log(f"  {n}")
        if self.warns:
            log("■ 경고 (게이트는 통과 — 사람이 판단할 것)")
            for w in self.warns:
                log(f"  ! {w}")
        if self.fails:
            log("■ 결함")
            for f in self.fails:
                log(f"  - {f}")
        else:
            log("■ 게이트 통과")
        return self.ok


# ── ① 누락 / 순서 ────────────────────────────────────────────────────────
def check_sequence(texts, seq, report, limit=12):
    """`seq` = [(설명, 텍스트)] 를 **조판 순서대로** PDF 전문에서 찾는다.

    위치가 뒤로만 가야 한다. 있는데 앞에 있으면 '순서 어긋남', 아예 없으면 '누락'.
    """
    allt = "".join(probe.norm(t) for t in texts)
    pos, missing, disorder = 0, [], []
    for label, text in seq:
        t = probe.norm(text)
        if not t:
            continue
        idx = allt.find(t, pos)
        if idx < 0:
            (disorder if allt.find(t) >= 0 else missing).append(label)
        else:
            pos = idx
    if missing:
        report.fail(f"누락 {len(missing)}건: {missing[:limit]}")
    if disorder:
        report.fail(f"순서 어긋남 {len(disorder)}건: {disorder[:limit]}")
    return missing, disorder


# ── ② 판면 넘침 ─────────────────────────────────────────────────────────
def check_overflow(pdf, frame, report, skip_pages=(), tol=1.5, limit=8):
    """본문이 판면(좌·우·아래)을 벗어났는가.

    frame: {"inner":23, "outer":26, "width":167, "top":25, "bottom":277.5}
      inner  = 왼쪽 면의 왼쪽 여백(= 안쪽), outer = 오른쪽 면의 왼쪽 여백
      top/bottom 밖(머리·꼬리)은 대상에서 뺀다.
    """
    over = []
    skip = set(skip_pages)
    with probe.open_pdf(pdf) as doc:
        for i, page in enumerate(doc):
            n = i + 1
            if n in skip:
                continue
            left = frame["inner"] if probe.is_left(n) else frame["outer"]
            right = left + frame["width"]
            for x0, y0, x1, y1 in probe.text_blocks_mm(page):
                if y0 < frame["top"] or y0 > frame["bottom"]:
                    continue
                if (x0 < left - tol or x1 > right + tol
                        or y1 > frame["bottom"]):
                    over.append((n, round(x0, 1), round(x1, 1), round(y1, 1)))
    if over:
        report.fail(f"판면 넘침 {len(over)}건: {over[:limit]}")
    return over


# ── ③ 준-빈면 ───────────────────────────────────────────────────────────
def check_blanks(texts, report, ignore_chars="", expect=(), limit=20):
    """뜻하지 않게 비어 있는 쪽. `expect` 는 의도된 빈 면(간지·MEMO)."""
    blanks = probe.blank_pages(texts, ignore_chars)
    unexpected = [p for p in blanks if p not in set(expect)]
    report.note(f"빈 면(간지·MEMO 포함): {blanks[:limit]}")
    if expect and unexpected:
        report.fail(f"예상 밖 빈 면 {len(unexpected)}쪽: {unexpected[:limit]}")
    return blanks


# ── ④ TrimBox / 도련 ────────────────────────────────────────────────────
def check_trimbox(pdf, report, bleed=3.0, tol=0.35):
    """전 면에 TrimBox 가 **MediaBox 원점 기준으로** 찍혔는가.

    `set_cropbox` 를 먼저 부르면 TrimBox 가 되돌아간다 — 그 사고를 잡는 게이트.
    """
    bad = []
    with probe.open_pdf(pdf) as doc:
        for i, page in enumerate(doc):
            mb, _cb, tb = probe.boxes(page)
            if tb is None:
                bad.append((i + 1, "없음"))
                continue
            want = (mb[0] + bleed, mb[1] + bleed, mb[2] - bleed, mb[3] - bleed)
            if any(abs(a - b) > tol for a, b in zip(tb, want)):
                bad.append((i + 1, tuple(round(v, 2) for v in tb)))
    if bad:
        report.fail(f"TrimBox 어긋남 {len(bad)}면: {bad[:8]}")
    return bad


def check_bleed_coverage(pdf, report, bleed=3.0, tol=0.3, min_len=20.0,
                         skip_pages=(), limit=8):
    """재단선에 **닿는** 색면이 도련까지 안 나간 곳.

    도련은 옮기는 게 아니라 늘리는 것 — 재단선에서 시작해 페이지 끝까지 3mm 를
    더 그려야 한다. 재단선에 딱 맞춰 끝난 색면은 재단 후 흰 줄이 남는다.
    """
    bad = []
    skip = set(skip_pages)
    with probe.open_pdf(pdf) as doc:
        for i, page in enumerate(doc):
            n = i + 1
            if n in skip:
                continue
            mb, _cb, _tb = probe.boxes(page)
            W, H = mb[2] - mb[0], mb[3] - mb[1]
            for rect, fill, _color, _w in probe.drawings_mm(page):
                if not fill:
                    continue
                x0, y0, x1, y1 = rect
                w, h = x1 - x0, y1 - y0
                if w < min_len and h < min_len:
                    continue
                # 재단선에 정확히 맞춰 끝난 변 = 도련 미달
                if h >= min_len and abs(x0 - bleed) < tol and x0 > tol:
                    bad.append((n, "왼쪽", round(x0, 2)))
                if h >= min_len and abs(x1 - (W - bleed)) < tol and x1 < W - tol:
                    bad.append((n, "오른쪽", round(x1, 2)))
                if w >= min_len and abs(y0 - bleed) < tol and y0 > tol:
                    bad.append((n, "위", round(y0, 2)))
                if w >= min_len and abs(y1 - (H - bleed)) < tol and y1 < H - tol:
                    bad.append((n, "아래", round(y1, 2)))
    if bad:
        report.fail(f"도련 미달 색면 {len(bad)}건: {bad[:limit]}")
    return bad


# ── ⑤ 빈칸 유실 ─────────────────────────────────────────────────────────
def count_gaps(t):
    """원고/PDF 의 빈칸 수 — 밑줄형(`___`)과 공백형(3칸 이상) 둘 다."""
    return (len(re.findall(r"_{3,}", t))
            + len(re.findall(r"[  ]{3,}", t)))


def check_gaps(items, texts, report, limit=10):
    """items = [(라벨, 원고텍스트, 찾기키)] — 원고 빈칸 수가 PDF 에서 줄었는가."""
    flat = [probe.norm(t) for t in texts]
    lost = []
    for label, src, key in items:
        want = count_gaps(src)
        if not want:
            continue
        k = probe.norm(key)
        pg = [i for i, t in enumerate(flat) if k and k in t]
        got = count_gaps(texts[pg[0]]) if pg else -1
        if got < want:
            lost.append((label, want, got))
    if lost:
        report.fail(f"빈칸 유실 {len(lost)}건(항목, 원고, PDF): {lost[:limit]}")
    return lost


# ── ⑥ 상자 면 걸침 ──────────────────────────────────────────────────────
def check_box_cut(pdf, report, top, bottom, min_w=150.0, limit=6):
    """테두리 상자가 면 위/아래에서 잘렸는가."""
    cut = []
    with probe.open_pdf(pdf) as doc:
        for i, page in enumerate(doc):
            for rect, _fill, color, _w in probe.drawings_mm(page):
                if not color or (rect[2] - rect[0]) < min_w:
                    continue
                y0, y1 = rect[1], rect[3]
                if y0 > top - 3 and (y0 < top + 2 or y1 > bottom):
                    cut.append((i + 1, round(y0, 1), round(y1, 1)))
    if cut:
        report.fail(f"상자 면 걸침 {len(cut)}건: {cut[:limit]}")
    return cut
