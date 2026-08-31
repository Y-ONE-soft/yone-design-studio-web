"""렌더 플랜(wb-flows-v1) → data.json — 역할 해석 + **범위·스텝 선택**.

입력은 기존 파이프라인이 이미 만드는 `jobs/<id>/render_plan.json` 이다.
원고 파서(`engines/workbook/parser.py`)는 **손대지 않는다** — 두 렌더러(InDesign·
Vivliostyle)가 같은 플랜을 나눠 쓴다.

여기서 하는 일 셋:

  ① 단락 스타일을 **역할**로 바꾼다 (`roles.resolve` — 구조 판정)
  ② 유닛을 **지문 묶음(group)** 으로 나눈다 — 라벨(`[20]`)이 있는 유닛이 묶음의
     시작이고, 라벨 없는 뒤 유닛은 그 묶음의 하단(발문·선지)이다. 스텝마다
     유닛 수가 18/36 으로 다른 이유가 이것이고, 이걸 알아야 "지문 2·4·6번만"이
     성립한다.
  ③ config 의 `select` 로 **만들 것만 남긴다** — 지운 게 아니라 안 만든 것이다.

인식 게이트: 못 알아본 스타일이 하나라도 있으면 조판하지 않고 세운다.
"""
import json
import os
import re
import unicodedata

from core.render_vivlio.series.workbook import roles

FORMAT = "wb-flows-v1"

# 스텝 메타 — 표지 문구·로고·지면 짜임. **데이터다.**
# layout:
#   a1    한 면에 유닛 2개(상·하 고정 프레임)
#   sheet 한 면에 유닛 1개(윗칸만)
#   pair  한 면에 지문 1개 = 상단 유닛 + 하단 유닛
#   flow  자동 흘림(면이 늘어난다)
#   s3    2단 자동 흘림(실전)
STEP_META = {
    "step1_a1":     dict(step=1, tag="FRAME",    logo="A1", title="어휘 선택 1", layout="a1"),
    "step1_a1_2":   dict(step=1, tag="FRAME",    logo="A1", title="어휘 선택 2", layout="a1"),
    "step1_a2":     dict(step=1, tag="FRAME",    logo="A2", title="본문 O/X",   layout="sheet"),
    "step1_b1":     dict(step=1, tag="FRAME",    logo="B1", title="본문 정리",   layout="pair"),
    "step1_b2":     dict(step=1, tag="FRAME",    logo="B2", title="내용 종합",   layout="sheet"),
    "step1_c1":     dict(step=1, tag="FRAME",    logo="C1", title="문장 배열",   layout="pair"),
    "step1_c2":     dict(step=1, tag="FRAME",    logo="C2", title="빈칸 어휘",   layout="sheet"),
    "step2_a1":     dict(step=2, tag="BUILD UP", logo="A1", title="어법 선택",   layout="sheet",
                         bottom_prompt="다음 밑줄 친 부분 중 어법상 틀린 것은?"),
    "step2_a1_btm": dict(step=2, tag="BUILD UP", logo="A1", title="어법 선택",   layout="attach",
                         attach_to="step2_a1"),
    "step2_b1":     dict(step=2, tag="BUILD UP", logo="B1", title="어법 O/X",   layout="sheet",
                         note="각 문장에서 어법상 틀린 곳이 있다면 표시한 후 바르게 수정하세요"),
    "step2_c1":     dict(step=2, tag="BUILD UP", logo="C1", title="빈칸 어법",   layout="sheet"),
    "step2_c2":     dict(step=2, tag="BUILD UP", logo="C2", title="영작 배열",   layout="flow"),
    "step3":        dict(step=3, tag="TEST",     logo="S",  title="실전 문제",   layout="s3"),
    "step3_short":  dict(step=3, tag="TEST",     logo="S",  title="실전 문제",   layout="s3"),
}

STEP_ORDER = list(STEP_META)

# 간지 — 스텝마다 한 벌(앞·뒤 2면)
STEP_MENU = {
    1: [("A1", "어휘 선택"), ("A2", "본문 O/X"), ("B1", "본문 정리"),
        ("B2", "내용 종합"), ("C1", "문장 배열"), ("C2", "빈칸 어휘")],
    2: [("A1", "어법 선택"), ("B1", "어법 O/X"), ("C1", "빈칸 어법"),
        ("C2", "영작 배열")],
    3: [("S", "실전 문제")],
}


def _nfc(s):
    return unicodedata.normalize("NFC", s or "")


def _paras(unit):
    return unit["paras"] if isinstance(unit, dict) else unit


class RecognitionError(Exception):
    pass


# ────────────────────────────────────────────────────────── 유닛 → 블록

def _blocks(unit, unknown, soft):
    """유닛의 단락들을 (역할, 텍스트, runs, 아이콘) 블록으로."""
    out = []
    label = None
    for p in _paras(unit):
        style = p.get("s")
        role = roles.resolve(style)
        if role is None:
            unknown[_nfc(style)] = unknown.get(_nfc(style), 0) + 1
            continue
        if roles.is_soft(style):
            soft[_nfc(style)] = soft.get(_nfc(style), 0) + 1
        text = p.get("t") or ""
        lbl = roles.label_text(text)
        if lbl is not None and label is None and not out:
            # 유닛 머리의 라벨 단락 — 지문 번호다(스타일과 무관하게 모양으로 판정)
            label = lbl
            continue
        icon = p.get("icon") or None
        if not text.strip() and not icon:
            continue                      # 빈 줄은 지면이 만든다
        out.append({
            "role": role,
            "text": text,
            "runs": p.get("runs") or [],
            "icon": (icon or {}).get("label") if icon else None,
        })
    return label, out


def _groups(units, unknown, soft):
    """유닛 목록 → 지문 묶음. 라벨 있는 유닛이 묶음을 연다.

    라벨이 아예 없는 스텝(빈칸 어휘·어법 O/X 등)은 유닛 하나가 곧 묶음이다.
    """
    labelled = _has_own_label(units)      # 이 스텝이 라벨 체계를 쓰는가
    groups = []
    for u in units or []:
        label, blocks = _blocks(u, unknown, soft)
        # 새 묶음을 여는 경우: 첫 유닛 · 라벨이 붙은 유닛 · 라벨 체계가 없는 스텝
        if not groups or label is not None or not labelled:
            groups.append({"label": label, "units": []})
        groups[-1]["units"].append(blocks)
    return groups


def _has_own_label(units):
    for u in units or []:
        for p in _paras(u):
            if roles.label_text(p.get("t") or "") is not None:
                return True
    return False


# ────────────────────────────────────────────────────────── 선택(③④)

_RE_NUM = re.compile(r"\d+")


def _label_num(label):
    m = _RE_NUM.search(label or "")
    return int(m.group()) if m else None


def apply_select(steps, select, log=print):
    """`select` 로 **만들 것만** 남긴다.

    passages : 지문 **순번**(1부터). 예 [2,4,6]
    labels   : 지문 **라벨**로 고르기. 예 ["20","22"] (순번과 함께 쓰면 합집합)
    steps    : 스텝 키 목록. 예 ["step1_a1","step1_c1","step3"]
    renumber : 남은 지문을 1..N 으로 다시 매김(라벨이 숫자일 때만)
    """
    select = select or {}
    want_steps = select.get("steps")
    pas = select.get("passages")
    labs = set(str(x) for x in (select.get("labels") or []))
    renumber = bool(select.get("renumber"))

    out = []
    for st in steps:
        if want_steps and st["key"] not in want_steps:
            log(f"  [선택] 스텝 제외 {st['key']}")
            continue
        groups = st["groups"]
        if pas or labs:
            keep = []
            for i, g in enumerate(groups, 1):
                by_ord = pas and i in pas
                by_lab = labs and str(g.get("label") or "") in labs
                if by_ord or by_lab:
                    keep.append(g)
            if not keep and (pas or labs):
                log(f"  [선택] {st['key']}: 남은 지문 0 — 스텝을 통째로 뺀다")
                continue
            groups = keep
        if renumber:
            for i, g in enumerate(groups, 1):
                if g.get("label") is not None:
                    g["label"] = _renumbered(g["label"], i)
        st = dict(st, groups=groups)
        out.append(st)
    return out


def _renumbered(label, i):
    """라벨의 숫자만 새 순번으로 갈아 끼운다 (`실전03` → `실전01`)."""
    if not _RE_NUM.search(label or ""):
        return label
    width = len(_RE_NUM.search(label).group())
    return _RE_NUM.sub(str(i).zfill(width) if width > 1 else str(i), label, count=1)


# ────────────────────────────────────────────────────────── 조립

def from_plan(plan, cfg=None, log=print):
    if plan.get("format") != FORMAT:
        raise RecognitionError(f"모르는 플랜 형식: {plan.get('format')} (기대 {FORMAT})")
    unknown, soft = {}, {}

    flows = {f["step"]: f for f in plan.get("flows", [])}
    steps = []
    for key in STEP_ORDER:
        if key not in flows:
            continue
        meta = STEP_META[key]
        if meta["layout"] == "attach":
            continue                      # 상위 스텝에 붙는다 (아래에서 처리)
        groups = _groups(flows[key].get("units"), unknown, soft)
        st = dict(meta, key=key, groups=groups)
        # 하단 붙임 스텝(step2_a1_btm)이 있으면 같은 순번끼리 짝지어 넣는다
        for k2, m2 in STEP_META.items():
            if m2["layout"] == "attach" and m2.get("attach_to") == key and k2 in flows:
                btm = _groups(flows[k2].get("units"), unknown, soft)
                for i, g in enumerate(st["groups"]):
                    if i < len(btm):
                        g["attach"] = btm[i]["units"]
                log(f"  {k2} → {key} 하단으로 {len(btm)}묶음")
        steps.append(st)

    if unknown:
        lines = "\n".join(f"    {v:>6}회  {k}" for k, v in
                          sorted(unknown.items(), key=lambda kv: -kv[1]))
        raise RecognitionError(
            "못 알아본 단락 스타일이 있다 — 조판하지 않는다(침묵 유실 방지):\n"
            + lines +
            "\n  → core/render_vivlio/series/workbook/roles.py 의 ROLE_WORDS 에"
            " 역할 어휘를 한 줄 추가할 것")

    book = dict(plan.get("divider") or {})
    data = {"book": book, "steps": steps}
    if soft:
        data["soft_styles"] = soft
        for k, v in soft.items():
            log(f"  [무름] 문장형 스타일 → 안내문으로 봄: {k} ({v}회)")
    return data


def build(cfg, log=print):
    """책 config 의 `manuscript.plan`(렌더 플랜 경로) → data.json."""
    src = cfg.resolve((cfg.section("manuscript") or {}).get("plan"))
    if not src or not os.path.exists(src):
        raise RecognitionError(f"렌더 플랜을 못 찾았다: {src}")
    with open(src, encoding="utf-8") as f:
        plan = json.load(f)
    data = from_plan(plan, cfg, log)

    # 책 표지 문구는 config 가 이긴다(플랜의 divider 는 기본값)
    for k, v in (cfg.book or {}).items():
        if k in ("line1", "line2", "title", "brand"):
            data["book"][k] = v

    sel = cfg.section("select")
    if sel:
        data["steps"] = apply_select(data["steps"], sel, log)
        data["select"] = sel

    data["stats"] = {
        "steps": len(data["steps"]),
        "passages": {s["key"]: len(s["groups"]) for s in data["steps"]},
    }
    out = cfg.path("data.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    tot = sum(data["stats"]["passages"].values())
    log(f"data.json — 스텝 {len(data['steps'])} · 지문묶음 합계 {tot}")
    return out


def load(cfg):
    with open(cfg.path("data.json"), encoding="utf-8") as f:
        return json.load(f)
