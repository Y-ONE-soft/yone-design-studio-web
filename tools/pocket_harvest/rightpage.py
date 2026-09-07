# -*- coding: utf-8 -*-
"""포켓북 **오른쪽 면을 직접 쓴다** — 작업 목록 내보내기 · 저술물 넣기 · 규격 검사.

## 왜

오른쪽 면(플로우노트·한글 주제/요약문·동반의어)은 지금까지 교재팀이 완성
`.indd` 에 직접 타이핑했다. 비블리오로 넘어오면 그 파일이 없으므로, **우리가
쓴다.** 분석본(영어 지문·구문분석·해석)만 교재팀에서 받고 나머지는 여기서 만든다.

## 규격은 완성본이 정한다 (코퍼스 1,368지문 전수 실측)

    플로우노트   줄 수 3~25 (중앙 12, 25~75% 구간 9~14)
                줄 길이 중앙 23자 (75% 31자, 40자 넘으면 두 줄로 끊는다)
                줄머리 비율 — 맨글 34% · `→` 29% · `[표제]` 21% · `-·` 11% · `①` 6%
                자주 쓰는 표제: 결론·예시·그러나·결과·주제·핵심·도입·이유·전환·문제점·실험
    주제        한 줄. 중앙 49자 (25~75% 구간 33~61자)
    요약문      한두 문장. 중앙 158자 (25~75% 구간 112~199자)
    동반의어    중앙 7장 (25~75% 구간 6~8, **최대 9**)
                유의어 중앙 3개 · 반의어 중앙 2개 · **19% 는 반의어 없음**

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
    "flow_len": 44,               # 한 줄 최대 글자
    "topic_len": (18, 80),
    "summary_len": (70, 260),
    "syn_cards": (5, 9),
    "syn_words": (2, 5),          # 유의어 개수
    "ant_words": (0, 5),
}
HEADS = ("도입", "주제", "핵심", "예시", "실험", "연구", "이유", "근거", "대조",
         "그러나", "반면", "전환", "문제", "문제점", "결과", "결론", "인용")
_HAN = re.compile(r"[가-힣]")


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
        for r in json.load(open(f, encoding="utf-8"))["passages"]:
            if r.get("kind") == "memtest":
                continue
            key = r.get("key") or r.get("no") or r.get("label")
            if not key or key in seen:
                continue
            need = [k for k in ("flownote", "topic", "summary", "synonyms")
                    if not r.get(k)]
            if not need:
                continue
            seen.add(key)
            got.append({
                "key": key, "book": tag,
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


def load(key):
    p = os.path.join(AUTHORED, "%s.json" % re.sub(r"[/\\]", "_", key))
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def save(key, data):
    os.makedirs(AUTHORED, exist_ok=True)
    p = os.path.join(AUTHORED, "%s.json" % re.sub(r"[/\\]", "_", key))
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    return p


def check(data, key=""):
    """규격 검사 → 어긋난 것 목록(사람이 읽는 말)."""
    bad = []
    fl = data.get("flownote") or []
    lo, hi = SPEC["flow_lines"]
    if fl and not (lo <= len(fl) <= hi):
        bad.append("플로우 %d줄 (규격 %d~%d)" % (len(fl), lo, hi))
    long = [l for l in fl if len(l) > SPEC["flow_len"]]
    if long:
        bad.append("플로우 %d줄이 %d자 넘음 — 끊어야 함: %r"
                   % (len(long), SPEC["flow_len"], long[0][:30]))
    if fl and not any(re.match(r"^\s*\[", l) for l in fl):
        bad.append("표제 대괄호가 하나도 없음 (완성본은 21%가 표제 줄)")
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


def check_all():
    bad = 0
    for p in sorted(glob.glob(os.path.join(AUTHORED, "*.json"))):
        if os.path.basename(p).startswith("_"):
            continue
        key = os.path.splitext(os.path.basename(p))[0]
        with open(p, encoding="utf-8") as f:
            msgs = check(json.load(f), key)
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
