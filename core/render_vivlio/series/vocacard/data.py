"""이의고2 단어장 원고 → data.json.

입력(책 config 의 `manuscript.files.words`): xlsx 단일 시트 '단어장 원고'.
열 순서(원고 그대로) — 번호/구간/표제어/품사/뜻/예문/해석/연관어휘 · 유반의어/
파생어/주의 · 혼동/영영풀이.

`vocabook`(상일보카)과 달리 Day 가 없다. '구간' 열이 곧 그룹핑 단서다:
  "교과서 - 본문 3"                         → part=text, group="본문 3"
  "부교재 - 8강 Exercise 03 [순서 추론]"      → part=supp, group="8강 Exercise 03 [순서 추론]"
  "2026년 9월 고2 모의고사 - 21번 [함축적 의미]" → part=mock, group="21번 [함축적 의미]"

인식은 접두어 구조로만 판정한다(리터럴 전체 문자열에 기대지 않음) — '부교재'
쪽 수능특강 강·회차가 바뀌어도, 모의고사 회차가 바뀌어도 그대로 통한다.

**인식 게이트**: 기대 수량과 어긋나면 조판하지 않고 중단한다(침묵 유실 금지).
기대값은 책 config 의 `options.expect`.
"""
import json
import os
import re

import openpyxl

_RE_NOTE_LABEL = re.compile(r"^(주의|혼동)\.\s*")

SHEET = "단어장 원고"
# 워드 원고의 라벨 줄 — 이 줄 자체는 내용이 아니라 **다음 줄들의 이름표**다.
DOC_LABELS = {"예문": "예문", "연관어휘 / 유반의어": "유반의어", "파생어": "파생어",
              "주의 / 혼동": "주의", "영영풀이": "영영풀이"}
_RE_DOC_HEAD = re.compile(r"^(\d{4})\s+(.+)$")
_RE_DOC_POS = re.compile(r"^(.*?)\s((?:n|v|a|ad|prep|conj|pron)\.)\s*(.*)$")
_RE_DOC_KO = re.compile(r"[~〜]?[가-힣]")
PART_TITLE = {"text": "교과서", "supp": "부교재", "mock": "모의고사"}
PART_ORDER = ("text", "supp", "mock")


def _t(v):
    return "" if v is None else str(v).strip()


def _lines(v):
    return [ln.strip() for ln in _t(v).split("\n") if ln.strip()]


# 구간 이름 → (파트, 소제목). **책마다 다르다** — config `options.parts_match` 로
# 덮는다. 아래는 이의고2 판(`교과서 - 본문 3`).
#   이의고1 은 부교재에 '부교재' 라는 말이 아예 없다(`수능특강 Light 영어 12강
#   Exercise 01`) — 기본 규칙만 믿었다가 부교재 256낱말이 통째로 앞 구간에
#   흡수됐다. 접두어는 구조가 아니라 **책이 정하는 값**이라 config 에 둔다.
DEFAULT_PARTS = (
    ("text", r"^교과서\s*-\s*(.+)$"),
    ("supp", r"^부교재\s*-\s*(.+)$"),
    ("mock", r"^.*모의고사\s*-\s*(.+)$"),
)
_classifier = None            # build() 가 config 로 채운다


def make_classifier(rules=None):
    """[(파트, 정규식)] → 판정 함수. 정규식의 첫 괄호가 소제목, 없으면 줄 전체."""
    pats = [(p, re.compile(rx)) for p, rx in (rules or DEFAULT_PARTS)]

    def classify(raw):
        raw = _t(raw)
        for part, rx in pats:
            m = rx.match(raw)
            if m:
                sub = (m.group(1) if m.groups() else "") or raw
                return part, sub.strip()
        return "etc", raw
    return classify


def classify(raw):
    return (_classifier or make_classifier())(raw)


def split_head(rest):
    """`recession n. 경기 침체, 불황` → (표제어, 품사, 뜻).

    품사가 없는 낱말(`show off 뽐내다`)은 **첫 한글**에서 가른다. 한글 앞에 붙은
    물결표(`~의 줄임말인`)는 뜻 쪽이다 — 표제어에 딸려 가면 `short for ~` 가 된다.
    """
    m = _RE_DOC_POS.match(rest)
    if m:
        return m.group(1).strip(), m.group(2), m.group(3).strip()
    k = _RE_DOC_KO.search(rest)
    if k:
        return rest[:k.start()].strip(), "", rest[k.start():].strip()
    return rest.strip(), "", ""


def parse_docx(path):
    """워드 원고 → 낱말 목록. 엑셀 파서와 **같은 모양**을 돌려준다.

    엑셀본에는 원고를 만들며 남긴 작업 메모(`유. 3개 확보 불가 — 사유: …`)가
    유의어 칸에 섞여 있어 그대로 조판하면 책에 실린다(실측: 65면). 워드본은
    학생이 볼 것만 담긴 정본이라 이쪽을 쓴다.

    구조로 읽는다 — 구간 줄은 `classify()` 가 알아보는 줄(교과서/부교재/모의고사 -
    …), 낱말 머리는 네 자리 번호로 시작하는 줄, 그 사이 라벨 줄이 뒤따르는
    줄들의 이름표다.
    """
    import docx
    items, cur, group, lab = [], None, "", None
    for para in docx.Document(path).paragraphs:
        t = para.text.strip()
        if not t:
            continue
        m = _RE_DOC_HEAD.match(t)
        if m:
            word, pos, mean = split_head(m.group(2))
            cur = {"no": int(m.group(1)), "part": "", "group": group,
                   "word": word, "pos": pos, "meaning": mean, "rows": [],
                   "_buf": {}}
            items.append(cur)
            lab = None
            continue
        if classify(t)[0] != "etc":          # 구간 줄
            group, lab, cur = t, None, None
            continue
        if t in DOC_LABELS:
            lab = DOC_LABELS[t]
            continue
        if cur is not None and lab:
            cur["_buf"].setdefault(lab, []).append(t)

    for it in items:
        it["part"] = classify(it["group"])[0]
        it["group"] = classify(it["group"])[1]
        buf = it.pop("_buf")
        rows = []
        if buf.get("예문"):
            rows.append({"label": "예문", "lines": buf["예문"][:2]})
        if buf.get("유반의어"):
            rows.append({"label": "유반의어", "lines": buf["유반의어"]})
        der = [x for x in buf.get("파생어", []) if x != "없음"]
        if der:
            rows.append({"label": "파생어", "lines": der})
        if buf.get("주의"):
            lines = buf["주의"]
            lab2 = "혼동" if lines and lines[0].startswith("혼동") else "주의"
            rows.append({"label": lab2,
                         "lines": [_RE_NOTE_LABEL.sub("", x) for x in lines]})
        if buf.get("영영풀이"):
            rows.append({"label": "영영풀이", "lines": buf["영영풀이"]})
        it["rows"] = rows
    return items


def parse(path):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[SHEET]
    items = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if not r or not _t(r[0]):
            continue
        (no, raw_sec, word, pos, mean, ex_en, ex_kr,
         syn, deriv, note, defn) = (list(r) + [None] * 11)[:11]
        part, group = classify(raw_sec)
        rows = []
        if _t(ex_en):
            rows.append({"label": "예문", "lines": [_t(ex_en), _t(ex_kr)]})
        if _t(syn):
            rows.append({"label": "유반의어", "lines": _lines(syn)})
        if _t(deriv) and _t(deriv) != "없음":
            rows.append({"label": "파생어", "lines": _lines(deriv)})
        if _t(note):
            note_lines = _lines(note)
            # 원고 줄 자체가 '주의.'/'혼동.' 로 시작 — 그 접두어를 행 라벨로
            # 쓰고(둘을 구분해 보이게) 줄 안에서는 중복이라 지운다.
            lab = "혼동" if note_lines and note_lines[0].startswith("혼동") else "주의"
            note_lines = [_RE_NOTE_LABEL.sub("", ln) for ln in note_lines]
            rows.append({"label": lab, "lines": note_lines})
        if _t(defn):
            rows.append({"label": "영영풀이", "lines": [_t(defn)]})
        items.append({
            "no": int(no) if isinstance(no, (int, float)) else len(items) + 1,
            "part": part, "group": group,
            "word": _t(word), "pos": _t(pos), "meaning": _t(mean),
            "rows": rows,
        })
    return items


def gate(items, expect):
    errs = []
    n = len(items)
    if expect.get("words") is not None and n != expect["words"]:
        errs.append(f"낱말 {n} (기대 {expect['words']})")
    counts = {}
    for it in items:
        counts[it["part"]] = counts.get(it["part"], 0) + 1
    if counts.get("etc"):
        errs.append(f"구간 미분류 {counts['etc']}건 — data.py classify() 확인")
    for k, want in (expect.get("parts") or {}).items():
        got = counts.get(k, 0)
        if got != want:
            errs.append(f"{PART_TITLE.get(k, k)} {got} (기대 {want})")
    if errs:
        raise SystemExit("[오류] 원고 인식 불일치:\n  - " + "\n  - ".join(errs))
    return counts


def build(cfg, log=print):
    global _classifier
    opts = cfg.section("options") or {}
    _classifier = make_classifier(opts.get("parts_match"))
    src = cfg.manuscript("words")
    items = (parse_docx if src.lower().endswith(".docx") else parse)(src)
    counts = gate(items, opts.get("expect") or {})

    out = cfg.path("data.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"items": items}, f, ensure_ascii=False)
    summary = " · ".join(f"{PART_TITLE.get(k, k)} {counts.get(k, 0)}"
                         for k in PART_ORDER if counts.get(k))
    log(f"OK  낱말 {len(items)} · {summary} "
        f"({os.path.basename(src)}) → {os.path.basename(out)}")
    return out


def load(cfg, log=None):
    """data.json + 정오표(errata.json) — 읽는 자리에서 얹는다."""
    from core.render_vivlio import errata
    return errata.load_data(cfg, log)
