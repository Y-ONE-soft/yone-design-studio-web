# -*- coding: utf-8 -*-
"""파이널 — **원고 직독**(B6). 워크북 `.indd` 역수확을 대신할 소스.

## 왜

지금 파이널은 이미 조판된 워크북 `.indd` 를 InDesign 으로 열어 단락스타일로
지문을 되수확한다. 거기서 나온 결함이 한 배치에서만 여섯 건이었다 — 인접
문항 오귀속, 지면 라벨 오류 채택, 장문 프레임 분할 소실, 파일 분할 중복.
전부 **조판 결과물의 성질**이지 원고의 성질이 아니다. 되읽기 잔재(하이픈
넣기 `lim-ited`)도 그렇게 생겨 납품본에 인쇄돼 있다.

원고는 그 위층에 있고, **출처가 무엇이든 파일 이름이 같다.**

    <교재 폴더>/… 워크북/Step1 C1 문장배열.docx    (교과서·올포·리딩파워·모의)
    <교재 폴더>/… 워크북/3. 문장배열.docx          (고3 수능특강 — 번호 방언)

## 무엇을 읽나

`Step1 C1 문장배열` = 파이널 ①문장배열 + ②문장삽입(하단 문제)
`Step2 C2 영작배열` = 파이널 ⑤서술형영작
`Step1 C2 빈칸어휘` = 파이널 ③중요어휘(고3만 — 고1·고2 는 구글시트가 정본)

## 라벨

원고는 **스스로 라벨을 말한다**(`1. L4-본문1(p.94)` · `2. p82-no.01`).
지면 순번으로 매기던 것보다 낫다 — 상일1 올포 12강 본문2/3 뒤바뀜이 바로
지면 순번 때문이었다. 방언은 출처마다 다르므로 `parse_label` 이 구조로 읽고,
`to_final_label` 이 시험범위 키(과·강·연월)를 붙여 파이널 라벨로 바꾼다.
"""
import os
import re
import unicodedata

# ── 원고 파일 찾기 ────────────────────────────────────────────────────────
# 이름이 아니라 **낱말**로 찾는다(계열마다 접두가 다르다: "Step1 C1 …" vs "3. …")
KIND_WORDS = {
    "arrange": ("문장배열", "문장 배열"),
    "writing": ("영작배열", "영작 배열"),
    "vocab":   ("빈칸어휘", "빈칸 어휘"),
    "grammar": ("어법선택", "어법 선택"),
}
ANSWER_WORDS = ("정답", "해설")


def _nfc(s):
    return unicodedata.normalize("NFC", s)


def find_manuscript(workbook_dir, kind):
    """워크북 원고 폴더에서 그 종류의 **문제지**를 고른다.

    ⚠ 정답지(`… 정답.docx`)를 집으면 지문이 통째로 답으로 바뀐다 —
      이름에 '정답'·'해설'이 든 것은 뺀다. 확장자는 docx 를 먼저 본다
      (hwp/hwpx 는 같은 내용의 다른 판본으로 함께 놓여 있다).
    """
    if not workbook_dir or not os.path.isdir(workbook_dir):
        return None
    words = KIND_WORDS[kind]
    best = None
    for name in sorted(os.listdir(workbook_dir)):
        n = _nfc(name)
        if n.startswith((".", "~")):
            continue
        if not any(w in n for w in words):
            continue
        if any(a in n for a in ANSWER_WORDS):
            continue
        ext = os.path.splitext(n)[1].lower()
        if ext not in (".docx", ".hwpx", ".hwp"):
            continue
        rank = {".docx": 0, ".hwpx": 1, ".hwp": 2}[ext]
        # 괄호가 붙은 변형본(`…(객관식)`·`…(서술형)`)은 뒤로
        rank += 5 if "(" in n else 0
        if best is None or rank < best[0]:
            best = (rank, os.path.join(workbook_dir, name))
    return best[1] if best else None


def find_workbook_dir(base):
    """교재 폴더 안에서 '워크북' 폴더를 찾는다(이름 방언 흡수)."""
    if not base or not os.path.isdir(base):
        return None
    if any("문장배열" in _nfc(n) or "문장 배열" in _nfc(n)
           for n in os.listdir(base)):
        return base                     # 이미 워크북 폴더다
    for name in sorted(os.listdir(base)):
        p = os.path.join(base, name)
        if os.path.isdir(p) and "워크북" in _nfc(name):
            return p
    return None


# ── docx 표 읽기 ─────────────────────────────────────────────────────────
def _docx_rows(path):
    """표의 첫 칸을 위에서부터 — 원고는 전부 한 열짜리 표다.

    같은 글이 두 칸에 복제된 표(교과서 계열)가 있어 **첫 칸만** 본다.
    """
    from docx import Document
    doc = Document(path)
    out, prev = [], None
    for t in doc.tables:
        for r in t.rows:
            cell = r.cells[0]
            for para in cell.paragraphs:
                s = para.text.strip()
                if s and s != prev:
                    out.append(s)
                    prev = s
    return out


# ── 라벨 ─────────────────────────────────────────────────────────────────
# `1. L4-본문1(p.94)` · `2. p82-no.01` · `7. L4-Read More(p.109)`
RE_ROW = re.compile(r"^\s*(\d{1,3})\s*[.)]\s*(.+?)\s*$")
RE_ITEM = re.compile(r"^\s*\(([A-Z])\)\s*")
RE_PROMPT = re.compile(r"^\s*Q\s*[.:]")


def parse_label(text):
    """원고 라벨 → {"page": "p94", "key": "본문1"} 같은 구조.

    형식이 아니라 자리로 읽는다 — `<쪽 표시>-<지문 이름>` 이고 뒤쪽 괄호는
    쪽 표시의 반복이라 버린다.
    """
    t = re.sub(r"\((?:p\.?\s*\d+[^)]*)\)\s*$", "", text).strip()
    page, _, name = t.partition("-")
    if not name:
        page, name = "", t
    return {"page": page.strip(), "key": name.strip()}


def is_block_head(text):
    """이 줄이 지문 머리인가 — `숫자.` 로 시작하고 항목 표시가 아니다."""
    m = RE_ROW.match(text)
    return bool(m) and not RE_ITEM.match(text)


# ── 문장배열(C1) ─────────────────────────────────────────────────────────
def read_arrange(path):
    """`Step1 C1 문장배열` → [{no, label, items}].

    머리글(교재명·`Q. …` 발문·챕터 표제)은 **첫 지문 머리 앞**에 있는 것으로
    가른다 — 글자로 찾지 않는다.
    """
    rows = _docx_rows(path)
    blocks, cur = [], None
    for s in rows:
        if is_block_head(s):
            m = RE_ROW.match(s)
            cur = {"no": int(m.group(1)), "raw": m.group(2),
                   "label": parse_label(m.group(2)), "items": []}
            blocks.append(cur)
        elif cur is not None:
            if RE_PROMPT.match(s):
                continue                # 다음 묶음의 발문
            cur["items"].append(s)
    return blocks


def read_writing(path):
    """`Step2 C2 영작배열` → [{no, label, pairs:[{korean, choices}]}]."""
    rows = _docx_rows(path)
    blocks, cur, kor = [], None, None
    for s in rows:
        if is_block_head(s):
            m = RE_ROW.match(s)
            cur = {"no": int(m.group(1)), "raw": m.group(2),
                   "label": parse_label(m.group(2)), "pairs": []}
            blocks.append(cur)
            kor = None
        elif cur is not None:
            if RE_PROMPT.match(s):
                continue
            if s.lstrip().startswith("("):      # 보기 상자
                if kor is not None:
                    cur["pairs"].append({"korean": kor, "choices": s})
                    kor = None
            else:
                kor = s
    return blocks


def read_vocab(path):
    """`Step1 C2 빈칸어휘` → [{no, label, lines}] (고3 중요어휘용)."""
    rows = _docx_rows(path)
    blocks, cur = [], None
    for s in rows:
        if is_block_head(s):
            m = RE_ROW.match(s)
            cur = {"no": int(m.group(1)), "raw": m.group(2),
                   "label": parse_label(m.group(2)), "lines": []}
            blocks.append(cur)
        elif cur is not None and not RE_PROMPT.match(s):
            cur["lines"].append(s)
    return blocks


READERS = {"arrange": read_arrange, "writing": read_writing,
           "vocab": read_vocab}


def read(workbook_dir, kind):
    """워크북 원고 폴더 + 종류 → 블록 목록(없으면 빈 목록)."""
    d = find_workbook_dir(workbook_dir)
    p = find_manuscript(d, kind)
    if not p:
        return [], None
    return READERS[kind](p), p
