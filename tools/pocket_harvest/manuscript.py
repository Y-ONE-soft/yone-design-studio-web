# -*- coding: utf-8 -*-
"""플로우노트/동반의어 원고(.hwpx) → 지문 조각.

원고는 **지문 1개 = 표 1개**다(플로우노트DB 실측). 행 구성:

    행0  제목 = 지문 키          `24-9 21번 Flow` · `명일2 4과 본문2`
    행1  흐름(교사용) | 흐름(빈칸본)   ← 빈칸본은 포켓북이 안 쓴다
    행2  주제: … / 주제문: …
    행3  동반의어  ← **새로 추가되는 행. 없으면 없는 대로 둔다.**

형식이 아니라 **구조로** 읽는다([[feedback_parser_structural_not_pattern]]):
행 개수·머리말 글자가 달라도 표 안에서 `주제:`·`동반의어` 같은 **의미 표지**를
찾아 가른다. 표가 아니라 그냥 문단으로 쓴 원고도 받는다(§_parse_flat).

⚠ `=` 를 전역 구분자로 쓰면 안 된다 — 흐름 줄에 `목표 = 오류 방지` 처럼 흔하다.
  **`동반의어` 블록 안에서만** `=`·`↔` 를 읽는다.
"""
import os
import re
import zipfile
import xml.etree.ElementTree as ET

P = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

_SYN_HEAD = re.compile(r"^\s*(동반의어|동의어|유의어\s*[/·]?\s*반의어)\s*$")
_TOPIC = re.compile(r"^\s*주제\s*[:：]\s*(.+)$")
_SUMMARY = re.compile(r"^\s*(주제문|요약문?)\s*[:：]\s*(.+)$")
_BLANKISH = re.compile(r"_{3,}")
_HANGUL = re.compile(r"[가-힣]")


# ── hwpx 읽기 ──────────────────────────────────────────────
def _sections(path):
    with zipfile.ZipFile(path) as z:
        for n in sorted(x for x in z.namelist()
                        if re.match(r"Contents/section\d+\.xml$", x)):
            yield ET.fromstring(z.read(n))


def _para_text(p):
    return "".join(t.text or "" for t in p.iter(P + "t"))


def _cell_lines(tc):
    out = []
    for p in tc.iter(P + "p"):
        out.append(_para_text(p))
    # 문단이 통째로 한 줄로 들어온 원고도 있다 → 눈에 보이는 줄로 쪼갠다
    return [l.strip() for l in out]


# ── 동반의어 한 줄 → 카드 ──────────────────────────────────
def parse_syn_line(line):
    """`expensive 비싼 = costly ↔ cheap, inexpensive` → dict.

    표제어와 뜻은 **첫 한글 자리**로 가른다. `depend on ~ ~에 달려 있다` 처럼
    표제어가 구(句)여도 안전하다 — 구분 기호를 새로 만들지 않기 위해서다.
    """
    s = (line or "").strip()
    if not s:
        return None
    ant = []
    m = re.split(r"\s*↔\s*|\s*<->\s*", s, maxsplit=1)
    if len(m) == 2:
        s, tail = m
        ant = [x.strip() for x in re.split(r"\s*,\s*", tail) if x.strip()]
    syn = []
    m = re.split(r"\s*=\s*", s, maxsplit=1)
    if len(m) == 2:
        s, tail = m
        syn = [x.strip() for x in re.split(r"\s*,\s*", tail) if x.strip()]
    head = s.strip()
    mk = _HANGUL.search(head)
    if mk:
        cut = mk.start()
        # `depend on ~ ~에 달려 있다` — 한글 바로 앞의 물결은 뜻에 딸린 것이다
        while cut > 0 and head[cut - 1] in "~-":
            cut -= 1
        word, ko = head[:cut].strip(), head[cut:].strip()
        # `filter A through B  B를 통해 A를 거르다` — 뜻이 변수 문자로 시작한다.
        # 앞에 이미 나온 홑 대문자면 뜻 쪽이다(표제어에서 떼면 뜻이 깨진다).
        toks = word.split()
        if len(toks) > 1 and len(toks[-1]) == 1 and toks[-1].isupper() \
                and toks[-1] in " ".join(toks[:-1]):
            word, ko = " ".join(toks[:-1]), (toks[-1] + ko)
    else:
        word, ko = head, ""
    if not word:
        return None
    return {"w": word, "ko": ko, "syn": syn, "ant": ant}


# ── 표 하나 → 지문 조각 ────────────────────────────────────
def _from_table(tbl):
    rows = tbl.findall(P + "tr")
    if not rows:
        return None
    cells = [r.findall(P + "tc") for r in rows]
    title = " ".join(_cell_lines(cells[0][0])).strip()
    if not title:
        return None

    flow, topic, summary, syn = [], "", "", []
    for r in cells[1:]:
        lines = _cell_lines(r[0])
        joined = [l for l in lines if l]
        if not joined:
            continue
        # 동반의어 블록인가 — 머리말 또는 `=`/`↔` 가 다수인가
        head_hit = any(_SYN_HEAD.match(l) for l in joined)
        if head_hit:
            started = False
            for l in joined:
                if _SYN_HEAD.match(l):
                    started = True
                    continue
                if started:
                    c = parse_syn_line(l)
                    if c:
                        syn.append(c)
            continue
        # 주제/주제문 블록인가
        if any(_TOPIC.match(l) or _SUMMARY.match(l) for l in joined):
            for l in joined:
                m = _TOPIC.match(l)
                if m:
                    topic = m.group(1).strip()
                    continue
                m = _SUMMARY.match(l)
                if m:
                    summary = m.group(2).strip()
            continue
        # 흐름 블록 — 빈칸본(밑줄 3개 이상이 여러 줄)은 버린다
        blanky = sum(1 for l in joined if _BLANKISH.search(l))
        if blanky >= max(1, len(joined) // 2):
            continue
        if not flow:
            flow = joined
    return {"key_raw": title, "flow": flow, "topic": topic,
            "summary": summary, "synonyms": syn}


def _parse_flat(paras):
    """표가 아니라 문단으로 쓴 원고. 키 줄로 블록을 가른다."""
    blocks, cur = [], None
    for line in paras:
        s = line.strip()
        if not s:
            continue
        if _is_key_line(s):
            if cur:
                blocks.append(cur)
            cur = {"key_raw": s, "lines": []}
        elif cur:
            cur["lines"].append(s)
    if cur:
        blocks.append(cur)
    out = []
    for b in blocks:
        flow, topic, summary, syn, mode = [], "", "", [], "flow"
        for l in b["lines"]:
            if _SYN_HEAD.match(l):
                mode = "syn"
                continue
            m = _TOPIC.match(l)
            if m:
                topic = m.group(1).strip()
                mode = "meta"
                continue
            m = _SUMMARY.match(l)
            if m:
                summary = m.group(2).strip()
                mode = "meta"
                continue
            if mode == "syn":
                c = parse_syn_line(l)
                if c:
                    syn.append(c)
            elif mode == "flow" and not _BLANKISH.search(l):
                flow.append(l)
        out.append({"key_raw": b["key_raw"], "flow": flow, "topic": topic,
                    "summary": summary, "synonyms": syn})
    return out


_KEY_PAT = re.compile(
    r"^\s*(?:\[)?\s*(?:"
    r"\d{2}\s*[-–]\s*\d{1,2}\s*\d{1,2}번"          # 24-9 21번
    r"|\d{6,8}"                                     # 250923
    r"|\d{2}년\s*\d{1,2}월\s*\d{1,2}번"             # 25년 9월 23번
    r"|.{0,20}\d+\s*과\s*본문\s*\d+"                # 명일2 4과 본문2
    r"|외부지문\s*\d+"
    r")\s*(?:\])?\s*(?:Flow)?\s*$", re.I)


def _is_key_line(s):
    return bool(_KEY_PAT.match(s))


def parse(path):
    """원고 .hwpx → [지문 조각]. 표 원고·문단 원고 둘 다 받는다."""
    frags, flat = [], []
    for root in _sections(path):
        tbls = list(root.iter(P + "tbl"))
        for t in tbls:
            f = _from_table(t)
            if f:
                frags.append(f)
        if not tbls:
            for p in root.iter(P + "p"):
                flat.append(_para_text(p))
    if flat:
        frags += _parse_flat(flat)
    return frags


if __name__ == "__main__":
    import json
    import sys
    fr = parse(os.path.expanduser(sys.argv[1]))
    print("지문 %d개" % len(fr))
    for f in fr[:3]:
        print(json.dumps(f, ensure_ascii=False, indent=1)[:900])
