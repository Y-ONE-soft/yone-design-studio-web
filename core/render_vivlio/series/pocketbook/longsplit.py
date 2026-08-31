# -*- coding: utf-8 -*-
"""한 지면에 못 담는 긴 지문을 여러 지문으로 나눈다.

포켓북 지문 상자는 115×127mm 다. 9pt/24pt 로 조판하면 약 1,050자, 행간을 하한
(14pt)까지 줄여도 **약 1,900자**가 한계다. 그런데 분석본에는 3,700자짜리 지문이
있다(배재2 26-2 `The Subscription Economy`). 그대로 두면 상자 밖으로 밀려
**글자가 통째로 사라진다** — G-P7 이 잡은 결함이 정확히 이것이다.

완성본은 이런 지문을 `본문7-1` · `본문7-2` 처럼 **나눠서** 싣는다. 여기서도 같은
방식으로 나눈다. 자르는 자리는 **문단 경계**가 첫째, 없으면 문장 경계다 —
낱말 한가운데서 자르면 구문분석 주석이 어느 쪽에 붙을지 알 수 없게 된다.

번역도 같은 비율로 나눈다. 번역은 문장 수가 지문과 다를 수 있어 글자 수 비율로
자르되 문장 경계에서만 끊는다.
"""
import re

# 행간 하한(14pt)에서 상자에 들어가는 글자 수. 실측에서 얻었다
# (1,431자가 24pt 로 161.7mm → 14pt 환산 94.3mm, 상자 127mm → 약 1,900자).
CAPACITY = 1850

_SENT = re.compile(r"(?<=[.!?])\s+")


def _text(runs):
    return "".join(r.get("t", "") for r in runs)


def _cut_runs(runs, at):
    """런 흐름을 글자 위치 `at` 에서 자른다. 런 안이면 그 런을 쪼갠다."""
    head, tail, seen = [], [], 0
    for r in runs:
        t = r.get("t", "")
        if seen >= at:
            tail.append(r)
        elif seen + len(t) <= at:
            head.append(r)
            seen += len(t)
        else:
            k = at - seen
            if k:
                head.append(dict(r, t=t[:k]))
            if t[k:]:
                tail.append(dict(r, t=t[k:]))
            seen = at
    return head, tail


def _boundaries(paras):
    """문단 경계의 글자 위치. 문단이 하나뿐이면 문장 경계."""
    pos, at = [], 0
    for p in paras:
        at += len(_text(p["runs"]))
        pos.append(at)
    if len(pos) > 1:
        return pos[:-1]
    text = _text(paras[0]["runs"]) if paras else ""
    out, k = [], 0
    for piece in _SENT.split(text):
        k += len(piece)
        out.append(k)
        k += 1
    return out[:-1]


def split_passage(p, capacity=CAPACITY):
    """긴 지문 → [지문 조각]. 나눌 필요가 없으면 원본 하나만 돌려준다."""
    paras = p.get("passage") or []
    runs = [r for pa in paras for r in pa["runs"]]
    total = len(_text(runs))
    if total <= capacity:
        return [p]
    n = (total + capacity - 1) // capacity
    bounds = _boundaries(paras)
    targets = [total * i // n for i in range(1, n)]
    cuts = []
    for t in targets:
        near = min(bounds, key=lambda b: abs(b - t)) if bounds else t
        if near not in cuts and 0 < near < total:
            cuts.append(near)
    cuts.sort()
    if not cuts:
        return [p]

    tr_runs = [r for pa in (p.get("translation") or []) for r in pa["runs"]]
    tr_total = len(_text(tr_runs))

    parts, rest, tr_rest, prev = [], runs, tr_runs, 0
    for i, c in enumerate(cuts + [total]):
        head, rest = _cut_runs(rest, c - prev)
        tr_at = int(round(tr_total * (c / float(total)))) if tr_total else 0
        tr_head, tr_rest = _cut_runs(tr_rest, max(0, tr_at - int(round(
            tr_total * (prev / float(total)))))) if tr_total else ([], [])
        q = dict(p)
        q["passage"] = [{"style": "본문", "runs": head}]
        q["translation"] = [{"style": "한글", "runs": tr_head}] if tr_head else None
        base = p.get("label") or p.get("pno") or ""
        q["label"] = "%s-%d" % (base, i + 1) if base else ""
        if i:                       # 뒤 조각은 오른쪽 면을 되풀이하지 않는다
            q["flownote"] = []
            q["synonyms"] = []
            q["topic"] = ""
            q["summary"] = ""
            q["links"] = []
        q["part"] = (i + 1, len(cuts) + 1)
        parts.append(q)
        prev = c
    return parts


def split_all(items, capacity=CAPACITY, log=None):
    out, n = [], 0
    for it in items:
        if it.get("kind") == "memtest" or not it.get("passage"):
            out.append(it)
            continue
        got = split_passage(it, capacity)
        if len(got) > 1:
            n += 1
            if log:
                log("  [긴 지문 분할] %s → %d조각 (%d자)"
                    % (it.get("label") or it.get("pno"), len(got),
                       len("".join(r.get("t", "") for pa in it["passage"]
                                   for r in pa["runs"]))))
        out += got
    return out
