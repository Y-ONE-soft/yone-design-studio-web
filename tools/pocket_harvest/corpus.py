# -*- coding: utf-8 -*-
"""완성 포켓북 IDML 무더기 → **지문 DB(코퍼스)**.

    python3 corpus.py build [--limit N] [--only 광문]
    python3 corpus.py report          # 이미 만든 코퍼스로 리포트만 다시

출력  ~/Documents/작업/Y.ONE STUDIO/조판/교재/포켓북/_corpus/
        <키>.json      지문 하나
        _index.json    키 → 요약 + 이번 수확 메타
        _empty.md      **동반의어 0개 · 플로우노트 0개** 목록(사람이 채울 자리)
        _unkeyed.md    키를 못 만든 지문(조용히 버리지 않는다)
        _conflicts.md  같은 키인데 지문 원문이 다른 것 = 진짜 키 충돌

전환계획 §3-C·§5 의 P2 단계다. 여기서 만든 JSON 이 앞으로 "완성본에서 가져오기"를
대신한다.

── 이 파일이 붙잡고 있는 세 가지 ────────────────────────────────────────

1. **지문 키.** `idml.read_book()` 이 주는 `pno`·`label` 은 그대로는 못 쓴다.
   지면 장식(`TRANSLATION`·`요약문`·`PICTURE`)이 라벨 자리로 새어 들어오고,
   지문번호가 문단 스타일 `암기테스트` 로도 `본문` 으로도 조판돼 있어
   **스타일로는 못 가른다**(명일2 실측). 그래서 **한 책 안에서 같은 자리에
   반복해 나타나는 짧은 프레임**(좌표 슬롯)으로 판정한다 → `_cluster`.

2. **병합.** 같은 지문이 여러 책에 있다. 파일명으로 고르면 틀린다 —
   `광문1_포켓북_내지.idml` 은 35지문 전부 동반의어가 비었고
   `광문1_포켓북_내지(동반의어_완).idml` 은 50지문 전부 차 있다.
   **필드마다 더 풍부한 쪽**을 남기고 `provenance` 를 붙인다.

3. **0개 리포트.** 칸이 3개든 6개든 하나라도 있으면 정상이다. **0개만 결함이다.**
   단 짤지문(한 스프레드에 지문 2개)은 오른쪽 면 자체가 없으므로 따로 센다.
"""
import argparse
import collections
import difflib
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
import xml.etree.ElementTree as ET
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import idml  # noqa: E402

IDML_ROOT = os.path.expanduser(
    "~/Documents/작업/Y.ONE STUDIO/조판/교재/포켓북/_idml/pocketbook")
OUT = os.path.expanduser(
    "~/Documents/작업/Y.ONE STUDIO/조판/교재/포켓북/_corpus")

# 포켓북 판형 A5 148×210mm. **파일명이 아니라 판형으로 가른다** — 같은 폴더에
# 분석본(210×297)이 섞여 있고, 파일명 표기는 학기마다 바뀐다.
TRIM_MM = (148.0, 210.0)
TRIM_TOL = 6.0

# 사람이 손댄 필드는 재수확이 덮지 않는다(전환계획 §5 provenance).
MANUAL_FROM = {"manual", "web", "hwpx"}

_DIGIT = re.compile(r"\d")
_WS = re.compile(r"\s+")


def nfc(s):
    return unicodedata.normalize("NFC", s or "")


# ══════════════════════════════════════════════════════════════════════
# 1. 지문 키
# ══════════════════════════════════════════════════════════════════════
# 규칙은 engines/pocketbook/jsx/run.jsx 의 expandPassageNo 를 그대로 승계한다.
#   · `230341~42` `230341-42` → 230341, 230342   (뒤 숫자가 짧으면 앞을 이어붙임)
#   · `23034142`(8자리 연번)  → 230341, 230342   (앞6 / 앞4+뒤2)
# run.jsx 는 "여러 후보로 찾아보기"였지만 DB 는 **대표 키 하나**가 필요하다.
# 그래서 범위는 언제나 `시작-끝`(양쪽 다 완전한 자릿수)로 편다 —
# `230341~42` 와 `23034142` 와 `230341-230342` 가 한 키로 모인다.
_RANGE = re.compile(r"^(\d{4,6})\s*[~\-–—]\s*(\d{1,6})$")
_PLAIN = re.compile(r"^\d{4,8}$")


def expand_pno(raw):
    """지문번호 표기 → (대표키, [번호…], [별칭…]). 못 읽으면 (None, [], [])."""
    s = _WS.sub("", nfc(raw or ""))
    if not s:
        return None, [], []

    def pack(start, end):
        if end == start:
            return str(start), [str(start)]
        return "%d-%d" % (start, end), [str(n) for n in range(start, end + 1)]

    m = _RANGE.match(s)
    if m:
        pre, suf = m.group(1), m.group(2)
        if len(suf) < len(pre):
            suf = pre[:len(pre) - len(suf)] + suf
        a, b = int(pre), int(suf)
        if b >= a and b - a < 20:
            key, nums = pack(a, b)
        else:
            key, nums = pre, [pre, suf]
        return key, nums, _aliases(key, nums, s)

    if _PLAIN.match(s):
        if len(s) == 8:
            a = int(s[:6])
            b = int(s[:4] + s[6:8])
            if b > a and b - a < 20:
                key, nums = pack(a, b)
                return key, nums, _aliases(key, nums, s)
            return s, [s], _aliases(s, [s], s)
        return s, [s], _aliases(s, [s], s)
    return None, [], []


def _aliases(key, nums, raw):
    """같은 지문을 가리키는 다른 표기들. 나중 조회가 어느 표기로 와도 맞게."""
    al = {key, raw}
    al.update(nums)
    if len(nums) > 1:
        a, b = nums[0], nums[-1]
        al.add("%s~%s" % (a, b[len(b) - 2:]))       # 230341~42
        al.add("%s-%s" % (a, b[len(b) - 2:]))
        al.add(a + b[len(b) - 2:])                   # 23034142
    return sorted(x for x in al if x)


def grade_of(school):
    """학교 폴더 → 학년. `강동1`·`명일2` 처럼 **끝 숫자가 학년**이다.

    ⚠ 이걸 빼면 조용히 틀린다. `250921`(25년 9월 21번)은 고1과 고2가 **다른 지문**인데
      지문번호 표기에는 학년이 없다 — 실측에서 43건이 겹쳤다. run.jsx 는 한 학교
      안에서만 조회하니 드러나지 않던 구멍이다.
    """
    m = re.search(r"(\d)\s*$", nfc(school or ""))
    return "고%s" % m.group(1) if m else ""


def norm_label(s):
    """라벨 → 키 조각. 공백·구두점만 정리한다(뜻은 건드리지 않는다)."""
    s = nfc(s or "").strip()
    s = re.sub(r"^[\[\(<【]|[\]\)>】]$", "", s).strip()
    s = _WS.sub("-", s)
    return re.sub(r"[/:\\]+", "-", s)


def term_scope(term):
    """`25-2-기말` → `25-2`. **교과서는 학년도·학기가 정한다.**

    중간·기말은 같은 교과서를 쓰므로 한 스코프로 묶는다.
    """
    parts = [x for x in nfc(term or "").split("-") if x]
    return "-".join(parts[:2])


def label_key(school, term, unit, label):
    """라벨 지문 키. **학교 + 학년도·학기 스코프**다.

    `4과 01` 은 학교마다, 그리고 **학기마다** 다른 교과서다
    (강동1 25-2 공통영어2 4과 ≠ 26-1 공통영어1 4과 — 실측에서 4건이 겹쳤다).
    학교·학기를 넘는 같은 지문(올림포스 등)은 키가 아니라 **원문 지문이 같다는
    사실**로 합친다(§4 텍스트 동일 병합). 잘못 합치는 것보다 못 합치는 쪽이 싸다.
    """
    lab = norm_label(label)
    if not lab:
        return None
    pre = ""
    if unit:
        u = norm_label(unit)
        # 단원 라벨 토큰 중 지문 라벨에 없는 것만 앞에 붙인다
        #   `교과서 4과` + `4과 01` → 교과서-4과-01   (4과 를 두 번 쓰지 않는다)
        have = set(lab.split("-"))
        rest = [t for t in u.split("-") if t and t not in have]
        pre = "-".join(rest)
    scope = ":".join(x for x in (school, term_scope(term)) if x)
    return "%s:%s" % (scope, "-".join(x for x in (pre, lab) if x))


def key_filename(key):
    """키 → 파일명. macOS 에서 `:` 는 Finder 가 `/` 로 보여 준다 → 쓰지 않는다."""
    return nfc(key).replace(":", "__").replace("/", "-") + ".json"


# ══════════════════════════════════════════════════════════════════════
# 2. IDML 한 권 → 지문 단위
# ══════════════════════════════════════════════════════════════════════
def _tr_xy(tr):
    p = (tr or "").split()
    try:
        return float(p[-2]), float(p[-1])
    except Exception:
        return 0.0, 0.0


def _page_mm(doc):
    """첫 본문 페이지의 재단 크기(mm). 판형으로 포켓북을 가리기 위한 것."""
    for f in doc.spread_files:
        try:
            root = ET.fromstring(doc.z.read(f))
        except ET.ParseError:
            continue
        for pg in root.iter("Page"):
            gb = pg.get("GeometricBounds")
            if not gb:
                continue
            try:
                y1, x1, y2, x2 = [float(v) for v in gb.split()]
            except ValueError:
                continue
            return (x2 - x1) * 25.4 / 72.0, (y2 - y1) * 25.4 / 72.0
    return 0.0, 0.0


def is_pocketbook(doc):
    w, h = _page_mm(doc)
    return (abs(w - TRIM_MM[0]) < TRIM_TOL and abs(h - TRIM_MM[1]) < TRIM_TOL)


# ── 짧은 텍스트 후보 ───────────────────────────────────────
# 지문 식별자는 언제나 **짧고 번호를 품는다**(`250923` `4과 01` `본문1` `11강 01`).
# 주제문·요약문은 길고 번호가 없다. 이건 표기 규칙이 아니라 식별자의 성질이다.
CAND_MAXLEN = 24
CAND_MAXTOK = 4


def _spread_scan(doc, sp):
    """스프레드 하나 → (역할별 스토리, 짧은 후보). 프레임 순서를 지킨다.

    프레임이 여러 개여도 스토리는 하나인 경우가 있어(동반의어 9칸이 한 스토리)
    **스토리 id 로 중복을 없앤다** — 안 하면 카드가 아홉 배가 된다.
    """
    seen = set()
    recs = []
    for fr in sp["frames"]:
        sid = fr["story"]
        if sid in seen:
            continue
        seen.add(sid)
        paras = doc.paragraphs(sid)
        if not paras:
            continue
        txt = "\n".join(idml.plain(p["runs"]) for p in paras).strip()
        role = idml._para_role(paras)
        x, y = _tr_xy(fr["tr"])
        # 영어 지문과 한글 해석이 **둘 다 문단 스타일 `본문`** 인 책이 있다
        # (강동1 실측) → 한글 비율로 가른다.
        if role == "passage" and len(txt) >= 30:
            role = "translation" if idml.han_ratio(txt) > 0.35 else "passage"
        # `주제/요약문` 틀은 **영어** 주제+요약이다. 그와 별도로 한글 주제 한 줄을
        # 다른 스타일(`본문 주제`)로 앉힌 책이 있다(광문2 실측 72개).
        # 역할 표에 없다고 버리면 완성본에만 있던 글이 통째로 사라진다.
        if role is None and "주제" in (paras[0]["style"] or "") and txt:
            role = "topic_ko"
        short = (txt and len(txt) <= CAND_MAXLEN
                 and len(txt.split()) <= CAND_MAXTOK)
        recs.append({"role": role, "paras": paras, "text": txt,
                     "x": x, "y": y, "short": bool(short)})
    return recs


def _cluster(points, step=10.0):
    """좌표 → 슬롯. 격자로 잘라 이웃끼리 잇는다.

    한 책 안에서 **같은 자리에 반복해 나타나는 짧은 프레임**을 찾으려는 것이다.
    판형이 바뀌면 좌표는 거짓말하지만, 여기서 쓰는 것은 절대 좌표가 아니라
    *한 책 안에서의 반복* 이라 판형과 무관하다.
    격자만 쓰면 1~2pt 흔들림에 슬롯이 갈라진다(실측: y −240/−250/−260) →
    이웃 칸을 union-find 로 잇는다.
    """
    cells = {}
    for i, (x, y) in enumerate(points):
        cells.setdefault((int(round(x / step)), int(round(y / step))),
                         []).append(i)
    parent = {c: c for c in cells}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for c in cells:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                n = (c[0] + dx, c[1] + dy)
                if n in cells:
                    ra, rb = find(c), find(n)
                    if ra != rb:
                        parent[ra] = rb
    out = [None] * len(points)
    for c, idxs in cells.items():
        r = find(c)
        for i in idxs:
            out[i] = r
    return out


def harvest_book(path):
    """완성 포켓북 IDML 한 권 → [지문 단위]. 없으면 [].

    ⚠ 짤지문 스프레드(마스터 G/H)는 **한 스프레드에 지문이 둘**이다.
      `idml.read_book()` 은 첫 지문만 남기고 둘째를 버린다(강동2 실측 5지문 유실).
      여기서는 프레임 순서로 갈라 둘 다 살린다.
    """
    doc = idml.Idml(path)
    if not is_pocketbook(doc):
        return []

    # ── 1패스: 스프레드 훑기 + 짧은 후보 모으기 ──
    spreads = []
    pts, refs = [], []
    for sp in doc.spreads():
        masters = {p["master"][:1] for p in sp["pages"] if p["master"]}
        recs = _spread_scan(doc, sp)
        item = {"pages": [p["name"] for p in sp["pages"]],
                "masters": sorted(masters), "recs": recs,
                "links": sp["links"],
                "is_test": bool(masters & set("BDFL")),
                "has_passage": any(r["role"] == "passage" and
                                   len(r["text"]) >= 30 for r in recs)}
        spreads.append(item)
        if item["is_test"] or not item["has_passage"]:
            continue
        for ri, r in enumerate(recs):
            if r["short"]:
                pts.append((r["x"], r["y"]))
                refs.append((len(spreads) - 1, ri))

    # ── 슬롯 통계로 '식별자 자리' 와 '단원 라벨 자리' 를 가른다 ──
    slots = _cluster(pts)
    stat = collections.defaultdict(list)
    for slot, (si, ri) in zip(slots, refs):
        stat[slot].append(spreads[si]["recs"][ri]["text"])

    ident, unit_slot, unit_uniq = set(), None, 1
    for slot, vals in stat.items():
        uniq = len(set(vals))
        digity = sum(1 for v in vals if _DIGIT.search(v)) / float(len(vals))
        # 식별자 자리 = 스프레드마다 값이 (거의) 다르고 번호를 품는다
        if uniq >= max(2, int(len(vals) * 0.8)) and digity >= 0.6:
            ident.add(slot)
        # 단원/교재 라벨 자리 = 값이 되풀이된다(`교과서 4과` `올림포스`).
        # 값이 딱 하나뿐인 자리는 지면 장식(`TRANSLATION` `요약문` `PICTURE`)이다.
        elif uniq >= 2 and uniq > unit_uniq:
            unit_slot, unit_uniq = slot, uniq
    slot_of = {}
    for slot, (si, ri) in zip(slots, refs):
        slot_of[(si, ri)] = slot

    # 책 전체에서 딱 한 번 나오는 짧은 텍스트 — 슬롯이 흔들려 놓친 식별자의 예비책
    all_short = collections.Counter(
        spreads[si]["recs"][ri]["text"] for si, ri in refs)

    # ── 2패스: 지문 단위 만들기 ──
    units, last, unit_label = [], None, ""
    for si, sp in enumerate(spreads):
        recs = sp["recs"]
        if sp["is_test"]:
            # 암기테스트 면은 **바로 앞 지문**에 붙는다
            if last is not None:
                mt = last.setdefault("memtest", {})
                for r in recs:
                    if r["role"] == "memtest_q":
                        mt.setdefault("q", r["text"])
                    elif r["role"] == "memtest" and len(r["text"]) >= 30:
                        mt.setdefault("a", r["text"])
            continue
        if not sp["has_passage"]:
            continue

        # 단원/교재 라벨은 묶음 첫 면에만 찍힌다 → 다음 값이 올 때까지 이어 간다
        for ri, r in enumerate(recs):
            if r["short"] and slot_of.get((si, ri)) == unit_slot:
                unit_label = r["text"]

        passages = [r for r in recs
                    if r["role"] == "passage" and len(r["text"]) >= 30]
        trans = [r for r in recs if r["role"] == "translation"]
        idents = [r for ri, r in enumerate(recs)
                  if r["short"] and (slot_of.get((si, ri)) in ident
                                     or (_DIGIT.search(r["text"])
                                         and all_short[r["text"]] == 1
                                         and slot_of.get((si, ri)) != unit_slot))]
        # ⚠ 지문 프레임이 둘이라고 지문이 둘인 것은 아니다.
        #   배지가 둘이면(`본문1`·`본문2`) 다른 지문이고,
        #   배지가 **하나**면(`250943-45`) 한 장문을 두 면에 나눠 앉힌 것이다.
        #   나누면 키가 하나 없어져 조용히 버려진다(광문2 실측).
        side_page = len(passages) > 1          # 오른쪽 면이 지문에 쓰인 서식
        if len(passages) > 1 and len(idents) < 2:
            passages = [_join(passages)]
            trans = [_join(trans)] if trans else []
        pair = len(passages) > 1
        flow = _first(recs, "flownote")
        topic_p = _first(recs, "topic")
        topic_ko_p = _first(recs, "topic_ko")
        syn_p = _first(recs, "synonyms")
        topic, summary = idml.split_topic(topic_p)

        for pi, p in enumerate(passages):
            raw = idents[pi]["text"] if pi < len(idents) else (
                idents[0]["text"] if idents and not pair else "")
            u = {
                "raw_label": raw,
                "unit": unit_label,
                "pages": sp["pages"],
                "masters": sp["masters"],
                "pair": side_page,
                "parts": p.get("parts", 1),
                "passage": p["paras"],
                "passage_text": p["text"],
                "links": sp["links"],
            }
            tr = trans[pi] if pi < len(trans) else (
                trans[0] if trans and not pair else None)
            u["translation"] = tr["paras"] if tr else None
            u["translation_text"] = tr["text"] if tr else ""
            # 짤지문 스프레드는 오른쪽 면이 없다 → 플로우·동반의어가 **구조적으로**
            # 없는 것이지 빠뜨린 것이 아니다. 첫 지문에만 달아 둔다.
            if pi == 0:
                u["flownote"] = [idml.plain(l).strip()
                                 for l in idml.lines_of(flow)] if flow else []
                u["topic"], u["summary"] = topic, summary
                u["topic_ko"] = " ".join(
                    idml.plain(l).strip()
                    for l in idml.lines_of(topic_ko_p)) if topic_ko_p else ""
                u["synonyms"] = idml.parse_synonym_cards(syn_p) if syn_p else []
            else:
                u["flownote"], u["topic"], u["summary"] = [], "", ""
                u["topic_ko"] = ""
                u["synonyms"] = []
            units.append(u)
            last = u
    return units


def _join(recs):
    """한 지문이 두 프레임에 나뉘어 앉은 것 → 하나로 잇는다(앞·뒤 차례 그대로)."""
    paras = []
    for r in recs:
        paras += r["paras"]
    return {"role": recs[0]["role"], "paras": paras,
            "text": "\n".join(r["text"] for r in recs),
            "x": recs[0]["x"], "y": recs[0]["y"], "short": False,
            "parts": len(recs)}


def _first(recs, role):
    for r in recs:
        if r["role"] == role:
            return r["paras"]
    return None


# ══════════════════════════════════════════════════════════════════════
# 3. 풍부함 점수 — 어느 책의 필드를 남길지
# ══════════════════════════════════════════════════════════════════════
def _score(field, v):
    if not v:
        return 0
    if field == "synonyms":
        # 카드 수가 먼저다. 같은 수면 알맹이(유의어·반의어)가 많은 쪽.
        return len(v) * 1000 + sum(
            len(c.get("w", "")) + len(c.get("ko", "")) +
            sum(len(x) for x in c.get("syn", [])) +
            sum(len(x) for x in c.get("ant", [])) for c in v)
    if field == "flownote":
        return len(v) * 1000 + sum(len(x) for x in v)
    if field == "passage":
        # 구문분석 주석(루비)이 많을수록 값진 판본이다 — 글자 수보다 앞선다.
        ruby = sum(1 for p in v for r in p["runs"] if r.get("ruby"))
        text = sum(len(r["t"]) for p in v for r in p["runs"])
        return ruby * 10000 + text
    if field == "translation":
        return sum(len(r["t"]) for p in v for r in p["runs"])
    if isinstance(v, dict):
        return sum(len(str(x)) for x in v.values())
    return len(v) if isinstance(v, (str, list)) else 1


MERGE_FIELDS = ["passage", "translation", "flownote", "topic", "summary",
                "topic_ko", "synonyms", "memtest", "links"]
TEXT_MIRROR = {"passage": "passage_text", "translation": "translation_text"}


def _norm_text(text):
    return re.sub(r"[^a-z0-9]+", "", nfc(text or "").lower())


def similarity(a, b):
    """두 지문 원문이 얼마나 같은가. 오타 한 자 고친 판본과 아예 다른 지문을
    가르기 위한 것이다 — 둘을 같은 '충돌'로 보고하면 262권에서는 잡음이 된다."""
    return difflib.SequenceMatcher(None, a, b).quick_ratio()


def fingerprint(text):
    """영어 지문 원문 지문(指紋). 서식·공백·구두점을 지운 알맹이만."""
    t = re.sub(r"[^a-z0-9]+", "", nfc(text or "").lower())
    return hashlib.sha1(t.encode("utf-8")).hexdigest() if len(t) >= 200 else ""


# ══════════════════════════════════════════════════════════════════════
# 4. 코퍼스 만들기
# ══════════════════════════════════════════════════════════════════════
def scan_idml(root=IDML_ROOT, only=None):
    out = []
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if not d.startswith(".")]
        for f in fn:
            if not f.lower().endswith(".idml") or f.startswith("."):
                continue
            p = os.path.join(dp, f)
            if only and only not in nfc(os.path.relpath(p, root)):
                continue
            out.append(p)
    out.sort(key=lambda p: nfc(p))
    return out


def _origin(path, root=IDML_ROOT):
    """경로 → (시기, 학교).

    GDrive 폴더가 늘 `<시기>/<학교>/파일` 인 것은 아니다 — 학교 폴더 없이
    `25-2-중간/배재1_포켓북_내지.idml` 로 놓인 것도 있다(실측). 그래서 자리로
    세지 않고 **시기처럼 생긴 폴더**를 골라내고 나머지에서 학교를 얻는다.
    """
    rel = nfc(os.path.relpath(path, root)).split(os.sep)
    dirs, base = rel[:-1], os.path.splitext(rel[-1])[0]
    term = next((d for d in dirs if re.match(r"^\d{2}-\d", d)), "")
    rest = [d for d in dirs if d != term]
    school = rest[-1] if rest else re.split(r"[_\s(]", base)[0]
    return term, school


def build(limit=None, only=None, root=IDML_ROOT, out_dir=OUT):
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    files = scan_idml(root, only)
    books, skipped, unkeyed, entries = [], [], [], {}
    fp_index = collections.defaultdict(list)   # 원문 지문 → [키]
    conflicts = []
    done = 0

    for path in files:
        if limit and done >= limit:
            break
        name = nfc(os.path.relpath(path, root))
        # 지금 내보내는 중인 파일을 읽으면 BadZipFile 로 죽는다(배치와 동시 실행)
        if time.time() - os.path.getmtime(path) < 30:
            skipped.append((name, "내보내는 중"))
            continue
        try:
            units = harvest_book(path)
        except (zipfile.BadZipFile, ET.ParseError) as e:
            skipped.append((name, "깨진 IDML: %s" % e))
            continue
        except Exception as e:                        # 한 권 때문에 멈추지 않는다
            skipped.append((name, "%s: %s" % (type(e).__name__, e)))
            continue
        if not units:
            skipped.append((name, "포켓북 판형이 아님(분석본 등)"))
            continue
        done += 1
        term, school = _origin(path, root)
        books.append({"file": name, "term": term, "school": school,
                      "passages": len(units)})

        for u in units:
            key, nums, aliases, kind = _key_of(u, school, term)
            src = {"file": name, "book": school, "term": term,
                   "pages": u["pages"], "harvested": stamp, "from": "idml"}
            if not key:
                unkeyed.append({"book": name, "pages": u["pages"],
                                "label": u["raw_label"], "unit": u["unit"],
                                "head": u["passage_text"][:60]})
                continue
            fp = fingerprint(u["passage_text"])
            e = entries.get(key)
            if e is None:
                e = entries[key] = _new_entry(key, kind, school, term, u,
                                              nums, aliases)
            else:
                e["aliases"] = sorted(set(e["aliases"]) | set(aliases))
                if fp and e.get("fp") and fp != e["fp"]:
                    r = similarity(e.get("_txt", ""),
                                   _norm_text(u["passage_text"]))
                    conflicts.append({
                        "key": key, "a": e["sources"][0]["file"], "b": name,
                        "pages": u["pages"], "sim": round(r, 3),
                        "kind": "판본 차이" if r >= 0.95 else "다른 지문"})
            _merge(e, u, src)
            e["sources"].append(src)
            if fp:
                e.setdefault("fp", fp)
                e.setdefault("_txt", _norm_text(u["passage_text"]))
                if key not in fp_index[fp]:
                    fp_index[fp].append(key)

    # ── 원문이 같으면 같은 지문이다 — 학교 스코프를 넘어 합친다 ──
    #   `4과 01` 은 학교마다 다른 교과서라 키로는 못 합치지만, 올림포스처럼
    #   여러 학교가 같이 쓰는 지문은 **원문이 글자까지 같다.** 그건 안전하다.
    merged_alias = 0
    for fp, keys in fp_index.items():
        if len(keys) < 2:
            continue
        keys = sorted(keys, key=lambda k: (0 if ":" not in k else 1, k))
        head = entries[keys[0]]
        for k in keys[1:]:
            other = entries.pop(k, None)
            if other is None:
                continue
            head["aliases"] = sorted(set(head["aliases"]) | {k} |
                                     set(other["aliases"]))
            for s in other["sources"]:
                head["sources"].append(s)
            for f in MERGE_FIELDS:
                _take(head, other, f, other["provenance"].get(f))
            merged_alias += 1

    _write(entries, books, skipped, unkeyed, conflicts, merged_alias,
           stamp, out_dir)
    return entries, books, skipped, unkeyed, conflicts


def _key_of(u, school, term=""):
    """지문 단위 → (키, 번호들, 별칭들, 갈래)."""
    key, nums, aliases = expand_pno(u["raw_label"])
    if key:
        g = grade_of(school)
        if g:
            key = "%s-%s" % (g, key)
            aliases = ["%s-%s" % (g, a) for a in aliases]
        return key, nums, aliases, "mock"
    if u["raw_label"]:
        k = label_key(school, term, u["unit"], u["raw_label"])
        return k, [], [k] if k else [], "label"
    return None, [], [], ""


def _new_entry(key, kind, school, term, u, nums, aliases):
    return {"key": key, "kind": kind, "aliases": sorted(set(aliases) | {key}),
            "nums": nums, "school": school, "term": term,
            "unit": u["unit"], "label": u["raw_label"],
            "masters": u["masters"], "pair": u["pair"],
            "parts": u.get("parts", 1),
            "passage": None, "passage_text": "",
            "translation": None, "translation_text": "",
            "flownote": [], "topic": "", "summary": "", "topic_ko": "",
            "synonyms": [],
            "memtest": {}, "links": [],
            "provenance": {}, "sources": []}


def _merge(e, u, src):
    """필드마다 더 풍부한 쪽을 남긴다. 사람이 고친 필드는 건드리지 않는다."""
    for f in MERGE_FIELDS:
        prov = dict(src)
        _take(e, u, f, prov)


def _take(e, src_obj, field, prov):
    old = e.get(field)
    new = src_obj.get(field)
    if not new:
        return
    keep = e["provenance"].get(field) or {}
    if keep.get("from") in MANUAL_FROM:
        return                                  # 재수확이 사람 수정을 덮지 않는다
    if _score(field, new) <= _score(field, old):
        return
    e[field] = new
    if prov:
        e["provenance"][field] = prov
    mirror = TEXT_MIRROR.get(field)
    if mirror and mirror in src_obj:
        e[mirror] = src_obj[mirror]


# ══════════════════════════════════════════════════════════════════════
# 5. 쓰기 + 리포트
# ══════════════════════════════════════════════════════════════════════
def _write(entries, books, skipped, unkeyed, conflicts, merged_alias,
           stamp, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    index = {}
    for key, e in sorted(entries.items()):
        out = dict(e)
        out.pop("fp", None)
        out.pop("_txt", None)
        with open(os.path.join(out_dir, key_filename(key)), "w",
                  encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        index[key] = {
            "kind": e["kind"], "label": e["label"], "unit": e["unit"],
            "school": e["school"], "term": e["term"], "pair": e["pair"],
            "grade": grade_of(e["school"]), "parts": e.get("parts", 1),
            "aliases": [a for a in e["aliases"] if a != key],
            "syn": len(e["synonyms"]), "flow": len(e["flownote"]),
            "ruby": sum(1 for p in (e["passage"] or []) for r in p["runs"]
                        if r.get("ruby")),
            "chars": len(e["passage_text"]),
            "translation": bool(e["translation_text"]),
            "topic": bool(e["topic"]), "topic_ko": bool(e["topic_ko"]),
            "books": sorted({s["file"] for s in e["sources"]}),
            # 사람이 바로 찾아가려면 **어느 책 몇 쪽**인지가 있어야 한다
            "where": [{"file": s["file"], "pages": "-".join(s["pages"])}
                      for s in e["sources"]],
            "file": key_filename(key),
        }
    real = [c for c in conflicts if c.get("kind") != "판본 차이"]
    meta = {"harvested": stamp, "books": books, "passages": len(entries),
            "conflicts_real": len(real),
            "skipped": [{"file": a, "why": b} for a, b in skipped],
            "unkeyed": len(unkeyed), "conflicts": len(conflicts),
            "merged_by_text": merged_alias}
    with open(os.path.join(out_dir, "_index.json"), "w",
              encoding="utf-8") as f:
        json.dump({"_meta": meta, "passages": index}, f,
                  ensure_ascii=False, indent=1)
    write_reports(index, meta, unkeyed, conflicts, out_dir)
    return index, meta


def write_reports(index, meta, unkeyed, conflicts, out_dir):
    _empty_md(index, meta, out_dir)
    _unkeyed_md(unkeyed, meta, out_dir)
    _conflicts_md(conflicts, meta, out_dir)


def _where(v):
    """`책 p.2-3` 목록. 같은 책이 두 번 나오면 한 번만."""
    seen, out = set(), []
    for w in v.get("where") or []:
        s = "%s p.%s" % (w["file"], w["pages"] or "?")
        if s not in seen:
            seen.add(s)
            out.append(s)
    return "<br>".join(out) or "<br>".join(v["books"]) or "—"


def _empty_md(index, meta, out_dir):
    """**0개만 결함이다.** 칸이 3개든 6개든 있으면 정상."""
    syn0 = {k: v for k, v in index.items() if v["syn"] == 0 and not v["pair"]}
    flow0 = {k: v for k, v in index.items() if v["flow"] == 0 and not v["pair"]}
    pair0 = {k: v for k, v in index.items()
             if v["pair"] and (v["syn"] == 0 or v["flow"] == 0)}
    L = ["# 포켓북 코퍼스 — 비어 있는 자리", "",
         "수확 %s · 지문 %d개" % (meta["harvested"], meta["passages"]), "",
         "> 동반의어 칸은 3~9장으로 제각각이고 **하나라도 있으면 정상**이다.",
         "> 여기 적힌 것은 **하나도 없는** 지문뿐이다.", "",
         "| | 개수 |", "|---|---|",
         "| 동반의어 0개 | **%d** |" % len(syn0),
         "| 플로우노트 0개 | **%d** |" % len(flow0),
         "| 짤지문(오른쪽 면 없음, 참고) | %d |" % len(pair0),
         "| 한글 해석 없음 | %d |" % sum(
             1 for v in index.values() if not v["translation"]),
         "| 주제/요약문 없음 | %d |" % sum(
             1 for v in index.values() if not v["topic"]), ""]

    def block(title, d, note=""):
        L.append("## %s — %d개" % (title, len(d)))
        if note:
            L.append("")
            L.append(note)
        L.append("")
        if not d:
            L.append("없음.")
            L.append("")
            return
        L.append("| 키 | 라벨 | 단원 | 학교 | 출처 책 · 쪽 |")
        L.append("|---|---|---|---|---|")
        for k, v in sorted(d.items(), key=lambda kv: (kv[1]["school"], kv[0])):
            L.append("| `%s` | %s | %s | %s | %s |"
                     % (k, v["label"] or "—", v["unit"] or "—",
                        v["school"], _where(v)))
        L.append("")

    block("동반의어 0개", syn0)
    block("플로우노트 0개", flow0)
    block("짤지문 — 서식상 오른쪽 면이 없다", pair0,
          "> 한 스프레드에 지문이 둘인 면이다. **빠뜨린 것이 아니다.**")
    _put(out_dir, "_empty.md", L)


def _unkeyed_md(unkeyed, meta, out_dir):
    L = ["# 키를 못 만든 지문", "",
         "수확 %s · %d개" % (meta["harvested"], len(unkeyed)), "",
         "> 조용히 버리지 않는다. 지문번호 배지가 아예 없거나, 배지 자리가",
         "> 책마다 달라 슬롯 판정에서 빠진 것이다.", ""]
    if unkeyed:
        L += ["| 책 | 쪽 | 라벨 | 단원 | 지문 첫머리 |", "|---|---|---|---|---|"]
        for u in unkeyed:
            L.append("| %s | %s | %s | %s | %s |"
                     % (u["book"], "-".join(u["pages"]), u["label"] or "—",
                        u["unit"] or "—", u["head"].replace("|", "/")))
    else:
        L.append("없음.")
    _put(out_dir, "_unkeyed.md", L)


def _conflicts_md(conflicts, meta, out_dir):
    real = [c for c in conflicts if c.get("kind") != "판본 차이"]
    var = [c for c in conflicts if c.get("kind") == "판본 차이"]
    L = ["# 키 충돌 — 같은 키인데 지문 원문이 다르다", "",
         "수확 %s · 진짜 충돌 **%d건** · 판본 차이 %d건"
         % (meta["harvested"], len(real), len(var)), "",
         "> **진짜 충돌** = 같은 키에 아예 다른 지문. 키를 갈라야 한다.",
         "> **판본 차이** = 같은 지문인데 글자가 조금 다르다(오타 수정본 등).",
         "> 코퍼스는 둘 중 더 풍부한 쪽을 남긴다 — 확인만 하면 된다.", ""]
    for title, rows in (("진짜 충돌", real), ("판본 차이", var)):
        L.append("## %s — %d건" % (title, len(rows)))
        L.append("")
        if not rows:
            L += ["없음.", ""]
            continue
        L += ["| 키 | 닮음 | 먼저 | 나중 | 쪽 |", "|---|---|---|---|---|"]
        for c in rows:
            L.append("| `%s` | %s | %s | %s | %s |"
                     % (c["key"], c.get("sim", "?"), c["a"], c["b"],
                        "-".join(c["pages"])))
        L.append("")
    _put(out_dir, "_conflicts.md", L)


def _put(out_dir, name, lines):
    with open(os.path.join(out_dir, name), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def report(out_dir=OUT):
    p = os.path.join(out_dir, "_index.json")
    if not os.path.exists(p):
        print("코퍼스가 없다. 먼저 `corpus.py build`.")
        return 1
    d = json.load(open(p, encoding="utf-8"))
    idx, meta = d["passages"], d["_meta"]
    _empty_md(idx, meta, out_dir)
    syn0 = sum(1 for v in idx.values() if v["syn"] == 0 and not v["pair"])
    flow0 = sum(1 for v in idx.values() if v["flow"] == 0 and not v["pair"])
    print("책 %d권 · 지문 %d개 · 키못만듦 %d · 진짜충돌 %d(판본차이 %d) · 원문병합 %d"
          % (len(meta["books"]), meta["passages"], meta["unkeyed"],
             meta.get("conflicts_real", meta["conflicts"]),
             meta["conflicts"] - meta.get("conflicts_real", 0),
             meta.get("merged_by_text", 0)))
    print("동반의어 0개 %d · 플로우노트 0개 %d" % (syn0, flow0))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="완성 포켓북 IDML → 지문 코퍼스")
    ap.add_argument("cmd", choices=["build", "report"])
    ap.add_argument("--limit", type=int, default=None, help="처리할 책 수")
    ap.add_argument("--only", default=None, help="경로에 이 글자가 든 것만")
    ap.add_argument("--root", default=IDML_ROOT)
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args(argv)
    if a.cmd == "report":
        return report(a.out)
    entries, books, skipped, unkeyed, conflicts = build(
        a.limit, a.only, a.root, a.out)
    print("책 %d권 · 지문 %d개 · 키못만듦 %d · 충돌후보 %d"
          % (len(books), len(entries), len(unkeyed), len(conflicts)))
    for f, why in skipped:
        print("  건너뜀 %s — %s" % (f, why))
    return report(a.out)


if __name__ == "__main__":
    sys.exit(main())
