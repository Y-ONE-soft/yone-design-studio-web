# -*- coding: utf-8 -*-
"""기출 정본 계측 — 실제 학교 시험지 PDF 에서 '학교 조판 규칙'을 뽑아낸다.

**정본은 완성된 InDesign 파일이 아니라 실제 학교 기출 시험지다.** 동형모의고사는
그 시험지를 흉내 내는 물건이므로, 규칙의 진실은 언제나 기출 쪽에 있다. 이 모듈은
기출 PDF 한 부를 읽어 다음을 실측값·표본과 함께 뽑는다.

  판형/여백/단          size·본문 bbox·단 수·단 폭·단 간격
  단락 역할별 서체       (서체, 크기) 별 글자수·행간·왼쪽 x 분포(= 들여쓰기)
  문항 묶음 표기         【 6, 서답형 1 】 / [7~8] / <4번, 서답형1번> / 없음
  서답형 라벨            [서답형 1] / 서술형1. / 〔서술형4〕 / 서답형 1.
  배점 표기              〔2.9점〕 / [3점] / (0.4점) / 【3점】
  <보기>/<조건>          표기 형태 + 테두리 상자인지 · 맨텍스트인지
  마무리                 - 끝 - / - 수고하셨습니다. - / 확인 사항 / 배점표
  기타 글리프            화살표 코드포인트, (A)(B) 짝 선지 구분자

산출은 '판정'이 아니라 **증거**다. 프로파일(profiles/*.json)은 사람이 이 증거를
보고 확정하며, 확정값이 기출과 어긋나면 게이트가 잡는다.
"""
import collections
import os
import re
import unicodedata

try:
    import fitz
except ImportError:  # 계측 전용 — 조판 경로는 fitz 없이 돈다
    fitz = None

MM = 25.4 / 72.0


def _nfc(s):
    return unicodedata.normalize("NFC", s or "")


# ── 표기 패턴 ───────────────────────────────────────────────────────────────
# 묶음 머리: 여는 괄호 종류별로 따로 잡아야 학교 방언이 드러난다.
RE_GROUP = {
    "lenticular": re.compile(r"【[^】\n]{1,40}】"),   # 【 6, 서답형 1 】
    "angle": re.compile(r"<[^<>\n]{0,30}(?:번|서답형|서술형)[^<>\n]{0,30}>"),
    "square": re.compile(r"\[\s*\d{1,3}\s*[~\-–—]\s*\d{1,3}\s*\]"),
    "paren": re.compile(r"\(\s*\d{1,3}\s*[~\-–—]\s*\d{1,3}\s*\)"),
    "tortoise": re.compile(r"〔[^〕\n]{1,40}〕"),
}
RE_ESSAY_LABEL = {
    "[서답형 N]": re.compile(r"\[\s*서답형\s*\d+\s*(?:번)?\s*\]"),
    "[서술형 N]": re.compile(r"\[\s*서술형\s*\d+\s*(?:번)?\s*\]"),
    "〔서술형N〕": re.compile(r"〔\s*서[술답]형\s*\d+\s*(?:번)?\s*〕"),
    "【서답형N】": re.compile(r"【\s*서[술답]형\s*\d+\s*(?:번)?\s*】"),
    "서술형N.": re.compile(r"(?m)^\s*서술형\s*\d+\s*[.)]"),
    "서답형N.": re.compile(r"(?m)^\s*서답형\s*\d+\s*[.)]"),
    "서답형N": re.compile(r"(?m)^\s*서[술답]형\s*\d+\s*(?![.)0-9])"),
}
RE_SCORE = {
    "〔N점〕": re.compile(r"〔\s*\d+(?:\.\d+)?\s*점[^〕]{0,20}〕"),
    "[N점]": re.compile(r"\[\s*\d+(?:\.\d+)?\s*점[^\]]{0,20}\]"),
    "(N점)": re.compile(r"\(\s*\d+(?:\.\d+)?\s*점[^)]{0,20}\)"),
    "【N점】": re.compile(r"【\s*\d+(?:\.\d+)?\s*점[^】]{0,20}】"),
}
RE_GIVEN = {
    "<보기>": re.compile(r"<\s*보\s*기\s*>"),
    "〈보기〉": re.compile(r"〈\s*보\s*기\s*〉"),
    "[보기]": re.compile(r"\[\s*보\s*기\s*\]"),
    "<Keywords>": re.compile(r"<\s*Keywords?\s*>", re.I),
    "<요약문>": re.compile(r"<\s*요약문?\s*>"),
}
RE_COND = {
    "<조건>": re.compile(r"<\s*조\s*건\s*>"),
    "〈조건〉": re.compile(r"〈\s*조\s*건\s*〉"),
    "[조건]": re.compile(r"\[\s*조\s*건\s*\]"),
    "<조 건>": re.compile(r"<\s*조\s+건\s*>"),
}
RE_QNUM = re.compile(r"(?m)^\s*(\d{1,2})\s*([.)])\s*\S")
RE_ENDING = re.compile(
    r"[-–—▸▶=~]*\s*"
    r"(?:끝|수고\s*하셨습니다|The\s*End|이상)\s*[.]?\s*"
    r"[-–—▸◂=~]*")
RE_COPY = re.compile(r"[^\n]*저작권[^\n]*")

# 화살표류 코드포인트(요약 화살표 방언 판별)
_ARROW_CPS = set(range(0x2190, 0x21FF)) | set(range(0x2B00, 0x2B0F)) | {
    0x2193, 0x21D3, 0x21E9, 0x2B07, 0x1F87B, 0x001A}


def _spans(page):
    """페이지의 텍스트 span 목록 (font/size/bbox/text)."""
    out = []
    d = page.get_text("dict")
    for blk in d.get("blocks", []):
        if blk.get("type") != 0:
            continue
        for line in blk.get("lines", []):
            for sp in line.get("spans", []):
                t = sp.get("text", "")
                if not t.strip():
                    continue
                out.append({
                    "t": _nfc(t), "font": sp.get("font", ""),
                    "size": round(sp.get("size", 0), 2),
                    "flags": sp.get("flags", 0),
                    "x0": sp["bbox"][0], "y0": sp["bbox"][1],
                    "x1": sp["bbox"][2], "y1": sp["bbox"][3],
                    "line_y": round(line["bbox"][1], 1),
                })
    return out


def _columns(spans, page_w):
    """본문 span 의 x0 히스토그램으로 단 개수·좌표 추정."""
    if not spans:
        return {}
    xs = sorted(s["x0"] for s in spans)
    mid = page_w / 2.0
    left = [x for x in xs if x < mid]
    right = [x for x in xs if x >= mid]
    if not left or not right or len(right) < len(xs) * 0.15:
        return {"count": 1, "left_mm": round(min(xs) * MM, 1),
                "right_mm": round(max(s["x1"] for s in spans) * MM, 1)}
    l0, r0 = min(left), min(right)
    l1 = max(s["x1"] for s in spans if s["x0"] < mid)
    r1 = max(s["x1"] for s in spans if s["x0"] >= mid)
    return {"count": 2,
            "col1_mm": [round(l0 * MM, 1), round(l1 * MM, 1)],
            "col2_mm": [round(r0 * MM, 1), round(r1 * MM, 1)],
            "gap_mm": round((r0 - l1) * MM, 1),
            "col_w_mm": round((l1 - l0) * MM, 1)}


def _font_census(all_spans):
    c = collections.Counter()
    for s in all_spans:
        c[(s["font"], s["size"])] += len(s["t"])
    return [{"font": f, "size": sz, "chars": n}
            for (f, sz), n in c.most_common(14)]


def _line_gaps(all_spans):
    """같은 서체·크기 안에서의 연속 줄 간격 최빈값 = 행간."""
    by = collections.defaultdict(list)
    for s in all_spans:
        by[(s["page"], s["font"], s["size"])].append(s["line_y"])
    gaps = collections.defaultdict(collections.Counter)
    for (_pg, f, sz), ys in by.items():
        ys = sorted(set(ys))
        for a, b in zip(ys, ys[1:]):
            g = round(b - a, 1)
            if 0 < g < 60:
                gaps[(f, sz)][g] += 1
    out = {}
    for k, c in gaps.items():
        g, n = c.most_common(1)[0]
        if n >= 3:
            out["%s@%s" % k] = {"leading_pt": g, "n": n}
    return out


def _rect_boxes(page):
    """그려진 사각형(테두리 상자) 목록 — <보기>/<조건> 상자 판정용."""
    out = []
    try:
        drawings = page.get_drawings()
    except Exception:
        return out
    for d in drawings:
        r = d.get("rect")
        if not r:
            continue
        w, h = r.width, r.height
        if w < 40 or h < 8:      # 밑줄·괘선 제외
            continue
        out.append({"x0": r.x0, "y0": r.y0, "x1": r.x1, "y1": r.y1,
                    "w_mm": round(w * MM, 1), "h_mm": round(h * MM, 1),
                    "stroke": bool(d.get("color")), "fill": bool(d.get("fill")),
                    "width_pt": round(d.get("width") or 0, 2)})
    return out


def _in_box(x, y, boxes, pad=6):
    for b in boxes:
        if b["x0"] - pad <= x <= b["x1"] + pad and b["y0"] - pad <= y <= b["y1"] + pad:
            return b
    return None


def _samples(pattern, text, limit=6):
    seen, out = set(), []
    for m in pattern.finditer(text):
        s = m.group(0).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= limit:
            break
    return out


def _detect_ab_separator(full):
    """(A)(B) 짝맞추기 선지의 열 구분자."""
    seps = [("-----", re.compile(r"-{3,}")),
            ("…", re.compile(r"…")),
            ("···", re.compile(r"·{2,}")),
            ("~~~", re.compile(r"~{3,}")),
            ("공백열", re.compile(r"[①-⑤]\s*\S+\s{4,}\S+"))]
    out = {}
    for name, pat in seps:
        n = len(pat.findall(full))
        if n:
            out[name] = n
    return out


def _indent_by_size(body, cols):
    """서체·크기별 첫 x 좌표 분포 → 들여쓰기 실측(단 왼쪽 기준 mm)."""
    if not body:
        return {}
    base = None
    if cols.get("count") == 2:
        base = cols["col1_mm"][0]
    elif cols.get("left_mm") is not None:
        base = cols["left_mm"]
    if base is None:
        return {}
    by = collections.defaultdict(collections.Counter)
    for s in body:
        by["%s@%s" % (s["font"], s["size"])][round(s["x0"] * MM - base, 1)] += 1
    out = {}
    for k, c in by.items():
        tot = sum(c.values())
        if tot < 6:
            continue
        out[k] = {"x_mm": [x for x, _ in c.most_common(3)], "n": tot}
    return out


def scan(pdf_path, max_pages=None):
    """기출 PDF 한 부 → 증거 dict."""
    if fitz is None:
        raise RuntimeError("PyMuPDF(fitz) 필요 — 계측 전용 의존")
    doc = fitz.open(pdf_path)
    n = doc.page_count
    pages = range(n if max_pages is None else min(n, max_pages))

    rec = {"file": _nfc(os.path.basename(pdf_path)), "path": pdf_path, "pages": n}
    pg0 = doc[0]
    rec["page_mm"] = [round(pg0.rect.width * MM, 1), round(pg0.rect.height * MM, 1)]

    all_spans, texts, boxes_by_page = [], [], {}
    for i in pages:
        page = doc[i]
        sp = _spans(page)
        for s in sp:
            s["page"] = i + 1
        all_spans += sp
        texts.append(_nfc(page.get_text()))
        boxes_by_page[i + 1] = _rect_boxes(page)

    full = "\n".join(texts)
    rec["text_chars"] = len(full.strip())
    rec["scanned"] = rec["text_chars"] < 500      # 텍스트층 없음 = 스캔본
    if rec["scanned"]:
        doc.close()
        return rec

    # ── 지면 골격 ──
    body = [s for s in all_spans if s["page"] >= 2] or all_spans
    rec["columns"] = _columns(body, pg0.rect.width)
    ys = [s["y0"] for s in body]
    rec["body_top_mm"] = round(min(ys) * MM, 1) if ys else None
    rec["body_bottom_mm"] = round(max(s["y1"] for s in body) * MM, 1) if body else None
    rec["fonts"] = _font_census(all_spans)
    rec["leading"] = _line_gaps(all_spans)

    # ── 표기 방언 ──
    rec["group_label"] = {k: _samples(p, full) for k, p in RE_GROUP.items()
                          if p.search(full)}
    rec["essay_label"] = {k: _samples(p, full) for k, p in RE_ESSAY_LABEL.items()
                          if p.search(full)}
    rec["score_mark"] = {k: _samples(p, full, 8) for k, p in RE_SCORE.items()
                         if p.search(full)}
    rec["given_marker"] = {k: _samples(p, full, 3) for k, p in RE_GIVEN.items()
                           if p.search(full)}
    rec["cond_marker"] = {k: _samples(p, full, 3) for k, p in RE_COND.items()
                          if p.search(full)}

    # 문항 번호 표기 (1. vs 1))
    rec["qnum_punct"] = dict(collections.Counter(
        m.group(2) for m in RE_QNUM.finditer(full)))

    # ── <보기>/<조건> 이 상자 안인가 ──
    def _box_state(markers):
        st = {}
        for name, pat in markers.items():
            hits = []
            for s in all_spans:
                if pat.search(s["t"]):
                    b = _in_box(s["x0"], s["y0"], boxes_by_page.get(s["page"], []))
                    hits.append({"page": s["page"], "boxed": bool(b),
                                 "box_mm": [b["w_mm"], b["h_mm"]] if b else None,
                                 "stroke_pt": b["width_pt"] if b else None,
                                 "size": s["size"], "font": s["font"],
                                 "x_mm": round(s["x0"] * MM, 1)})
                if len(hits) >= 4:
                    break
            if hits:
                st[name] = hits
        return st

    rec["given_box"] = _box_state(RE_GIVEN)
    rec["cond_box"] = _box_state(RE_COND)

    # ── 마무리 ──
    rec["ending_hits"] = _samples(RE_ENDING, full, 6)
    rec["last_page_tail"] = (texts[-1] if texts else "").strip()[-600:]
    rec["has_score_table"] = bool(re.search(r"문항\s*\n\s*배점", full))
    rec["copyright"] = _samples(RE_COPY, full, 2)

    # ── 글리프 ──
    arrows = collections.Counter()
    for ch in full:
        if ord(ch) in _ARROW_CPS:
            arrows["U+%04X %s" % (ord(ch), ch)] += 1
    rec["arrows"] = dict(arrows.most_common(8))
    rec["ab_separator"] = _detect_ab_separator(full)

    # ── 역할별 들여쓰기(단 왼쪽 기준) ──
    rec["indent"] = _indent_by_size(body, rec.get("columns") or {})

    doc.close()
    return rec


def scan_dir(root, max_pages=None):
    """폴더(학교키/파일.pdf) 전수 계측."""
    out = []
    for dirpath, _dirs, files in os.walk(root):
        for f in sorted(files):
            if not f.lower().endswith(".pdf"):
                continue
            key = _nfc(os.path.basename(dirpath))
            try:
                rec = scan(os.path.join(dirpath, f), max_pages=max_pages)
            except Exception as e:                     # 손상본은 건너뛰되 남긴다
                rec = {"file": _nfc(f), "error": str(e)[:200]}
            rec["school_key"] = key
            out.append(rec)
    return out


if __name__ == "__main__":
    import json
    import sys
    target = sys.argv[1]
    res = scan_dir(target) if os.path.isdir(target) else [scan(target)]
    print(json.dumps(res, ensure_ascii=False, indent=1))
