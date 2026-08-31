# -*- coding: utf-8 -*-
"""정본 역할별 실측 — 텍스트층 있는 기출 PDF 에서 단락 역할마다 수치를 뽑는다.

`refscan` 이 '무슨 표기를 쓰는가'(방언)를 본다면, 여기는 '얼마나 큰가/어디서
시작하는가'(수치)를 본다. 역할 판정은 줄 머리 표기로 한다 — 학교마다 표기가
다르므로 판정 규칙 자체를 프로파일에서 받는다(기본값은 다수 학교 공통형).

**판형 정규화**: 학교 기출은 A4/B4 로 제각각인데 우리 제품은 B4(257×364) 고정이다.
그래서 모든 수치를 (a) 정본 그대로 (b) B4 로 환산한 값 두 벌로 낸다. 환산 계수는
정본 지면 폭 대비 제품 지면 폭이다 — 지면이 커지면 글자도 같은 비율로 커져야
'같은 밀도'가 된다.
"""
import collections
import re

try:
    import fitz
except ImportError:
    fitz = None

MM = 25.4 / 72.0
PRODUCT_W_MM = 257.0          # B4 제품 폭 (도련본 263 은 도련 3mm 씩 포함)

DEFAULT_RULES = [
    ("group",  re.compile(r"^\s*(?:【|\[\s*\d+\s*[~\-–]|〔)")),
    ("essay",  re.compile(r"^\s*(?:\[\s*서[답술]형|〔\s*서[답술]형|서[답술]형\s*\d)")),
    ("stem",   re.compile(r"^\s*\d{1,2}\s*[.)]\s*\S")),
    ("choice", re.compile(r"^\s*[①-⑮➀-➉]")),
    ("given",  re.compile(r"^\s*(?:<\s*보\s*기\s*>|〈보기〉|\[\s*보기\s*\]|<\s*요약문?\s*>|<\s*Keywords?\s*>)")),
    ("cond",   re.compile(r"^\s*(?:<\s*조\s*건\s*>|〈조건〉|\[\s*조건\s*\]|\|\s*조\s*건\s*\|)")),
    ("answer", re.compile(r"^\s*(?:답\s*[:：]|\[\s*답\s*\]|→\s*\(?\s*고친)")),
]


def _lines(doc, pages=None):
    out = []
    rng = range(doc.page_count) if pages is None else pages
    for i in rng:
        for b in doc[i].get_text("dict")["blocks"]:
            if b.get("type") != 0:
                continue
            for l in b["lines"]:
                txt = "".join(s["text"] for s in l["spans"])
                if not txt.strip():
                    continue
                sp = max(l["spans"], key=lambda s: len(s["text"]))
                head = l["spans"][0]
                out.append({"pg": i + 1, "y": l["bbox"][1], "x0": l["bbox"][0],
                            "x1": l["bbox"][2], "t": txt,
                            "font": sp["font"], "size": round(sp["size"], 2),
                            "head_font": head["font"],
                            "head_size": round(head["size"], 2),
                            "head_t": head["text"][:12],
                            "bold": bool(sp.get("flags", 0) & 2 ** 4)})
    return out


def _classify(t, rules):
    for name, pat in rules:
        if pat.search(t):
            return name
    return "body"


def _column_origins(lines, page_w):
    """단 왼쪽 x 좌표들. 줄 x0 최빈값을 왼쪽부터 훑어 단 원점을 잡는다."""
    c = collections.Counter(round(l["x0"], 1) for l in lines)
    strong = [x for x, n in c.items() if n >= max(6, len(lines) * 0.02)]
    strong.sort()
    origins = []
    for x in strong:
        if not origins or x - origins[-1] > page_w * 0.15:
            origins.append(x)
    return origins


def measure(pdf_path, rules=None, skip_first_page=False):
    """텍스트층 PDF → 역할별 수치 dict (정본 단위 + B4 환산)."""
    if fitz is None:
        raise RuntimeError("PyMuPDF(fitz) 필요")
    rules = rules or DEFAULT_RULES
    doc = fitz.open(pdf_path)
    page_w = doc[0].rect.width
    page_h = doc[0].rect.height
    pages = range(1, doc.page_count) if (skip_first_page and doc.page_count > 1) \
        else range(doc.page_count)
    lines = _lines(doc, pages)
    if not lines:
        doc.close()
        return {"error": "텍스트층 없음"}

    origins = _column_origins(lines, page_w)
    ncol = len(origins) if origins else 1

    def col_of(x):
        best, bi = None, 0
        for i, o in enumerate(origins):
            if x >= o - 6 and (best is None or o > best):
                best, bi = o, i
        return bi, (origins[bi] if origins else 0)

    by = collections.defaultdict(list)
    for l in lines:
        by[_classify(l["t"], rules)].append(l)

    scale = PRODUCT_W_MM / (page_w * MM)      # 정본 → B4 환산 계수

    def role_stat(rows):
        if not rows:
            return None
        sizes = collections.Counter(r["size"] for r in rows)
        fonts = collections.Counter(r["font"] for r in rows)
        indents = collections.Counter()
        for r in rows:
            _i, o = col_of(r["x0"])
            indents[round((r["x0"] - o) * MM, 1)] += 1
        size = sizes.most_common(1)[0][0]
        heads = collections.Counter((r["head_font"], r["head_size"]) for r in rows)
        (hf, hs), _hn = heads.most_common(1)[0]
        return {
            "n": len(rows),
            "font": fonts.most_common(1)[0][0],
            "fonts": dict(fonts.most_common(3)),
            "size_pt": size,
            "size_pt_b4": round(size * scale, 2),
            "marker_font": hf,
            "marker_size_pt": hs,
            "marker_size_pt_b4": round(hs * scale, 2),
            "marker_differs": hs != size or hf != fonts.most_common(1)[0][0],
            "indent_mm": [x for x, _ in indents.most_common(3)],
            "indent_mm_b4": [round(x * scale, 2) for x, _ in indents.most_common(3)],
            "bold_ratio": round(sum(1 for r in rows if r["bold"]) / len(rows), 2),
            "samples": [r["t"][:80] for r in rows[:3]],
        }

    # 줄 간격: 단 안에서 '읽는 순서'로 늘어놓고, 역할 줄의
    #   leading      = 그 줄 → 바로 다음 줄 (문단 안 행간)
    #   space_before = 바로 앞 줄 → 그 줄 (문단 앞 여백)
    ordered = sorted(lines, key=lambda r: (r["pg"], col_of(r["x0"])[0], r["y"]))
    lead = collections.defaultdict(collections.Counter)
    before = collections.defaultdict(collections.Counter)
    for a, b in zip(ordered, ordered[1:]):
        if a["pg"] != b["pg"] or col_of(a["x0"])[0] != col_of(b["x0"])[0]:
            continue
        g = round(b["y"] - a["y"], 1)
        if not (2 < g < 60):
            continue
        lead[_classify(a["t"], rules)][g] += 1
        before[_classify(b["t"], rules)][g] += 1
    leading = {}
    for role in set(list(lead) + list(before)):
        e = {}
        if lead.get(role):
            g, n = lead[role].most_common(1)[0]
            e["leading_pt"] = g
            e["leading_pt_b4"] = round(g * scale, 2)
            e["leading_n"] = n
        if before.get(role):
            g, n = before[role].most_common(1)[0]
            e["space_before_pt"] = g
            e["space_before_pt_b4"] = round(g * scale, 2)
            e["space_before_n"] = n
        leading[role] = e

    xs_all = [l["x0"] for l in lines]
    x1_all = [l["x1"] for l in lines]
    res = {
        "file": pdf_path,
        "sheet_mm": [round(page_w * MM, 1), round(page_h * MM, 1)],
        "scale_to_b4": round(scale, 4),
        "columns": ncol,
        "column_origins_mm": [round(o * MM, 1) for o in origins],
        "column_width_mm": (round((origins[1] - origins[0]) * MM, 1)
                            if ncol >= 2 else None),
        "text_left_mm": round(min(xs_all) * MM, 1),
        "text_right_mm": round(max(x1_all) * MM, 1),
        "text_top_mm": round(min(l["y"] for l in lines) * MM, 1),
        "text_bottom_mm": round(max(l["y"] for l in lines) * MM, 1),
        "roles": {k: role_stat(v) for k, v in sorted(by.items())},
        "leading": leading,
    }
    doc.close()
    return res


if __name__ == "__main__":
    import json
    import sys
    print(json.dumps(measure(sys.argv[1]), ensure_ascii=False, indent=1))
