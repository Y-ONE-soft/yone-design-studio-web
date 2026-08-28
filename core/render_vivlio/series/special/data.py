"""특강 합본(special) 원고 인식 — 스타일 이름이 곧 구조다.

이 계열의 원고는 **단락 스타일로 의미가 붙어 있는 docx** 다(`Week제목`·`지문`·
`해설항목`…). 그래서 다른 계열처럼 정규식으로 형태를 더듬을 필요가 없고, 오히려
정규식을 쓰면 원고가 조금만 달라져도 깨진다. 여기서는 **스타일 이름을 유일한
구조 신호로 쓰고, 모르는 스타일이 나오면 조용히 버리지 않고 게이트로 세운다.**

산출 data.json 은 **문서 순서 그대로의 블록 스트림**이다. 트리로 깊게 묶지 않는
이유는 이 책이 "묶음 안의 묶음"이 아니라 흐름이기 때문이다 — 묶기가 필요한 곳
(낱말 카드 · 예제 한 벌 · 문항 한 벌)만 렌더러가 `unit` 으로 감싼다.

    {
      "cover":   {...},                      합본 표지
      "blocks":  [ {"t": 종류, ...}, ... ]   문서 순서
    }

인라인 서식은 다른 계열과 같은 rich 세그먼트다: 문자열 또는
`{"t": 글자, "b": 굵게, "u": 밑줄, "k": 종류}`. `k` 는 원고가 **색으로** 표시한
의미(문항 번호 · 출처 · 정답 · 품사)를 색이 아니라 이름으로 옮긴 것이다.
"""
import json
import os
import re

# ── 원고가 색으로 구별한 것 → 의미 이름 ────────────────────────────────
#    색 값 자체는 원고의 사정이고 조판 색은 테마가 정한다. 여기서 이름으로
#    바꿔 두지 않으면 원고 색이 바뀔 때마다 렌더러를 고쳐야 한다.
ROLE_BY_COLOR = {
    "1F3364": "num",      # 문항 번호 · 해설 정답
    "666666": "src",      # 해설 출처 [2020 11월 고1 40번]
    "0096AF": "src",      # 발문 출처 [ 2024년 9월 고1 모의고사 23번 ]
    "FFFFFF": "src",      # 낱말 예문 출처 — 원고에서 흰 글자로 숨어 있다
    "7F6000": "pos",      # 다품사 예문의 (n) (v)
}

# ── 스타일 → 블록 종류 ─────────────────────────────────────────────────
#    값이 None 인 것은 "내용 없는 자리 표시"라 버린다(빈 단락 · 쪽 나눔용).
SIMPLE = {
    # 합본 표지
    "합본표지부제": "cover_sub",
    "합본표지제목": "cover_title",
    "합본표지안내": "cover_note",
    # 부(部) 간지 · 목차
    "간지대제목": "vol_title",
    "간지설명": "vol_desc",
    "합본목차제목": "toc_title",
    "합본목차대": "toc_1",
    "합본목차소": "toc_2",
    # 어휘부
    "Week제목": "week",
    "분류띠": "group",
    "부록": "appendix",
    # 구문·어법부
    "PART표지번호": "part_no",
    "PART표지제목": "part_title",
    "강제목": "lesson",
    "강설명": "lesson_sub",
    "소제목": "subhead",
    "불릿": "bullet",
    "개념문단": "concept",
    "연습제목": "drill",
    "연습지시": "drill_note",
    "문제": "q",
    "POINT": "q_point",
    "기입선": "q_field",
    # 구문·어법 해설
    "해설강제목": "ans_head",
    "해설구분": "ans_kind",
    "해설문항": "ans_q",
    "해설영문": "ans_en",
    "해설항목": "ans_item",
    # 독해부
    "간지Part": "rpart_no",
    "간지제목": "rpart_title",
    "DH_Week제목": "week",
    "DH_강제목": "lesson",
    "개념헤더": "concept_head",
    "블록제목": "block_head",
    "블록불릿": "block_bullet",
    "필기헤더": "wnote_head",
    "예제헤더": "ex_head",
    "예제태그": "ex_tag",
    "발문": "stem",
    "지문": "passage",
    "지문압축": "passage",
    "각주": "footnote",
    "선택지": "choice",
    "선택지압축": "choice",
    "노트헤더": "note_head",
    "해석헤더": "trans_head",
    "해석본문": "trans",
    "해석본문소": "trans",
    "해석본문초소": "trans",
    "해석본문극소": "trans",
    "배경헤더": "bg_head",
    "배경항목": "bg_item",
    "정답항목": "ans_line",
}

# 내용 없는 자리 표시(쪽 나눔·간격)
DROP = {"DH_Normal", "GG_Normal", "Normal", "No Spacing"}

# 낱말 카드 셀 안의 스타일
WORD_CELL = {
    "번호": "no", "단어": "head", "짜임": "build", "뜻": "sense",
    "예문": "ex", "노트라벨": "note", "빈칸": None,
}

RE_WS = re.compile(r"[ \t ]+")


# ── docx 원자 ───────────────────────────────────────────────────────────
def _color(run):
    c = run.font.color
    if c is None or c.type is None or c.rgb is None:
        return ""
    return str(c.rgb).upper()


def _runs(para):
    """단락 → rich 세그먼트 목록. 같은 서식이 이어지면 붙인다."""
    out = []
    for r in para.runs:
        t = r.text
        if not t:
            continue
        t = t.replace("\t", "	")
        seg = {"t": t}
        if r.bold:
            seg["b"] = 1
        if r.underline:
            seg["u"] = 1
        role = ROLE_BY_COLOR.get(_color(r))
        if role:
            seg["k"] = role
        if out and _same(out[-1], seg):
            out[-1]["t"] += t
        else:
            out.append(seg)
    # 서식 없는 조각은 문자열로 (data.json 이 읽기 쉬워진다)
    return [s["t"] if set(s) == {"t"} else s for s in out]


def _same(a, b):
    return all(a.get(k) == b.get(k) for k in ("b", "u", "k"))


def plain(rich):
    if rich is None:
        return ""
    if isinstance(rich, str):
        return rich
    if isinstance(rich, dict):
        return rich.get("t", "")
    return "".join(plain(x) for x in rich)


def _blank(rich):
    return not plain(rich).strip()


def _style(p):
    return (p.style.name if p.style is not None else "") or ""


# ── 표(낱말 카드 · 필기 상자) ──────────────────────────────────────────
def _word_card(tbl, log, bad):
    """1×2 표 = 낱말 카드. 왼쪽 = 표제어, 오른쪽 = 예문."""
    cells = tbl.rows[0].cells
    card = {"t": "word", "no": "", "head": "", "build": "",
            "senses": [], "ex": [], "note": ""}
    for cell in cells:
        for p in cell.paragraphs:
            st = _style(p)
            if st in DROP:
                continue
            kind = WORD_CELL.get(st, "?")
            if kind == "?":
                bad.append(f"낱말 카드 안의 모르는 스타일: {st}")
                continue
            if kind is None:
                continue
            rich = _runs(p)
            if _blank(rich):
                continue
            if kind == "sense":
                card["senses"].append(rich)
            elif kind == "ex":
                card["ex"].append(rich)
            elif kind == "note":
                card["note"] = plain(rich)
            else:
                card[kind] = plain(rich)
    return card


def _note_box(tbl):
    """1×1 빈 표 = 필기 상자. 원고에 내용이 있으면 그대로 담는다."""
    txt = "\n".join(p.text for p in tbl.rows[0].cells[0].paragraphs).strip()
    return {"t": "notebox", "text": txt}


# ── 본체 ────────────────────────────────────────────────────────────────
def parse(path, log=print):
    import docx
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = docx.Document(path)
    blocks, bad = [], []
    seen_styles = set()

    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            p = Paragraph(child, doc)
            st = _style(p)
            seen_styles.add(st)
            if st in DROP:
                continue
            kind = SIMPLE.get(st)
            if kind is None:
                bad.append(f"모르는 단락 스타일: {st!r} — {p.text[:40]!r}")
                continue
            rich = _runs(p)
            if _blank(rich):
                continue
            blocks.append({"t": kind, "r": rich})
        elif child.tag == qn("w:tbl"):
            tbl = Table(child, doc)
            ncell = len(tbl.rows[0].cells) if tbl.rows else 0
            if len(tbl.rows) == 1 and ncell == 2:
                blocks.append(_word_card(tbl, log, bad))
            elif len(tbl.rows) == 1 and ncell == 1:
                blocks.append(_note_box(tbl))
            else:
                bad.append(f"모르는 표: {len(tbl.rows)}×{ncell}")

    return blocks, bad, seen_styles


# ── 부(部) 나누기 ───────────────────────────────────────────────────────
#    `vol_title`(간지 대제목)이 부의 시작이다. 앞머리(합본 표지)는 부 밖.
VOL_ID = {"어휘": "vocab", "구문 · 어법": "grammar", "독해": "reading"}


def _split(blocks):
    cover, vols = [], []
    for b in blocks:
        if b["t"] == "vol_title":
            name = plain(b["r"]).strip()
            vols.append({"name": name,
                         "id": VOL_ID.get(name, f"v{len(vols) + 1}"),
                         "blocks": []})
        elif vols:
            vols[-1]["blocks"].append(b)
        else:
            cover.append(b)
    return cover, vols


# ── 인식 게이트 ─────────────────────────────────────────────────────────
def _gate(data, bad, log):
    """원고가 통째로 어긋났는지 — 조판 전에 세운다.

    세는 것은 '있어야 하는 것의 개수'다. 원고 형식이 바뀌면 여기서 먼저 걸린다.
    """
    fails = list(bad)
    vols = data["volumes"]
    if len(vols) != 3:
        fails.append(f"부(部)가 3개가 아니다: {[v['name'] for v in vols]}")
    counts = {}
    for v in vols:
        c = {}
        for b in v["blocks"]:
            c[b["t"]] = c.get(b["t"], 0) + 1
        counts[v["id"]] = c
    v = counts.get("vocab", {})
    if v.get("word", 0) != 80:
        fails.append(f"어휘 낱말 카드 {v.get('word', 0)}개 (80이어야 한다)")
    if v.get("week", 0) != 9:
        fails.append(f"어휘 Week {v.get('week', 0)}개 (8주 + 부록 = 9)")
    g = counts.get("grammar", {})
    if g.get("q", 0) != 160:
        fails.append(f"구문·어법 문항 {g.get('q', 0)}개 (160이어야 한다)")
    if g.get("lesson", 0) != 10:
        fails.append(f"구문·어법 강 {g.get('lesson', 0)}개 (10이어야 한다)")
    if g.get("ans_q", 0) != 160:
        fails.append(f"구문·어법 해설 {g.get('ans_q', 0)}개 (160이어야 한다)")
    r = counts.get("reading", {})
    if r.get("stem", 0) != 34:
        fails.append(f"독해 예제 {r.get('stem', 0)}개 (34이어야 한다)")
    # 지문은 예제보다 많을 수 있다 — 순서배열·문장삽입은 주어진 글과 (A)(B)(C)가
    # 각각 한 단락이라 한 예제가 여러 지문 단락을 갖는다. 적으면 유실이다.
    if r.get("passage", 0) < r.get("stem", 0):
        fails.append(f"독해 지문 {r.get('passage', 0)} < 예제 {r.get('stem', 0)}")
    if r.get("trans", 0) != r.get("stem", 0):
        fails.append(f"독해 발문 {r.get('stem', 0)} ≠ 해석 {r.get('trans', 0)}")
    for vid, c in counts.items():
        log(f"  {vid}: " + " · ".join(f"{k} {n}" for k, n in sorted(c.items())))
    return fails


def build(cfg, log=print):
    src = cfg.manuscript("body")
    blocks, bad, styles = parse(src, log)
    cover, vols = _split(blocks)
    data = {"book": cfg.book, "cover": cover, "volumes": vols}
    log(f"■ 원고 {os.path.basename(src)} · 블록 {len(blocks):,}개 · "
        f"스타일 {len(styles)}종")
    fails = _gate(data, bad, log)
    if fails:
        raise ValueError("원고 인식 실패:\n  - " + "\n  - ".join(fails[:20]))
    out = cfg.path("data.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    log(f"OK  → {out}")
    return data


def load(cfg):
    with open(cfg.path("data.json"), encoding="utf-8") as f:
        return json.load(f)
