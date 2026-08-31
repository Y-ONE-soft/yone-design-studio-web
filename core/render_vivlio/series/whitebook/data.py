"""화이트북 실전문제 원고(docx) → data.json.

원고는 Day 하나에 `문제` 한 벌 + `정답` 한 벌이다.

    화이트북 2권 Day 01   워드마스터 고등 COMPLETE Day 21~30  어휘 연습 (20문항)
    [문제]
    1. 다음 문장의 밑줄 친 부분 중, 문맥상 적절하지 않은 것은?
    ① The two witnesses' accounts …

**구조로 읽는다 — 파일 이름도 형식 문구도 믿지 않는다.**
  · Day 번호 = 문서 첫 줄의 `Day N`(범위 `Day 21~30` 은 Day 가 아니다).
    첫 줄에 없으면 파일 이름, 그것도 없으면 폴더 안 순서.
  · 갈래 = `[문제]` / `[정답…]` 표식 줄. 없으면 **정답 줄의 비율**로 가른다
    (정답본은 거의 모든 항목이 `N. ⑤ …` 로 시작한다).
  · 문항 = `N.` 로 시작하고 번호가 직전 +1 인 단락.
  · 선지 = ①~⑤. **한 줄에 뭉쳐 온 선지**(`① a   ② b   …`)는 서식을 지키며 쪼갠다.
  · 보기 = `<보기>` 다음부터 선지 전까지. 지문 = 그 밖의 긴 줄.
  · 정답 항목 = `N.` 줄(= 정답·유형·풀이) + 뒤따르는 부연 줄(선지 해석·뜻·지문 해석).

인식 게이트: Day 마다 문항 수 == 정답 수, 번호 1..N 연속, 선지 5개, 정답 비어 있지
않음. 하나라도 어긋나면 조판하지 않고 중단한다(침묵 유실 금지).
"""
import json
import os
import re
import unicodedata

from core.render_vivlio.series.blackbook.data import (
    GateError, gate, plain, read_paras, rich, strip_lead, txt)

CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩"
RE_ITEM = re.compile(r"^\s*(\d+)\.\s")
RE_BOGI = re.compile(r"^\s*[<〈]\s*보\s*기\s*[>〉]\s*$")
RE_MARK_Q = re.compile(r"^\s*\[\s*문제\s*\]\s*$")
RE_MARK_A = re.compile(r"^\s*\[\s*정답")
RE_BULLET = re.compile(r"^\s*[∙•·]\s*")
RE_ARROW = re.compile(r"^\s*[→⇒]\s*")
# 이름·머리글의 `Day 21~30` 은 교재 범위지 Day 번호가 아니다.
RE_DAY = re.compile(r"Day\s*0*(\d+)\s*(?![~∼〜\-–])")
# 원고 앞머리의 기입란(학년 반 번 이름) — 조판에는 들어가지 않는다
RE_NAMEROW = re.compile(r"^\s*학년.{0,20}이름")


# ------------------------------------------------------------------ 선지 쪼개기

def split_choices(segs):
    """`① a   ② b   ③ c` 한 줄 → 선지 다섯 줄. 서식(밑줄·굵기)은 그대로 지킨다.

    ⚠ 글자를 이어 붙여 쪼개면 **밑줄이 사라진다**(어휘 문제는 밑줄이 곧 문제다)
      → 세그먼트를 걸어가며 자른다.
    """
    parts, cur = [], []
    for t, fl in segs:
        buf = ""
        for ch in t:
            if ch in CIRCLED and (buf.strip() or cur):
                if buf:
                    cur.append((buf, fl))
                if cur:
                    parts.append(cur)
                cur, buf = [], ch
            else:
                buf += ch
        if buf:
            cur.append((buf, fl))
    if cur:
        parts.append(cur)
    out = []
    for p in parts:
        # 앞뒤 공백 정리 (한 줄에 뭉쳐 있던 사이 간격)
        while p and not p[0][0].strip():
            p.pop(0)
        while p and not p[-1][0].strip():
            p.pop()
        if not p:
            continue
        p[0] = (p[0][0].lstrip(), p[0][1])
        p[-1] = (p[-1][0].rstrip(), p[-1][1])
        out.append(p)
    return out


def _choice(segs):
    return {"t": "choice", "mark": txt(segs)[0],
            "body": rich(strip_lead(segs, 1))}


# ------------------------------------------------------------------ 문제 파서

def parse_problems(paras):
    items, cur, expect, mode = [], None, None, None

    def push():
        if cur is not None:
            items.append(cur)

    for p in paras:
        t = p["text"].strip()
        if not t or RE_MARK_Q.match(t) or RE_NAMEROW.match(t):
            continue
        m = RE_ITEM.match(t)
        if m and (expect is None or int(m.group(1)) == expect):
            push()
            cur = {"no": int(m.group(1)),
                   "stem": rich(strip_lead(p["segs"], m.end())),
                   "blocks": []}
            expect = cur["no"] + 1
            mode = None
            continue
        if cur is None:
            continue                      # 머리글 영역
        B = cur["blocks"]
        if RE_BOGI.match(t):
            B.append({"t": "bogi", "items": []})
            mode = "bogi"
            continue
        if t[0] in CIRCLED:
            for seg in split_choices(p["segs"]):
                B.append(_choice(seg))
            mode = None
            continue
        if RE_ARROW.match(t):
            B.append({"t": "trans", "body": rich(strip_lead(p["segs"], 1))})
            mode = None
            continue
        if mode == "bogi":
            B[-1]["items"].append(rich(p["segs"]))
            continue
        # 남는 것은 지문
        if B and B[-1]["t"] == "passage":
            B[-1]["paras"].append(rich(p["segs"]))
        else:
            B.append({"t": "passage", "paras": [rich(p["segs"])]})
        mode = None
    push()
    return items


# ------------------------------------------------------------------ 정답 파서

def parse_answers(paras):
    items, cur, expect = [], None, None
    for p in paras:
        t = p["text"].strip()
        if not t or RE_MARK_A.match(t):
            continue
        m = RE_ITEM.match(t)
        if m and (expect is None or int(m.group(1)) == expect):
            if cur:
                items.append(cur)
            cur = {"no": int(m.group(1)),
                   "answer": rich(strip_lead(p["segs"], m.end())),
                   "notes": []}
            expect = cur["no"] + 1
            continue
        if cur is None:
            continue
        cur["notes"].append(rich(p["segs"]))
    if cur:
        items.append(cur)
    return items


# ------------------------------------------------------------------ 원고 모으기

def _norm(s):
    return unicodedata.normalize("NFC", s)


def _classify(paras):
    """(갈래, Day 번호 또는 None) — 표식이 없으면 구조로 가른다."""
    head = next((p["text"].strip() for p in paras if p["text"].strip()), "")
    kind = None
    for p in paras[:8]:
        t = p["text"].strip()
        if RE_MARK_Q.match(t):
            kind = "문제"
            break
        if RE_MARK_A.match(t):
            kind = "정답"
            break
    if kind is None:
        # 정답본은 `N.` 줄이 곧 정답 줄이라 ①~⑤ 가 번호 바로 뒤에 붙는다.
        n_ans = sum(1 for p in paras
                    if re.match(r"^\s*\d+\.\s*[①-⑩]", p["text"].strip()))
        kind = "정답" if n_ans >= 5 else "문제"
    md = RE_DAY.search(head)
    return kind, (int(md.group(1)) if md else None)


def collect(cfg, log=print):
    """원고 폴더 → {day: {'문제': paras, '정답': paras}}"""
    m = cfg.section("manuscript") or {}
    src = cfg.resolve(m.get("dir", "원고"))
    if not os.path.isdir(src):
        raise GateError(f"원고 폴더 없음: {src}")
    files = sorted(f for f in os.listdir(src)
                   if f.lower().endswith(".docx") and not f.startswith("~$"))
    gate(files, f"원고 없음: {src}")
    days, seq = {}, 0
    for f in files:
        paras = read_paras(os.path.join(src, f))
        kind, day = _classify(paras)
        if day is None:                    # 머리글에 없으면 파일 이름 → 순서
            md = RE_DAY.search(_norm(f))
            if md:
                day = int(md.group(1))
            else:
                seq += 1
                day = seq
        slot = days.setdefault(day, {})
        gate(kind not in slot,
             f"Day {day} {kind} 원고가 둘이다: {f}")
        slot[kind] = (f, paras)
        log(f"  {f}  → Day {day} {kind} ({len(paras)}단락)")
    return days


# ------------------------------------------------------------------ main

def build(cfg, log=print):
    days = collect(cfg, log)
    want = (cfg.section("manuscript") or {}).get("questions_per_day", 20)
    book = {"title": cfg.book.get("title", ""), "days": []}
    for day in sorted(days):
        slot = days[day]
        gate("문제" in slot, f"Day {day} 문제 원고 없음")
        gate("정답" in slot, f"Day {day} 정답 원고 없음")
        head = next((p["text"].strip() for p in slot["문제"][1]
                     if p["text"].strip()), "")
        items = parse_problems(slot["문제"][1])
        ans = parse_answers(slot["정답"][1])

        gate(len(items) == want,
             f"Day {day} 문항 {len(items)}개 (기대 {want})")
        gate(len(ans) == len(items),
             f"Day {day} 문항 {len(items)} vs 정답 {len(ans)} 불일치")
        nos = [i["no"] for i in items]
        gate(nos == list(range(1, len(nos) + 1)),
             f"Day {day} 문항 번호 비연속: {nos[:6]}")
        gate([a["no"] for a in ans] == nos, f"Day {day} 정답 번호 불일치")
        for it in items:
            ch = [b for b in it["blocks"] if b["t"] == "choice"]
            gate(len(ch) == 5,
                 f"Day {day} {it['no']}번 선지 {len(ch)}개 "
                 f"({plain(it['stem'])[:24]})")
            gate(plain(it["stem"]).strip(), f"Day {day} {it['no']}번 발문 없음")
        for a in ans:
            gate(plain(a["answer"]).strip(), f"Day {day} {a['no']}번 정답 없음")

        book["days"].append({
            "day": day, "header": head,
            "label": f"DAY {day:02d}",
            "problems": items, "answers": ans})

    out = cfg.path("data.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(book, f, ensure_ascii=False, indent=1)
    log("■ 인식 결과")
    for D in book["days"]:
        kinds = {}
        for it in D["problems"]:
            k = ("보기" if any(b["t"] == "bogi" for b in it["blocks"])
                 else "지문" if any(b["t"] == "passage" for b in it["blocks"])
                 else "영작" if any(b["t"] == "trans" for b in it["blocks"])
                 else "선지")
            kinds[k] = kinds.get(k, 0) + 1
        log(f"  {D['label']}  문항 {len(D['problems'])} / 정답 "
            f"{len(D['answers'])}  ({', '.join(f'{k}{v}' for k, v in sorted(kinds.items()))})")
    log(f"  합계 Day {len(book['days'])} · 문항 "
        f"{sum(len(D['problems']) for D in book['days'])}  "
        f"→ {os.path.basename(out)}")
    return out


def load(cfg, log=None):
    from core.render_vivlio import errata
    return errata.load_data(cfg, log)
