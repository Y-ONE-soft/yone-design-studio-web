"""서답형 워크시트 원고(docx) -> 세트 IR.

구조 (지문 1개 = 세트 1개, N-1~N-4):
    <지문 영문>                         (N-1~3 공용)
    N-1 요약 빈칸 발문 / 요약문((A)(B)) / (A)___ (B)___
    N-2 배열 발문 / <보기> ... / ___
    N-3 영작 발문 / → ___
    N-4 어법 발문 / <밑줄 지문 ①~⑤> / 번호:__ → 수정:__

발문 머리 `N-M` 로 하위문항을 자르고, 그 사이 단락을 유형별로 배치한다.
"""
import re

RE_SUBQ = re.compile(r"^\s*(\d+)-(\d+)\s+(.*)$", re.S)
RE_BOGI = re.compile(r"^\s*<\s*보기\s*>\s*", re.S)
RE_ANSLINE = re.compile(r"_{6,}")           # 답란(밑줄 6칸 이상)
RE_UND = re.compile(r"_{2,}")


def _runs_to_blanks(runs):
    """runs 의 언더스코어(2칸+)를 blank run 으로 승격."""
    out = []
    for r in runs:
        t = r.get("t", "")
        last = 0
        for m in RE_UND.finditer(t):
            if m.start() > last:
                nr = dict(r); nr["t"] = t[last:m.start()]; out.append(nr)
            nb = dict(r); nb["t"] = ""; nb["blank"] = True
            nb["blen"] = m.end() - m.start()
            out.append(nb)
            last = m.end()
        if last < len(t):
            nr = dict(r); nr["t"] = t[last:]; out.append(nr)
    return [r for r in out if r.get("t") or r.get("blank")]


def _clean(p):
    return {"text": p["text"], "runs": p.get("runs") or [{"t": p["text"]}]}


def parse(paras):
    """docx 단락 -> {'title','subtitle','sets':[...],'warnings':[]}"""
    title = paras[0]["text"].strip() if paras else ""
    subtitle = paras[1]["text"].strip() if len(paras) > 1 else ""

    # 하위문항 발문 위치
    marks = [(i, RE_SUBQ.match(p["text"].strip()))
             for i, p in enumerate(paras)]
    subq_idx = [(i, int(m.group(1)), int(m.group(2)))
                for i, m in marks if m]

    sets = {}
    order = []
    for k, (i, sn, qn) in enumerate(subq_idx):
        end = subq_idx[k + 1][0] if k + 1 < len(subq_idx) else len(paras)
        block = paras[i + 1:end]
        # 발문 텍스트 (머리 N-M 제거)
        qtext = RE_SUBQ.match(paras[i]["text"].strip()).group(3).strip()

        # 이 세트의 지문: N-1 앞의 bare 영문 단락(직전 빈 줄 위)
        if sn not in sets:
            sets[sn] = {"n": sn, "passage": None, "subs": []}
            order.append(sn)
            # 지문 = i 직전의 비어있지 않은 영문 단락
            j = i - 1
            while j >= 0 and not paras[j]["text"].strip():
                j -= 1
            if j >= 0 and not RE_SUBQ.match(paras[j]["text"].strip()):
                sets[sn]["passage"] = _clean(paras[j])

        sub = {"label": f"{sn}-{qn}", "qn": qn, "question": qtext,
               "boxes": [], "passage": None, "summary": None,
               "answer_lines": []}
        for p in block:
            t = p["text"].strip()
            if not t:
                continue
            if RE_ANSLINE.fullmatch(t.replace(" ", "")) or \
                    re.match(r"^(\(A\)|→|번호\s*:)", t):
                sub["answer_lines"].append(_clean(p))
            elif RE_BOGI.match(t):
                sub["boxes"].append(_clean(p))
            elif qn == 4 and any(c in t for c in "①②③④⑤"):
                sub["passage"] = _clean(p)      # 어법 밑줄 지문
            elif qn == 1 and "(A)" in t and "(B)" in t:
                sub["summary"] = _clean(p)       # 요약문
            else:
                # 요약문/보기 뒤에 이어지는 줄
                (sub["summary"] and sub["summary"]["text"].__class__)  # no-op
                sub.setdefault("extra", []).append(_clean(p))
        sets[sn]["subs"].append(sub)

    out = [sets[n] for n in order]
    return {"title": title, "subtitle": subtitle, "sets": out, "warnings": []}


# --- blank/underline helpers exposed for renderer ---
def blankify(clean_para):
    return _runs_to_blanks(clean_para["runs"])
