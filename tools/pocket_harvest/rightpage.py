# -*- coding: utf-8 -*-
"""포켓북 **오른쪽 면을 직접 쓴다** — 작업 목록 내보내기 · 저술물 넣기 · 규격 검사.

## 왜

오른쪽 면(플로우노트·한글 주제/요약문·동반의어)은 지금까지 교재팀이 완성
`.indd` 에 직접 타이핑했다. 비블리오로 넘어오면 그 파일이 없으므로, **우리가
쓴다.** 분석본(영어 지문·구문분석·해석)만 교재팀에서 받고 나머지는 여기서 만든다.

## ⚠ 모양보다 **내용**이다

처음 이 파일은 줄 수·글자 수만 쟀다. 그것만 맞춰 놓고 "규격 통과"라고 했는데,
지적을 받았다 — *"들어가는 내용이 훨씬 100배는 더 중요해. 시험 전에 학생들이
들고다니면서 본문 내용 익히고 중요한 거 익히고 단어 외우고 하는 책"*.
맞는 말이고, 실측이 그걸 뒷받침한다. 완성본 1,216지문을 해석과 나란히 놓고
재 보니 **내용 쪽 규칙이 따로 있었다**:

    표제      **`[역할] 그 지문의 내용`** 꼴이다. 대괄호 안은 이 대목이 글의
              어느 부분인지 말하는 **역할 딱지**(`결론`·`예시`·`도입`·`그러나`)이고,
              그 지문의 내용은 **딱지 옆**에 붙는다.

                  ○ `[결론] 예술가가 하는 일`
                       `→ 남이 버린 물건을 재료로 삼아…`
                  ✘ `[예술가가 하는 일]`   ← 내용이 무슨 부분인지 모른다
                  ✘ `[상황]` `[맺음]`      ← 어느 지문에나 붙어 내용이 없다

              완성본 표제가 중앙 3자인 것은 대괄호 안이 **딱지**이기 때문이다
              (`결론` 205회 · `예시` 171회 · `도입` 46회). 내용을 대괄호 안에
              넣으면 색과 간격은 붙지만 **읽는 사람이 갈피를 못 잡는다.**
              대괄호 안이 지문의 말이어야 하는 게 아니라, **딱지 옆 글**이
              지문의 말이어야 한다.
    고르기    줄 수 = 해석 문장 수의 **1.0~1.9배(중앙 1.4)**, 짚는 문장은 **67%**.
              모든 문장을 옮기지 않는다. 주장·근거·수치·대조·결론을 남기고
              꾸밈은 버린다. 전부 옮기면 해석을 한 번 더 쓴 것이지 노트가 아니다.
    구체 정보 해석에 숫자가 있으면 **84%** 가 그 숫자를 그대로 살린다
              (`600년도 더 전`, `빛이 최소 1,000년 여행`). 고유명사도 같다.
              시험에 나오는 것이 그 구체값이라 뭉개면 안 된다.
    영어 병기 **40%** 가 시험에 나올 영어 표현을 괄호로 붙인다
              (`“볼 때 믿겠다(I’ll believe it when I see it)”`), 인용부호 36%.
    사슬      인과는 `→` 로 **이어서** 보인다 — 표제로 자꾸 끊으면 논리가 끊긴다.

## 모양 규격 (같은 코퍼스 실측)

    플로우노트   줄 수 3~25 (중앙 12, 25~75% 구간 9~14)
                줄 길이 중앙 23자 (75% 31자, 40자 넘으면 두 줄로 끊는다)
                줄머리 비율 — 맨글 32% · `→` 29% · `[표제]` 22% · `-·` 11% · `①` 6%
                ⚠ `**굵게**` 는 별표가 그대로 인쇄된다. 쓰지 않는다.
    주제        한 줄. 중앙 49자 (25~75% 구간 33~61자)
    요약문      한두 문장. 중앙 158자 (25~75% 구간 112~199자)
    동반의어    **8~9장이 표준** (8장 23% · 9장 22% · 6장 19% · 7장 15%)
                유의어 중앙 3개 · 반의어 중앙 2개 · **19% 는 반의어 없음**
                표제어는 **82% 가 그 지문에 실제로 나오는 낱말**이고,
                지문에 나온 **차례대로** 뽑는 편이다(앞 절반에서 58%).
                길이 중앙 8자 · 숙어/구 5% ·
                품사 = 명사 53% · 동사 25% · 형용사 21% · 부사 2%

⚠ 주제·요약문은 **한글**이다. 옛 완성본에는 영어로 된 것이 많지만(25-2 세대),
  26-1 부터 한글로 바뀌었고 포켓북이 쓰는 것은 한글이다.

## 쓰는 자리

    조판/교재/포켓북/_authored/<지문키>.json
        {"flownote": [...], "topic": "...", "summary": "...",
         "synonyms": [{"w":..., "ko":..., "syn":[...], "ant":[...]}]}

우선순위는 **교재팀 원고 > 우리가 쓴 것 > 코퍼스**다. 교재팀이 준 것이 있으면
그것을 쓴다 — 사람이 쓴 것을 기계가 덮지 않는다.

    python3 tools/pocket_harvest/rightpage.py todo [책폴더…]   # 쓸 거리 내보내기
    python3 tools/pocket_harvest/rightpage.py check            # 규격 검사
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.expanduser("~/Documents/작업/Y.ONE STUDIO/조판/교재/포켓북")
AUTHORED = os.path.join(ROOT, "_authored")

# 완성본 실측에서 뽑은 규격. 벗어나면 `check` 가 말한다.
SPEC = {
    "flow_lines": (5, 20),        # 줄 수
    "topic_len": (18, 80),
    "summary_len": (70, 260),
    # ── 동반의어를 **어디서 고르나** (완성본 + 분석본 대조 실측) ─────
    #
    # ⚠ 이것을 조사하지 않고 지문을 읽어 내 판단으로 낱말을 뽑았다. 교재팀이
    #   "쓸 수 없는 수준"이라고 한 이유다. 완성본 동반의어와 그 지문의 분석본
    #   **중요어휘 표**를 맞대어 보니 규칙이 있었다:
    #
    #     · 표제어의 **84%** 가 분석본 중요어휘 표에 있는 낱말이다
    #     · 어휘표는 지문당 중앙 27낱말 → 그중 **26%**(중앙 6장)만 카드가 된다
    #     · 고르는 자리는 표 전체에 걸쳐 있다(앞 44% · 가운데 29% · 뒤 27%)
    #     · 뜻(한국어)은 **61%** 가 어휘표의 뜻을 그대로 쓴다
    #     · 구·숙어보다 **한 낱말**을 고른다(뽑힘 1.10낱말 · 안 뽑힘 1.34낱말)
    #
    #   그러니 순서는 **어휘표에서 고르기**이지 지문을 읽고 짓기가 아니다.
    #   기존 포켓북에 같은 지문이 있으면 **그 동반의어를 그대로 가져온다** —
    #   교재팀이 이미 고른 것이 정본이다.
    #
    # ⚠ 전수 실측(1,220지문): 8장 23% · 9장 22% · 6장 19% · 7장 15%.
    #   **8~9장이 표준**이다. 처음에 중앙값 7만 보고 6~8로 잡았다가
    #   "왜 7개만 뽑느냐" 는 지적을 받았다 — 되도록 9장을 채운다.
    "syn_cards": (7, 9),
    "syn_words": (2, 5),          # 유의어 개수
    "ant_words": (0, 5),
    # ── 내용 규격 (완성본 1,216지문 실측) ─────────────────────────
    # ⚠ 표제는 **길이로 재면 안 된다**. 완성본은 `[결론]` 을 205번, `[도입]`
    #   을 46번 쓴다 — 논리 딱지 자체가 틀린 게 아니다. 틀린 것은 표제가
    #   **전부** 그런 딱지여서 이 지문이 무슨 글인지 하나도 안 남는 경우다.
    "head_own": 0.30,             # 표제 중 지문의 말을 쓴 비율 (완성본 35%)
    "head_max": 8,                # 대괄호 안은 **역할 딱지**다 — 짧아야 한다
    "head_bare": 0.5,             # 딱지만 있고 옆에 글이 없는 줄의 최대 비율
    "line_ratio": (0.8, 2.1),     # 줄 수 ÷ 해석 문장 수 (완성본 중앙 1.4)
    "keep_num": True,             # 해석의 숫자는 살린다 (완성본 84%)
    # ⚠ 44자가 아니다. 플로우노트는 **두 단**이고 한 단이 53mm 다 —
    #   9pt 도담도담으로 한글 24자 남짓이면 꽉 찬다(완성본 줄 길이 중앙 23자와
    #   정확히 같은 이유다). 44자로 두면 모든 줄이 두 줄로 접힌다.
    "flow_len": 26,
}
# 완성본 표제 3,155개에 **한 번도(또는 한 번)** 안 나온 말. 내가 쓰던 것들이
# 여기 몰려 있었다 — `맺음` `인식` `안내` `바람` `방침` `내용` `물음` 은 0회,
# `본론` `정리` 는 1회다. 완성본이 안 쓰는 말은 우리도 쓰지 않는다.
FLAT_HEADS = {
    "맺음", "인식", "안내", "바람", "방침", "내용", "물음", "본론", "정리",
    "서두", "끝맺음", "총평", "개요",
}
_HAN = re.compile(r"[가-힣]")


def _wlen(s):
    """한글 자 수로 잰 줄 길이. 영문·숫자는 폭이 절반쯤이라 그렇게 센다."""
    return sum(1.0 if ord(c) > 0x2000 else 0.55 for c in s)
_HEAD = re.compile(r"^\s*[\[［]([^\]］]+)[\]］]")
_NUM = re.compile(r"\d[\d,.]*")


def _plain(runs):
    return "".join(x.get("t", "") for p in (runs or []) for x in p.get("runs", []))


def todo(books=None, out=None):
    """쓸 거리 내보내기 — 오른쪽 면이 빈 지문의 **영어 원문 + 한글 해석**.

    지문을 안 읽고는 못 쓴다. 조판이 이미 들고 있는 글을 그대로 꺼내 준다.
    """
    books = books or sorted(glob.glob(os.path.join(ROOT, "*", "*")))
    got, seen = [], set()
    for b in books:
        f = os.path.join(b, "build", "_studio_data.json")
        if not os.path.exists(f):
            continue
        tag = "/".join(os.path.normpath(b).split(os.sep)[-2:])
        cat = ""
        for r in json.load(open(f, encoding="utf-8"))["passages"]:
            cat = (r.get("category") or "").strip() or cat
            if r.get("kind") == "memtest":
                continue
            key = r.get("key") or r.get("no") or r.get("label")
            uid = (tag, key, cat)
            if not key or uid in seen:
                continue
            need = [k for k in ("flownote", "topic", "summary", "synonyms")
                    if not r.get(k)]
            if not need:
                continue
            seen.add(uid)
            got.append({
                "key": key, "book": tag, "file": fname(key, tag, cat),
                "category": cat,
                "label": r.get("no") or r.get("label") or "",
                "need": need,
                "passage": _plain(r.get("passage_runs") and
                                  [{"runs": r["passage_runs"]}]),
                "translation": r.get("translation") or "",
            })
    out = out or os.path.join(AUTHORED, "_todo.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(got, f, ensure_ascii=False, indent=1)
    print("쓸 지문 %d개 → %s" % (len(got), out))
    return got


def fname(key, book="", cat=""):
    """저술물 파일 이름 = **책 + 지문 키**.

    ⚠ 키만 쓰면 조용히 엉뚱한 글이 붙는다. `본문2`·`서술형 Practice` 는 학교가
      달라도, 심지어 **한 책 안에서도** 겹치는 이름이다(광문1 실측: 5강 뒤와
      7강 뒤에 `서술형 Practice` 가 각각 있다). 겹치면 두 지문에 같은
      플로우노트가 인쇄되는데, 게이트로도 안 잡힌다 — 둘 다 채워져 있으니까.
      그래서 **단원(`cat`)까지** 이름에 넣는다. 단원이 빈 지문은 부르는 쪽에서
      앞 지문의 단원을 이어받아 넘겨 준다(`_cat_run`).
    """
    key = str(key)
    cat = str(cat or "").strip()
    if cat and not key.startswith(cat):
        key = "%s %s" % (cat, key)
    stem = "%s__%s" % (book, key) if book else key
    return re.sub(r"[/\\]", "_", stem)


def load(key, book="", cat=""):
    for stem in [fname(key, book, cat), fname(key, book), fname(key)]:
        p = os.path.join(AUTHORED, "%s.json" % stem)
        if os.path.exists(p):
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    return None


def save(key, data, book="", cat=""):
    os.makedirs(AUTHORED, exist_ok=True)
    p = os.path.join(AUTHORED, "%s.json" % fname(key, book, cat))
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return p


def _sents(t):
    return [x for x in re.split(r"(?<=[.?!다])\s+", re.sub(r"\s+", " ", t or ""))
            if len(x) > 6]


def check(data, key="", src=""):
    """규격 검사 → 어긋난 것 목록(사람이 읽는 말).

    `src` 는 그 지문의 **한글 해석**이다. 주면 모양뿐 아니라 **내용**까지 본다
    — 표제가 이 지문의 말인지, 해석의 숫자를 살렸는지, 문장을 골랐는지.
    """
    bad = []
    fl = data.get("flownote") or []
    lo, hi = SPEC["flow_lines"]
    if fl and not (lo <= len(fl) <= hi):
        bad.append("플로우 %d줄 (규격 %d~%d)" % (len(fl), lo, hi))
    long = [l for l in fl if _wlen(l) > SPEC["flow_len"]]
    if long:
        bad.append("플로우 %d줄이 한 단(한글 %d자)을 넘음 — 끊어야 함: %r"
                   % (len(long), SPEC["flow_len"], long[0][:30]))
    if fl and not any(re.match(r"^\s*\[", l) for l in fl):
        bad.append("표제 대괄호가 하나도 없음 (완성본은 22%가 표제 줄)")
    if any("**" in l for l in fl):
        bad.append("`**굵게**` 가 있음 — 별표가 그대로 인쇄된다")
    # ── 내용 ─────────────────────────────────────────────
    heads = [m.group(1).strip() for l in fl
             for m in [_HEAD.match(l)] if m]
    body_ = re.sub(r"\s+", " ", src or "")
    # 대괄호 안이 길다 = 내용을 딱지 안에 넣었다는 뜻이다
    long_h = [h for h in heads if len(h) > SPEC["head_max"]]
    if long_h:
        bad.append("표제 %d개가 딱지가 아니라 내용 — `[역할] 내용` 꼴로 "
                   "바꿔야 한다: %s" % (len(long_h), ", ".join(long_h[:3])))
    # 딱지만 있고 옆에 글이 없으면 그 딱지는 아무것도 말해 주지 않는다
    bare = [l for l in fl for m in [_HEAD.match(l)]
            if m and not l[m.end():].strip()]
    if heads and len(bare) > len(heads) * SPEC["head_bare"]:
        bad.append("딱지만 있고 옆에 내용이 없는 줄 %d/%d — `[결론] 예술가가 "
                   "하는 일` 처럼 붙여야 한다" % (len(bare), len(heads)))
    flat = [h for h in heads if h in FLAT_HEADS]
    if flat:
        bad.append("표제 %d개가 어느 지문에나 붙는 말 — 이 지문의 내용을 넣어야 "
                   "한다: %s" % (len(flat), ", ".join(flat[:5])))
    if src:
        body = body_
        # ⚠ 지문의 말이 있어야 하는 곳은 **대괄호 안이 아니라 딱지 옆**이다.
        #   `[결론] 예술가가 하는 일` 에서 `결론` 은 역할이고 내용은 그 옆이다.
        side = [l[m.end():].strip() for l in fl
                for m in [_HEAD.match(l)] if m and l[m.end():].strip()]
        if side:
            own = sum(1 for x in side
                      if any(w in body for w in re.findall(r"[가-힣]{2,}", x)))
            if own / len(side) < SPEC["head_own"]:
                bad.append("딱지 옆 글 %d개 중 지문의 말을 쓴 것이 %d개뿐 — "
                           "딱지 옆에는 이 지문의 내용이 와야 한다"
                           % (len(side), own))
        ns = _sents(body)
        # ⚠ 실용문(광고·안내문)은 **문장 수로 재면 안 된다**. 항목이 줄로 늘어서
        #   있어 해석은 5문장인데 노트는 12줄이 정상이다 — 그걸 "다 옮겼다"고
        #   나무라면 되레 내용을 빼게 된다.
        if sum(1 for w in ("달러", "오전", "오후", "참가비", "등록비", "장소",
                           "예약", "일정", "요금", "문의", "신청")
               if w in body) >= 3:
            ns = []
        if ns and fl:
            r = len(fl) / len(ns)
            lo2, hi2 = SPEC["line_ratio"]
            if r > hi2:
                bad.append("해석 %d문장에 플로우 %d줄 — 문장을 다 옮겼다. "
                           "고르지 않으면 노트가 아니다 (완성본 1.4배)"
                           % (len(ns), len(fl)))
            elif r < lo2:
                bad.append("해석 %d문장에 플로우 %d줄뿐 — 내용이 빠졌다"
                           % (len(ns), len(fl)))
        nums = [n for n in dict.fromkeys(_NUM.findall(body)) if len(n) > 1]
        gone = [n for n in nums if n not in " ".join(fl)]
        if nums and len(gone) > len(nums) / 2:
            bad.append("해석의 수치 %s 가 플로우에 없음 — 시험에 나오는 건 "
                       "그 숫자다 (완성본 84%%가 살린다)" % ", ".join(gone[:4]))
    for name, key_ in (("주제", "topic"), ("요약문", "summary")):
        v = (data.get(key_) or "").strip()
        if not v:
            continue
        lo, hi = SPEC[("topic_len" if key_ == "topic" else "summary_len")]
        if not (lo <= len(v) <= hi):
            bad.append("%s %d자 (규격 %d~%d)" % (name, len(v), lo, hi))
        if not _HAN.search(v):
            bad.append("%s가 한글이 아님" % name)
    sy = data.get("synonyms") or []
    lo, hi = SPEC["syn_cards"]
    if sy and not (lo <= len(sy) <= hi):
        bad.append("동반의어 %d장 (규격 %d~%d)" % (len(sy), lo, hi))
    for c in sy:
        if not c.get("w") or not c.get("ko"):
            bad.append("동반의어에 표제어나 뜻이 빔: %r" % c)
            break
        n = len(c.get("syn") or [])
        if not (SPEC["syn_words"][0] <= n <= SPEC["syn_words"][1]):
            bad.append("`%s` 유의어 %d개 (규격 %d~%d)"
                       % (c["w"], n, *SPEC["syn_words"]))
    return ["[%s] %s" % (key, b) if key else b for b in bad]


def _srcs():
    """`todo` 가 뽑아 둔 해석 — 내용 검사의 잣대."""
    p = os.path.join(AUTHORED, "_todo.json")
    if not os.path.exists(p):
        return {}
    with open(p, encoding="utf-8") as f:
        return {d.get("file") or d["key"]: _plain_tr(d.get("translation"))
                for d in json.load(f)}


def _plain_tr(t):
    if isinstance(t, str):
        return t
    if isinstance(t, list):
        return " ".join(_plain_tr(x) for x in t)
    if isinstance(t, dict):
        return _plain_tr(t.get("t") or t.get("runs") or "")
    return ""


def check_all():
    bad = 0
    src = _srcs()
    for p in sorted(glob.glob(os.path.join(AUTHORED, "*.json"))):
        if os.path.basename(p).startswith("_"):
            continue
        key = os.path.splitext(os.path.basename(p))[0]
        with open(p, encoding="utf-8") as f:
            msgs = check(json.load(f), key, src.get(key, ""))
        for m in msgs:
            print("  ", m)
        bad += bool(msgs)
    n = len(glob.glob(os.path.join(AUTHORED, "*.json")))
    print("저술 %d지문 · 규격 어긋남 %d지문" % (n, bad))
    return bad


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "todo"
    if cmd == "todo":
        todo(sys.argv[2:] or None)
    elif cmd == "check":
        sys.exit(1 if check_all() else 0)
    else:
        print(__doc__)
