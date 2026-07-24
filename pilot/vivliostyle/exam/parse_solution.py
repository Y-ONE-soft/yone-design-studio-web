"""정답및해설 원고 -> 해설지 문항 IR.

구조 (블록 경계 = 출처 줄):
    [NN년 N월 고N NN번]  정답 ④
    [출제의도] ...
    [해석] ...            (또는 라벨 없는 지문 = 해석)
    [어구] ... / [어휘 및 어구] ...
    [해설] ...
    [선지 해석]
    ① ...  ② ...  ...

섹션 라벨은 '알려진 것'만 헤더로 본다 — 그 외 대괄호(예: 원고 오류로 남은
'[열의]')는 직전 섹션의 내용으로 흡수한다.
"""
import re

RE_SRC_ANS = re.compile(
    r"^\[(\d{2}년\s*\d{1,2}월\s*고\d\s*\d+번)\]\s*정답\s*(.+?)\s*$")
# 섹션 라벨 (순서·표기 고정)
SECTIONS = ["출제의도", "해석", "어구", "어휘 및 어구", "해설", "선지 해석"]
RE_LABEL = re.compile(r"^\s*\[(" + "|".join(map(re.escape, SECTIONS)) + r")\]\s*")


def _norm_src(s):
    return "[" + re.sub(r"\s+", " ", s) + "]"


def parse(paras):
    """rich 단락 -> {'items':[...], 'warnings':[...]}"""
    items, warnings = [], []
    cur = None
    sec = None            # 현재 채우고 있는 섹션 dict
    for p in paras:
        raw = p["text"].strip()
        if not raw:
            continue
        m = RE_SRC_ANS.match(raw)
        if m:                               # 새 블록 시작
            if cur:
                items.append(cur)
            cur = {"src": _norm_src(m.group(1)), "answer": m.group(2).strip(),
                   "sections": []}
            sec = None
            continue
        if cur is None:                     # "정답 및 해설" 표지 등
            continue
        m = RE_LABEL.match(raw)
        if m:
            label = m.group(1)
            body = raw[m.end():].strip()
            sec = {"label": label, "text": body}
            cur["sections"].append(sec)
        elif sec is not None:               # 라벨 없는 이어지는 줄 -> 직전 섹션
            sec["text"] += ("\n" if sec["text"] else "") + raw
        else:                               # 라벨 이전의 지문 = 해석
            sec = {"label": "해석", "text": raw}
            cur["sections"].append(sec)
    if cur:
        items.append(cur)

    # 문항 번호 부여 (문제지와 같은 순서 = 1..N)
    for i, it in enumerate(items, 1):
        it["n"] = i
    return {"items": items, "warnings": warnings}


# 선지 해석 분해: "① ...  ② ...  ..." 한 줄 -> [(label, text)]
RE_CHOICE_SPLIT = re.compile(r"(?=[①-⑤])")


def split_choices(text):
    out = []
    for part in RE_CHOICE_SPLIT.split(text):
        part = part.strip()
        if not part:
            continue
        if part[:1] in "①②③④⑤":
            out.append((part[0], part[1:].strip()))
        elif out:
            out[-1] = (out[-1][0], out[-1][1] + " " + part)
    return out


if __name__ == "__main__":
    import sys
    sys.path.insert(0, ".")
    import hwpx_rich as H
    doc = parse(H.extract(sys.argv[1]))
    print("items", len(doc["items"]))
    for it in doc["items"][:3]:
        print(it["n"], it["src"], "정답", it["answer"],
              "| 섹션", [s["label"] for s in it["sections"]])
