# -*- coding: utf-8 -*-
"""PDF 원고 → 단락 목록 (Step3 전용) — docx/hwp 추출기와 같은 모양으로 낸다.

    [{"text": str, "runs": [{"t": str, "ul": bool}]}]
    (+ image_dir 지정 시 그림 단락 {"text": "", "runs": [], "image": {...}})

PDF 에는 '단락'이 없다. 글자와 좌표만 있으므로 다음 순서로 되살린다.

1. **시각 줄** — 글자를 기준선(baseline)으로 모은다. PDF 의 '줄' 객체는 믿지
   않는다: 크롬·한컴 PDF 는 양끝정렬 줄을 **낱말마다 별개 줄**로 쪼개 내고
   (2026-09-12 실측: 너른터·아잉카 원고), 첨자 각주번호('것은?1)')는 기준선이
   살짝 떠 있어 따로 떨어진다.
2. **단 나누기** — 쪽 가운데 띠에 글자가 거의 없으면 2단으로 보고 왼쪽 단을
   먼저 읽는다. 두 단을 가로지르는 줄(제목 등)은 띠(band) 경계가 된다.
3. **머리말·꼬리말** — 쪽 위·아래 가장자리에서 여러 쪽에 되풀이되는 줄과
   쪽번호만 있는 줄은 버린다(숫자는 같은 것으로 본다).
4. **단락 경계** — "다음 줄 첫 낱말이 앞줄 끝에 들어갈 자리가 있었나"로 본다.
   자리가 있었는데 줄을 바꿨다면 단락이 끝난 것이다. 양끝정렬·왼쪽정렬
   어느 쪽에서도 성립한다. 여기에 줄 사이 빈 간격·글자 크기 변화·
   (앞줄이 문장부호로 끝났을 때의) 번호/선지 머리를 더한다.
5. **밑줄** — PDF 의 밑줄은 글자 속성이 아니라 따로 그린 가는 선이다. 글자
   기준선 바로 아래의 선을 글자 단위로 대응시킨다. 상자·표 테두리는 글자
   범위보다 넓게 뻗으므로 제외된다.
6. **미주(정답 해설)** — hwp 추출기가 각주/미주를 빼듯이(exclude_footnotes),
   PDF 끝에 본문으로 찍힌 미주 구간을 본문 각주번호('것은?1)')와 같은 번호
   순열로 알아보고 잘라낸다 (아잉카 수특라이트 12강: 'Answer Keys' 2쪽).

글자 정보가 깨졌거나(Ghostscript 재출력본 — 공백이 'ா', 한글이 엉뚱한 문자)
글자 정보가 없는(스캔본) PDF 는 **조용히 넘기지 않고** PdfTextUnreadable 로
멈춘다. 한글 OCR 은 설치돼 있지 않다(tesseract eng 만).
"""
import hashlib
import logging
import math
import os
import re
import statistics
import unicodedata

_LOG = logging.getLogger(__name__)


class PdfTextUnreadable(RuntimeError):
    """PDF 에서 원고 글자를 믿고 읽을 수 없음 (깨진 글꼴 대응표·스캔본)."""


# ── 글자 건강도 ──────────────────────────────────────────────────────────────

_OK_RANGES = (
    (0x0020, 0x007E), (0x00A0, 0x024F),      # 라틴
    (0x0370, 0x03FF),                        # 그리스(수식 기호)
    (0x1100, 0x11FF), (0x3130, 0x318F), (0xAC00, 0xD7A3),   # 한글
    (0x2000, 0x206F), (0x2100, 0x21FF),      # 문장부호·기호·화살표
    (0x2200, 0x22FF), (0x2460, 0x24FF),      # 수학 기호·원문자
    (0x2500, 0x27BF),                        # 상자·도형·기타 기호·딩뱃
    (0x3000, 0x303F), (0x3200, 0x32FF),      # CJK 문장부호·괄호 문자
    (0x4E00, 0x9FFF),                        # 한자
    (0xFF00, 0xFFEF),                        # 전각
    (0xFE00, 0xFE0F), (0x1F000, 0x1FAFF),    # 변이 선택자·이모지(날씨 아이콘 등)
)


def _ok_char(c):
    o = ord(c)
    for a, b in _OK_RANGES:
        if a <= o <= b:
            return True
    return False


# ── 페이지 읽기 ──────────────────────────────────────────────────────────────

def _read_page(page, want_ul, want_img):
    import fitz
    flags = fitz.TEXT_PRESERVE_WHITESPACE | fitz.TEXT_MEDIABOX_CLIP
    if want_img:
        flags |= fitz.TEXT_PRESERVE_IMAGES
    raw = page.get_text("rawdict", flags=flags)
    spans, images = [], []
    for b in raw.get("blocks", []):
        if b.get("type") == 1:
            if want_img and b.get("image"):
                images.append(b)
            continue
        for ln in b.get("lines", []):
            d = ln.get("dir") or (1, 0)
            if abs(d[1]) > 0.1:                  # 세로쓰기·회전 글자(측면 탭 등)
                continue
            for s in ln.get("spans", []):
                size = float(s.get("size") or 0) or 1.0
                chars = []
                for ch in s.get("chars", []):
                    c = ch.get("c", "")
                    if not c or c in ("\x00", "\ufeff", "\u200b"):
                        continue
                    x0, y0, x1, y1 = ch["bbox"]
                    chars.append({"c": c, "x0": x0, "x1": x1,
                                  "base": ch["origin"][1], "size": size,
                                  "ul": False})
                if not chars:
                    continue
                spans.append({"chars": chars,
                              "x0": min(c["x0"] for c in chars),
                              "x1": max(c["x1"] for c in chars),
                              "base": s.get("origin", (0, chars[0]["base"]))[1],
                              "size": size})
    segs = _underline_segments(page) if want_ul else []
    return spans, images, segs


def _underline_segments(page):
    """가로로 누운 가는 선(선분·납작한 사각형) → [(x0, x1, y)]."""
    segs = []
    try:
        drawings = page.get_drawings()
    except Exception:                                          # noqa: BLE001
        return segs
    for g in drawings:
        for it in g.get("items", []):
            kind = it[0]
            if kind == "l":
                a, b = it[1], it[2]
                if abs(a.y - b.y) <= 0.8 and abs(a.x - b.x) >= 2:
                    segs.append((min(a.x, b.x), max(a.x, b.x), (a.y + b.y) / 2))
            elif kind == "re":
                r = it[1]
                if r.height <= 1.6 and r.width >= 2:
                    segs.append((r.x0, r.x1, (r.y0 + r.y1) / 2))
    return segs


# ── 단 나누기 ────────────────────────────────────────────────────────────────

def _column_split(spans, width, height=None):
    """2단 조판이면 가운데 빈 띠의 x 좌표, 아니면 None.

    머리말·꼬리말 영역(쪽 위 10%·아래 8%) 조각은 빼고, 조각 폭은 공백을
    뺀 실제 글자 범위로 잰다 — 가운데 쪽번호·머리말, 줄 끝 공백이 단 밖으로
    뻗은 조각('was       ')이 가운데 띠를 막아 2단 쪽을 1단으로 읽고 좌우
    단 글자를 한 줄로 섞던 문제(수특라이트 12강 21쪽 실측)."""
    body = []
    for s in spans:
        solid = [c for c in s["chars"] if not c["c"].isspace()]
        if not solid:
            continue
        if height and not (0.10 * height <= s["base"] <= 0.92 * height):
            continue
        body.append({"x0": min(c["x0"] for c in solid),
                     "x1": max(c["x1"] for c in solid),
                     "chars": solid})
    if len(body) < 12:
        return None
    n = int(math.ceil(width)) + 2
    occ = [0] * n
    for s in body:
        for x in range(max(0, int(s["x0"])), min(n - 1, int(s["x1"]) + 1)):
            occ[x] += 1
    lo, hi = int(width * 0.28), int(width * 0.72)
    limit = max(2, int(len(body) * 0.03))
    best, run_start = None, None
    for x in range(lo, hi + 1):
        if occ[x] <= limit:
            if run_start is None:
                run_start = x
        else:
            if run_start is not None:
                if best is None or x - run_start > best[1] - best[0]:
                    best = (run_start, x)
                run_start = None
    if run_start is not None:
        if best is None or hi + 1 - run_start > best[1] - best[0]:
            best = (run_start, hi + 1)
    if not best or best[1] - best[0] < 6:
        return None
    split = (best[0] + best[1]) / 2.0
    nl = sum(len(s["chars"]) for s in body if s["x1"] <= split + 1)
    nr = sum(len(s["chars"]) for s in body if s["x0"] >= split - 1)
    tot = sum(len(s["chars"]) for s in body) or 1
    if nl / tot < 0.2 or nr / tot < 0.2:
        return None
    return split


# ── 시각 줄 ──────────────────────────────────────────────────────────────────

def _group_lines(spans):
    spans = sorted(spans, key=lambda s: (s["base"], s["x0"]))
    lines = []
    for s in spans:
        placed = False
        for ln in reversed(lines[-4:]):
            tol = 0.5 * max(ln["size"], s["size"])
            if abs(s["base"] - ln["base"]) <= tol:
                ln["spans"].append(s)
                if s["size"] > ln["size"]:
                    ln["size"], ln["base"] = s["size"], s["base"]
                placed = True
                break
        if not placed:
            lines.append({"base": s["base"], "size": s["size"], "spans": [s]})
    out = []
    for ln in lines:
        chars = _line_chars(ln)
        if not chars:
            continue
        rec = {"chars": chars, "base": ln["base"], "size": ln["size"]}
        _finish_line(rec)
        out.append(rec)
    return out


def _finish_line(rec):
    """글자 목록에서 줄의 글·좌우 끝·대표 크기를 (다시) 계산한다."""
    chars = rec["chars"]
    text = "".join(c["c"] for c in chars)
    # 밑줄 친 공백(빈칸)은 지면에 보이는 글자다 — 줄 끝 계산에 넣는다.
    # 빼면 빈칸이 줄 머리/끝에 걸린 지문이 '앞줄 끝에 자리가 남았다'로
    # 읽혀 두 단락으로 갈라진다(수특라이트 12강 실측).
    solid = [c for c in chars if not c["c"].isspace() or c.get("ul")]
    rec["text"] = text
    rec["x0"] = min(c["x0"] for c in solid) if solid else chars[0]["x0"]
    rec["x1"] = max(c["x1"] for c in solid) if solid else chars[-1]["x1"]
    # 줄 크기 = 한글·영문 글자의 대표 크기. 숫자·문장부호를 넣으면 '오.47)'
    # 처럼 첨자 각주번호가 섞인 짧은 줄이 6pt 로 재져 글자 크기가 바뀐
    # 것으로 오판된다(수특라이트 12강 '쓰시|오.' 분리 실측).
    letters = [c["size"] for c in chars if c["c"].isalpha()]
    pool = letters or [c["size"] for c in solid]
    rec["size"] = statistics.median(pool) if pool else rec["size"]


def _line_chars(ln):
    chars = sorted((c for s in ln["spans"] for c in s["chars"]),
                   key=lambda c: (c["x0"], c["x1"]))
    out = []
    for c in chars:
        if out:
            p = out[-1]
            # 가짜 굵게(같은 글자를 살짝 비껴 두 번 찍기) — 두 번째를 버린다
            if c["c"] == p["c"] and abs(c["x0"] - p["x0"]) < 0.5:
                continue
            gap = c["x0"] - p["x1"]
            if (gap > 0.25 * max(c["size"], p["size"])
                    and not p["c"].isspace() and not c["c"].isspace()):
                out.append({"c": " ", "x0": p["x1"], "x1": c["x0"],
                            "base": c["base"], "size": c["size"],
                            "ul": False, "syn": True})
        out.append(dict(c))
    return out


# ── 밑줄 대응 ────────────────────────────────────────────────────────────────

def _apply_underlines(lines, segs):
    if not segs or not lines:
        return
    for x0, x1, y in segs:
        hit = []
        for ln in lines:
            sz = ln["size"]
            if not (ln["base"] - 0.25 * sz <= y <= ln["base"] + 0.45 * sz):
                continue
            for c in ln["chars"]:
                cx = (c["x0"] + c["x1"]) / 2.0
                if x0 - 0.3 <= cx <= x1 + 0.3:
                    hit.append((ln, c))
        if not hit:
            continue
        # 글자에 붙은 선만 밑줄 — 글자 범위보다 넓게 뻗는 선은 상자/표 테두리
        cx0 = min(c["x0"] for _, c in hit)
        cx1 = max(c["x1"] for _, c in hit)
        slack = max(3.0, 0.6 * max(ln["size"] for ln, _ in hit))
        if x0 < cx0 - slack or x1 > cx1 + slack:
            continue
        for _, c in hit:
            c["ul"] = True
    # 합성 공백은 양옆이 모두 밑줄일 때만 밑줄 (밑줄 친 구절 안의 낱말 사이)
    for ln in lines:
        ch = ln["chars"]
        for i, c in enumerate(ch):
            if c.get("syn") and 0 < i < len(ch) - 1:
                c["ul"] = ch[i - 1]["ul"] and ch[i + 1]["ul"]


# ── 머리말·꼬리말 ────────────────────────────────────────────────────────────

_RE_PAGENO = re.compile(
    r"^(?:[-–—·\s]*#[-–—·\s]*|#\s*/\s*#|(?:page|p\.?)\s*#|#\s*쪽|#\s*페이지)$", re.I)


def _margin_key(text):
    return re.sub(r"\d+", "#", re.sub(r"\s+", "", unicodedata.normalize("NFC", text)))


def _margin_pieces(ln):
    """큰 간격(1.5em 초과)으로 떨어진 덩어리들의 키 — 한 쪽에서는 세 조각
    ('너른터' · '- 1 -' · 'nernter.com')으로, 다른 쪽(1단 쪽)에서는 한 줄로
    합쳐져 나오는 꼬리말을 같은 것으로 보기 위해."""
    pieces, cur, last = [], [], None
    for c in ln["chars"]:
        if c["c"].isspace():
            continue
        if last is not None and c["x0"] - last["x1"] > 1.5 * max(c["size"], 1):
            pieces.append("".join(cur))
            cur = []
        cur.append(c["c"])
        last = c
    if cur:
        pieces.append("".join(cur))
    return [_margin_key(p) for p in pieces if p.strip()]


def _drop_margins(pages):
    """pages: [{"h": H, "lines": [...]}] — 머리말/꼬리말 줄 제거 (제자리)."""
    npg = len(pages)
    seen = {}
    for pi, pg in enumerate(pages):
        H = pg["h"]
        for ln in pg["lines"]:
            zone = ("top" if ln["base"] < 0.10 * H
                    else "bot" if ln["base"] > 0.92 * H else None)
            ln["_zone"] = zone
            if zone and ln["text"].strip():
                seen.setdefault((zone, _margin_key(ln["text"])), set()).add(pi)
                for pk in _margin_pieces(ln):
                    seen.setdefault((zone, pk), set()).add(pi)
    need = max(2, int(math.ceil(0.3 * npg)))
    dropped = 0
    for pg in pages:
        keep = []
        for ln in pg["lines"]:
            z = ln.get("_zone")
            if z and ln["text"].strip():
                key = _margin_key(ln["text"])
                reps = len(seen.get((z, key), ()))

                def _rep(k):
                    return ((npg >= 2 and len(seen.get((z, k), ())) >= need)
                            or _RE_PAGENO.match(k))
                pieces = _margin_pieces(ln)
                if _rep(key) or (len(pieces) >= 2 and all(_rep(k) for k in pieces)):
                    dropped += 1
                    continue
            keep.append(ln)
        pg["lines"] = keep
    return dropped


# ── 읽는 순서 ────────────────────────────────────────────────────────────────

def _page_sequence(lines, split):
    """한 쪽의 줄 → 읽는 순서 [(col, line)] (col: 'S'|'L'|'R'|'F')."""
    if split is None:
        return [("S", ln) for ln in sorted(lines, key=lambda l: l["base"])]
    L, R, F = [], [], []
    for ln in lines:
        if ln["x1"] <= split + 1:
            L.append(ln)
        elif ln["x0"] >= split - 1:
            R.append(ln)
        else:
            F.append(ln)
    F.sort(key=lambda l: l["base"])
    bounds = [-1e9] + [f["base"] for f in F] + [1e9]
    seq = []
    for i in range(len(bounds) - 1):
        a, b = bounds[i], bounds[i + 1]
        seq += [("L", l) for l in sorted(L, key=lambda l: l["base"])
                if a < l["base"] <= b]
        seq += [("R", l) for l in sorted(R, key=lambda l: l["base"])
                if a < l["base"] <= b]
        if i < len(F):
            seq.append(("F", F[i]))
    return seq


def _col_right_edges(pages):
    """(쪽, 단)별 오른쪽 끝 — 글자 15자 이상 줄의 90% 분위. 표본이 적으면
    문서 전체의 같은 단 값으로."""
    per, pool = {}, {}
    for pi, pg in enumerate(pages):
        for col, ln in pg["seq"]:
            if len(ln["text"].strip()) >= 15:
                per.setdefault((pi, col), []).append(ln["x1"])
                pool.setdefault(col, []).append(ln["x1"])

    def q90(v):
        v = sorted(v)
        return v[min(len(v) - 1, int(0.9 * len(v)))]
    doc = {c: q90(v) for c, v in pool.items() if v}
    page_max = {}
    for pi, pg in enumerate(pages):
        xs = [ln["x1"] for _, ln in pg["seq"]]
        page_max[pi] = max(xs) if xs else 0
    edges = {}
    for pi, pg in enumerate(pages):
        for col in {c for c, _ in pg["seq"]}:
            v = per.get((pi, col), [])
            if col == "F":
                edges[(pi, col)] = page_max[pi]
            elif len(v) >= 3:
                edges[(pi, col)] = q90(v)
            else:
                edges[(pi, col)] = doc.get(col, page_max[pi])
    return edges


# ── 단락 경계 ────────────────────────────────────────────────────────────────

_RE_HEAD = re.compile(
    r"^\s*(?:[①-⑳ⓐ-ⓩ❶-❿⑴-⒇]|\d{1,3}\s*[.)]\s|\(\s*[A-Ea-e가-하]\s*\)"
    r"|\[|<|〈|《|【|\*|※|▶|■|□|◆|◇|○|●|Q\s*\.|[A-E]\s*\.\s)")
# 앞줄이 문장으로 끝났을 때 끊는 머리 — 지문 **안**에도 흔히 오는 원문자
# (ⓐ While…)·(A)/(B) 표지·'3. ' 는 뺀다(줄 머리에 걸려도 지문이 이어진다).
# 원문자 선지는 _CIRCLED(선지 뒤 선지)로, 발문 번호는 _RE_QHEAD 로 따로 본다.
_RE_PARA_HEAD = re.compile(
    r"^\s*(?:\[|<|〈|《|【|\*|※|▶|■|□|◆|◇|○|●|Q\s*\.)")
# 번호 + 한글 지시문 — 영어 지문 속에서 줄 머리에 올 수 없는 모양 (항상 끊는다)
_RE_QHEAD = re.compile(r"^\s*\d{1,3}\s*[.)]\s*[가-힣\[(<“\"]")
_CIRCLED = set("①②③④⑤⑥⑦⑧⑨⑩ⓐⓑⓒⓓⓔ")
_RE_TERMINAL = re.compile(
    r"[.?!…。:;\]\)>》〉】」』\"'”’](?:\s*\d{1,3}\))?\s*$")


def _first_word_width(ln):
    ch = ln["chars"]
    blank = lambda c: c["c"].isspace() and not c.get("ul")
    i = 0
    while i < len(ch) and blank(ch[i]):
        i += 1
    j = i
    while j < len(ch) and not blank(ch[j]):
        j += 1
    if j <= i:
        return 0.0
    return ch[j - 1]["x1"] - ch[i]["x0"]


def _breaks(prev, cur, prev_edge, pitch, para_first="", para_lines=1):
    """(끊나?, 빈 줄 간격 때문인가?)

    para_first: 지금 짓고 있는 단락의 첫 글자 — 선지(①) 단락 뒤에 선지가
        오면 끊는다. 앞 선지 줄이 우연히 단 끝까지 차서(마침표 없음)
        '자리 없음 → 이어짐'으로 읽히는 것을 막는다. 지문 속 '① [minimal]'
        이 줄 머리에 걸린 경우는 앞 단락이 지문이라 끊지 않는다."""
    ptxt, ctxt = prev["text"].rstrip(), cur["text"].lstrip()
    if not ptxt or not ctxt:
        return True, False
    if _RE_QHEAD.match(ctxt):
        return True, False
    if ctxt[0] in _CIRCLED and para_first in _CIRCLED and para_lines <= 3:
        return True, False
    if prev.get("_colkey") == cur.get("_colkey"):
        gap = cur["base"] - prev["base"]
        if gap <= 0:
            return True, False
        if gap > max(1.6 * pitch, 2.0 * prev["size"]):
            return True, True
    big = max(prev["size"], cur["size"])
    if abs(prev["size"] - cur["size"]) > 0.18 * big:
        return True, False
    if _RE_PARA_HEAD.match(ctxt) and _RE_TERMINAL.search(ptxt):
        return True, False
    room = prev_edge - prev["x1"]
    if room > _first_word_width(cur) + 0.35 * prev["size"] + 1.0:
        return True, False
    return False, False


def _is_hangul(c):
    return "가" <= c <= "힣"


def _glue(prev_chars, cur_chars, hangul_joined=False):
    """앞 단락 끝과 다음 줄 사이에 넣을 글자 (없으면 None).

    hangul_joined: 이 문서는 어절에서 줄을 바꿀 때 줄 끝에 공백 글리프를
        남긴다(한컴 PDF 실측 63% vs 크롬 0%). 그런 문서에서 한글-한글 사이에
        공백이 없으면 **글자 단위 줄바꿈**이므로 붙인다 ('새로' + '운' → '새로운')."""
    if not prev_chars or not cur_chars:
        return None
    a, b = prev_chars[-1]["c"], cur_chars[0]["c"]
    if a.isspace() or b.isspace():
        return None
    if hangul_joined and _is_hangul(a) and _is_hangul(b):
        return None
    if (a in "-‐" and len(prev_chars) >= 2 and prev_chars[-2]["c"].isalpha()
            and b.islower()):
        return None                              # 'well-' + 'being'
    return {"c": " ", "ul": prev_chars[-1]["ul"] and cur_chars[0]["ul"]}


def _chars_to_para(chars):
    """글자 목록 → {"text", "runs"} (공백 정리 — 밑줄 공백은 보존)."""
    # 앞뒤 공백 제거
    i, j = 0, len(chars)
    while i < j and chars[i]["c"].isspace() and not chars[i]["ul"]:
        i += 1
    while j > i and chars[j - 1]["c"].isspace() and not chars[j - 1]["ul"]:
        j -= 1
    runs = []
    prev_space = False
    for c in chars[i:j]:
        t, ul = c["c"], bool(c["ul"])
        if t.isspace() and not ul:
            if prev_space:
                continue
            t = " "
            prev_space = True
        else:
            prev_space = False
        if runs and runs[-1]["ul"] == ul:
            runs[-1]["t"] += t
        else:
            runs.append({"t": t, "ul": ul})
    for r in runs:
        r["t"] = unicodedata.normalize("NFC", r["t"])
    text = "".join(r["t"] for r in runs)
    return {"text": text, "runs": runs or [{"t": "", "ul": False}]}


# ── 미주(정답 해설) 구간 ─────────────────────────────────────────────────────

_RE_REF_TAIL = re.compile(r"[?.!…\"”’)\]』」](\s*)(\d{1,3})\)\s*$")
_RE_NOTE_HEAD = re.compile(r"^\s*(\d{1,3})\)\s*\S")


def _trim_tail(p, n):
    """단락 끝 n 글자를 지운다 (runs 도 함께)."""
    if n <= 0:
        return
    p["text"] = p["text"][:-n].rstrip()
    runs = p.get("runs") or []
    while n > 0 and runs:
        r = runs[-1]
        if len(r["t"]) <= n:
            n -= len(r["t"])
            runs.pop()
        else:
            r["t"] = r["t"][:-n]
            n = 0
    if runs:
        runs[-1]["t"] = runs[-1]["t"].rstrip() if not runs[-1]["ul"] else runs[-1]["t"]
    p["runs"] = runs or [{"t": "", "ul": False}]
    p["text"] = "".join(r["t"] for r in p["runs"])


def _cut_endnotes(paras, log=None, label=""):
    refs = []
    first_ref_idx = None
    for i, p in enumerate(paras):
        m = _RE_REF_TAIL.search(p["text"])
        if m:
            refs.append(int(m.group(2)))
            if first_ref_idx is None:
                first_ref_idx = i
    rs = set(refs)
    if len(rs) < 2:
        return paras
    lo = min(rs)
    for k in range(first_ref_idx + 1, len(paras)):
        m = _RE_NOTE_HEAD.match(paras[k]["text"])
        if not m or int(m.group(1)) != lo:
            continue
        nums = [int(mm.group(1)) for mm in
                (_RE_NOTE_HEAD.match(p["text"]) for p in paras[k:]) if mm]
        hits = [n for n in nums if n in rs]
        if len(set(hits)) < max(2, int(0.5 * len(rs))):
            continue
        cut = k
        # 바로 앞의 짧은 표제('Answer Keys', 'EBS … 정답')도 함께. 답란 줄
        # ('ⓓ ⓔ')·빈 단락에서는 멈춘다 — 마지막 문항의 일부다.
        for _ in range(2):
            t = paras[cut - 1]["text"].strip() if cut > 0 else ""
            letters = len(re.findall(r"[A-Za-z가-힣]", t))
            if (t and len(t) <= 30 and letters >= 2 and not _RE_HEAD.match(t)
                    and not re.search(r"[.?!]$", t)):
                cut -= 1
            else:
                break
        if callable(log):
            log(f"[PDF] {label}: 끝의 미주(정답 해설) 구간 {len(paras) - cut}단락 "
                f"제외 — 본문 각주번호 {len(rs)}개와 같은 번호 순열 "
                f"(hwp 원고의 각주/미주 제외와 같은 처리)")
        kept = paras[:cut]
        for p in kept:
            m = _RE_REF_TAIL.search(p["text"])
            if m and int(m.group(2)) in rs:
                _trim_tail(p, len(p["text"]) - m.start(1))
        return kept
    return paras


# ── 본체 ─────────────────────────────────────────────────────────────────────

def _pdf_extract_paragraphs(pdf_path, extract_underline=False,
                            exclude_footnotes=True, image_dir=None, log=None):
    """PDF → 단락 목록. 읽을 수 없는 PDF 는 PdfTextUnreadable."""
    import fitz
    from core.extract.extractors import _write_picture, _normalize_circled_numbers
    label = os.path.basename(pdf_path)
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:                                     # noqa: BLE001
        raise PdfTextUnreadable(f"PDF 를 열 수 없습니다: {label} ({e})")
    try:
        if doc.needs_pass:
            raise PdfTextUnreadable(f"암호가 걸린 PDF 입니다: {label}")
        pages, all_chars, img_pages = [], [], 0
        img_digest_pages = {}
        for pi in range(doc.page_count):
            page = doc[pi]
            spans, images, segs = _read_page(page, extract_underline,
                                             image_dir is not None)
            if not spans and page.get_images():
                img_pages += 1
            W, H = page.rect.width, page.rect.height
            split = _column_split(spans, W, H)
            lines = []
            if split is None:
                lines = _group_lines(spans)
            else:
                # 단마다 따로 줄을 짓는다 — 같은 높이의 좌·우 단 글자가
                # 한 줄로 섞이지 않게. 가로지르는 줄(F)은 따로.
                L = [s for s in spans if s["x1"] <= split + 1]
                R = [s for s in spans if s["x0"] >= split - 1]
                F = [s for s in spans if s not in L and s not in R]
                lines = _group_lines(L) + _group_lines(R) + _group_lines(F)
            _apply_underlines(lines, segs)
            for ln in lines:
                _finish_line(ln)
            imgs = []
            for bi, b in enumerate(images):
                x0, y0, x1, y1 = b["bbox"]
                if (x1 - x0) < 25 or (y1 - y0) < 25:
                    continue
                dig = hashlib.md5(b["image"]).hexdigest()
                img_digest_pages.setdefault(dig, set()).add(pi)
                imgs.append({"img": b, "dig": dig, "key": f"p{pi + 1}_{bi}",
                             "x0": x0, "x1": x1, "base": y0, "y1": y1})
            pages.append({"h": H, "w": W, "split": split, "lines": lines,
                          "imgs": imgs})

        # ── 공백 대체 글리프 ────────────────────────────────────────────────
        # 공백 글리프에 유니코드 대응이 없는 글꼴은 공백을 U+FFFD/제어문자로
        # 낸다(동아(박) 예상문제 실측: 폭 2.8pt 한 가지, 진짜 공백 0개).
        # 폭이 좁고 진짜 공백이 거의 없을 때만 공백으로 되돌린다 — 글자
        # 자체가 깨진 PDF 는 이 조건을 못 맞추고 아래 검사에서 멈춘다.
        subs, real_sp = [], 0
        for pg in pages:
            for ln in pg["lines"]:
                for c in ln["chars"]:
                    o = ord(c["c"][0])
                    if c["c"] == "\ufffd" or o < 0x20:
                        subs.append(c)
                    elif c["c"] == " " and not c.get("syn"):
                        real_sp += 1
        n_all = sum(len(ln["chars"]) for pg in pages for ln in pg["lines"])
        if subs:
            rels = [(c["x1"] - c["x0"]) / (c["size"] or 1) for c in subs]
            rel = statistics.median(rels)
            # 공백이라면 폭이 한 가지다 (동아 100% 균일 vs 깨진 YBM 76% —
            # 여러 글리프가 한데 뭉개진 것). 비율도 공백다워야 한다(≤30%).
            uniform = sum(1 for w in rels
                          if abs(w - rel) <= 0.15 * max(rel, 0.05)) / len(rels)
            if (rel < 0.45 and uniform >= 0.9 and real_sp < 0.2 * len(subs)
                    and len(subs) <= 0.3 * max(1, n_all)):
                for c in subs:
                    c["c"] = " "
                for pg in pages:
                    for ln in pg["lines"]:
                        _finish_line(ln)
                if callable(log):
                    log(f"[PDF] {label}: 공백 글리프 {len(subs)}개가 대체 문자로 "
                        f"들어 있어 공백으로 복원")
        for pg in pages:
            for ln in pg["lines"]:
                all_chars.extend(c["c"] for c in ln["chars"])
        # 줄 끝 공백 관행 — 한글 글자 단위 줄바꿈 판정용 (_glue)
        n_lines = n_trail = 0
        for pg in pages:
            for ln in pg["lines"]:
                if ln["text"].strip():
                    n_lines += 1
                    n_trail += ln["chars"][-1]["c"].isspace()
        hangul_joined = n_lines > 0 and n_trail / n_lines >= 0.3

        # ── 읽을 수 있는 PDF 인가 ───────────────────────────────────────────
        nonspace = [c for c in all_chars if not c.isspace()]
        if len(nonspace) < 30 * max(1, doc.page_count) * 0.2 and img_pages:
            raise PdfTextUnreadable(
                f"글자 정보가 없는 PDF(스캔본으로 보임): {label} — 한글 OCR 이 "
                f"설치돼 있지 않아 읽을 수 없습니다. 한글/워드 원본으로 올려 주세요.")
        if nonspace:
            ok = sum(1 for c in nonspace if _ok_char(c)) / len(nonspace)
            if ok < 0.95:
                bad = sorted({c for c in nonspace if not _ok_char(c)})[:8]
                raise PdfTextUnreadable(
                    f"PDF 의 글자 정보가 깨져 있습니다: {label} (정상 글자 "
                    f"{ok:.0%}, 깨진 예 {''.join(bad)!r}) — 글꼴 대응표가 없는 "
                    f"재출력본입니다. 한글/워드 원본으로 올리거나 원본에서 "
                    f"PDF 를 다시 저장해 주세요.")

        dropped = _drop_margins(pages)

        # ── 읽는 순서 + 단 오른쪽 끝 ────────────────────────────────────────
        for pi, pg in enumerate(pages):
            pg["seq"] = _page_sequence(pg["lines"], pg["split"])
            for col, ln in pg["seq"]:
                ln["_colkey"] = (pi, col)
        edges = _col_right_edges(pages)
        pitches = {}
        for pi, pg in enumerate(pages):
            by = {}
            for col, ln in pg["seq"]:
                by.setdefault(col, []).append(ln)
            for col, ls in by.items():
                d = [b["base"] - a["base"] for a, b in zip(ls, ls[1:])
                     if 0 < b["base"] - a["base"] < 2.2 * a["size"]]
                pitches[(pi, col)] = (statistics.median(d) if d
                                      else 1.3 * (ls[0]["size"] if ls else 10))

        # ── 그림 자리 (반복 로고·가장자리 제외) ─────────────────────────────
        placed_imgs = 0
        for pi, pg in enumerate(pages):
            for im in pg["imgs"]:
                if len(img_digest_pages.get(im["dig"], ())) >= 2:
                    continue
                if im["y1"] < 0.10 * pg["h"] or im["base"] > 0.92 * pg["h"]:
                    continue
                split = pg["split"]
                cx = (im["x0"] + im["x1"]) / 2.0
                col = ("S" if split is None
                       else "L" if im["x1"] <= split + 1
                       else "R" if im["x0"] >= split - 1 else "F")
                # 같은 단에서 그림 위쪽 가장 가까운 줄 뒤에 끼운다
                idx = len(pg["seq"])
                for k, (c2, ln) in enumerate(pg["seq"]):
                    if c2 == col and ln["base"] > im["base"]:
                        idx = k
                        break
                pg["seq"].insert(idx, (col, {"_image": im}))
                placed_imgs += 1

        # ── 단락 짓기 ───────────────────────────────────────────────────────
        paras, cur, prev, cur_lines = [], None, None, 0
        stem = re.sub(r"[^\w가-힣]+", "_", os.path.splitext(label)[0])[:40]

        def flush():
            if cur:
                p = _chars_to_para(cur)
                if p["text"].strip() or any(r["ul"] for r in p["runs"]):
                    paras.append(p)

        for pi, pg in enumerate(pages):
            for col, ln in pg["seq"]:
                if "_image" in ln:
                    flush()
                    cur, prev = None, None
                    im = ln["_image"]
                    b = im["img"]
                    try:
                        os.makedirs(image_dir, exist_ok=True)
                        path, wpx, hpx = _write_picture(
                            b["image"], b.get("ext") or "png", image_dir, stem,
                            im["key"])
                        paras.append({"text": "", "runs": [], "image": {
                            "path": path, "bindata_id": im["key"],
                            "w_mm": round((im["x1"] - im["x0"]) * 25.4 / 72, 2),
                            "h_mm": round((im["y1"] - im["base"]) * 25.4 / 72, 2),
                            "w_px": wpx, "h_px": hpx}})
                    except Exception as e:                     # noqa: BLE001
                        _LOG.warning("[PDF] 그림 추출 실패(%s, %s): %s",
                                     im["key"], label, e)
                    continue
                if prev is None:
                    cur = list(ln["chars"])
                    cur_lines = 1
                    prev = ln
                    continue
                first = next((c["c"] for c in cur if not c["c"].isspace()), "")
                brk, blank = _breaks(prev, ln,
                                     edges.get(prev["_colkey"], prev["x1"]),
                                     pitches.get(prev["_colkey"], 12.0), first,
                                     cur_lines)
                if brk:
                    flush()
                    if blank:
                        paras.append({"text": "", "runs": [{"t": "", "ul": False}]})
                    cur = list(ln["chars"])
                    cur_lines = 1
                else:
                    cur_lines += 1
                    g = _glue(cur, ln["chars"], hangul_joined)
                    if g:
                        cur.append(g)
                    cur.extend(ln["chars"])
                prev = ln
        flush()

        if exclude_footnotes:
            paras = _cut_endnotes(paras, log, label)
        paras = _normalize_circled_numbers(paras)
        if callable(log):
            ul_runs = sum(1 for p in paras for r in p.get("runs") or [] if r["ul"])
            log(f"[PDF] {label}: {doc.page_count}쪽 → 단락 {len(paras)}개"
                f" (2단 {sum(1 for p in pages if p['split'])}쪽, 머리말·꼬리말 "
                f"{dropped}줄 제외" + (f", 밑줄 {ul_runs}곳" if extract_underline
                                     else "")
                + (f", 그림 {placed_imgs}개" if placed_imgs else "") + ")")
        return paras
    finally:
        doc.close()


def pdf_content_words(pdf_path):
    """중복 판정용 내용 낱말 집합 (영어 4자+ 소문자 · 한글 2자+).
    읽을 수 없으면 PdfTextUnreadable."""
    paras = _pdf_extract_paragraphs(pdf_path, False, exclude_footnotes=True)
    return content_words(p.get("text", "") for p in paras)


def content_words(texts):
    out = set()
    for t in texts:
        t = unicodedata.normalize("NFC", t or "")
        out.update(w.lower() for w in re.findall(r"[A-Za-z]{4,}", t))
        out.update(re.findall(r"[가-힣]{2,}", t))
    return out
