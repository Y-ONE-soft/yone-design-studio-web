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


def _passage_slots(groups, canon_n):
    """묶음 목록 → **지문 묶음의 자리 번호**. 지문이 아닌 묶음은 None.

    구조로 가른다:
      · 라벨이 있고 그 스텝 안에서 **한 번만** 나오면 지문 묶음이다.
        (`본문` 처럼 두 번 이상 나오는 라벨은 구역 이름이지 지문이 아니다 —
         어법 선택은 `본문·본문·N049…N052` 로 온다: 실측)
      · 라벨이 아예 없어도 **묶음 수가 이 책의 지문 수와 같으면** 순서대로
        지문으로 본다 (빈칸 어휘는 라벨 없이 지문 수만큼 온다: 실측)
      · 그 밖(실전 문제처럼 통째 한 묶음)은 지문 묶음이 아니다 → 항상 남긴다
    """
    labs = [g.get("label") for g in groups]
    seen = {}
    for l in labs:
        if l:
            seen[l] = seen.get(l, 0) + 1
    uniq = [i for i, l in enumerate(labs) if l and seen[l] == 1]
    slots = [None] * len(groups)
    if uniq:
        for k, i in enumerate(uniq, 1):
            slots[i] = k
    elif canon_n and len(groups) == canon_n:
        for i in range(len(groups)):
            slots[i] = i + 1
    return slots


def canonical_passages(steps):
    """이 책의 지문 수와 라벨 — 지문 라벨을 가장 많이 가진 스텝에서."""
    best = []
    for st in steps:
        labs = [g.get("label") for g in st["groups"]]
        seen = {}
        for l in labs:
            if l:
                seen[l] = seen.get(l, 0) + 1
        uniq = [l for l in labs if l and seen[l] == 1]
        if len(uniq) > len(best):
            best = uniq
    return best


def _limit_slots(limit, groups, canon_n):
    """스텝별 개수 제한 → 남길 지문 **순번 집합**. 제한이 없으면 빈 집합.

    `{"passages": 4}`  앞에서 4개          (「문항 수만 줄이기」)
    `{"passages": [1,3]}`  그 순번만
    """
    if not isinstance(limit, dict):
        return set()
    n = limit.get("passages")
    if isinstance(n, bool) or n is None:
        return set()
    if isinstance(n, (list, tuple, set)):
        return set(int(x) for x in n)
    have = [s for s in _passage_slots(groups, canon_n) if s is not None]
    return set(sorted(have)[: max(0, int(n))])


def apply_select(steps, select, log=print):
    """`select` 로 **만들 것만** 남긴다 — 지운 게 아니라 안 만든 것이다.

    passages : 지문 **순번**(1부터). 예 [2,4,6] — 전 스텝 공통
    labels   : 지문 **라벨**로 고르기. 예 ["실전02","실전04"] (순번과 합집합)
    steps    : **넣을** 스텝 키 목록. 예 ["step1_a1","step1_c1","step3"]
    exclude  : **뺄** 스텝 키 목록. 학교 프리셋이 쓰는 자리다 —
               원고에 없는 키를 적어도 그냥 넘어간다(있으면 빼고 없으면 그만).
    include  : `exclude` 를 **이 책에서만 되돌린다**. 「이 학교는 빈칸 어휘를
               빼지만 이 부교재는 넣어주세요」가 여기서 된다.
    order    : 스텝을 놓을 **순서**. 적은 것이 먼저, 안 적은 것은 뒤에
               원래 순서대로. 학교마다 푸는 차례가 다를 수 있다.
    limits   : 스텝마다 남길 지문. {"step1_c2": {"passages": 4}} 는 앞에서 4개,
               {"passages": [1,3]} 은 그 순번만. 전 스텝 공통인 `passages` 와
               달리 **그 스텝에만** 걸린다 (「빈칸 어휘만 문항 수 줄이기」).
    renumber : 남은 지문의 라벨 숫자를 1..N 으로 다시 매김

    지문이 아닌 묶음(어법 선택의 `본문`, 실전 문제 통째)은 **거르지 않는다** —
    지문 단위가 아니기 때문이다.
    """
    select = select or {}
    want_steps = select.get("steps")
    # 뺄 목록 − 되돌린 것 = 실제로 뺄 것. 되돌리기가 이긴다(교재 개별 예외).
    drop_steps = set(select.get("exclude") or []) - set(select.get("include") or [])
    limits = select.get("limits") or {}
    pas = set(select.get("passages") or [])
    labs = set(str(x) for x in (select.get("labels") or []))
    renumber = bool(select.get("renumber"))
    canon = canonical_passages(steps)
    canon_n = len(canon)
    if labs and canon:                       # 라벨 → 순번으로도 환산
        for i, l in enumerate(canon, 1):
            if str(l) in labs:
                pas.add(i)

    out = []
    for st in steps:
        if want_steps and st["key"] not in want_steps:
            log(f"  [선택] 스텝 제외 {st['key']}")
            continue
        if st["key"] in drop_steps:
            log(f"  [선택] 스텝 뺌 {st['key']}")
            continue
        groups = st["groups"]
        # 이 스텝에만 걸리는 개수 제한이 있으면 그것이 전 스텝 공통보다 우선한다
        want = _limit_slots(limits.get(st["key"]), groups, canon_n) or pas
        if want:
            slots = _passage_slots(groups, canon_n)
            keep, dropped = [], 0
            for g, slot in zip(groups, slots):
                if slot is None or slot in want:
                    keep.append(g)
                else:
                    dropped += 1
            if dropped:
                log(f"  [선택] {st['key']}: 지문 {dropped}개 제외 "
                    f"→ {len(keep)}묶음")
            groups = keep
        if renumber:
            slots = _passage_slots(groups, None)
            for g, slot in zip(groups, slots):
                if slot is not None and g.get("label") is not None:
                    g["label"] = _renumbered(g["label"], slot)
        out.append(dict(st, groups=groups))

    # ── 순서 ── 적은 것이 먼저, 안 적은 것은 뒤에 원래 순서대로.
    want_order = [str(x) for x in (select.get("order") or [])]
    if want_order:
        rank = {k: i for i, k in enumerate(want_order)}
        before = [st["key"] for st in out]
        out.sort(key=lambda st: (rank.get(st["key"], len(rank)),
                                 before.index(st["key"])))
        if [st["key"] for st in out] != before:
            log("  [선택] 순서 → " + " · ".join(st["key"] for st in out))
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
                # ⚠ 앞에서부터 짝지으면 **하단 문제가 없는 지문**(수능만만의 '본문'
                #   구역)이 남의 문제를 달고 나온다. 하단은 뒤쪽 지문부터 붙으므로
                #   **뒤에서부터** 짝짓는다(실측).
                lead = max(0, len(st["groups"]) - len(btm))
                for i, g in enumerate(st["groups"]):
                    j = i - lead
                    if 0 <= j < len(btm):
                        g["attach"] = btm[j]["units"]
                log(f"  {k2} → {key} 하단으로 {len(btm)}묶음 "
                    f"(앞 {lead}묶음은 하단 없음)")
        steps.append(st)

    _inherit_labels(steps, log)

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


def _inherit_labels(steps, log=print):
    """라벨이 없는 스텝에 **지문 라벨을 물려준다.**

    실물은 어법 O/X·빈칸 어휘·빈칸 어법 면에도 지문 번호를 찍는다(실측:
    수능만만10강 p42-45·p49-52 = 실전01~04). 그런데 그 스텝들의 렌더 플랜에는
    라벨 단락이 없다 — InDesign 쪽은 지문번호 프레임이 마스터에 따로 있어서
    원고에 없어도 찍힌다.

    규칙(구조): 이 책의 지문 라벨 N개를, 라벨이 하나도 없는 스텝의 **뒤에서
    N개** 묶음에 순서대로 물려준다. 앞쪽 묶음(어법 O/X 의 '본문' 구역 등)은
    지문 단위가 아니므로 비워 둔다 — 없는 것을 지어내지 않는다.
    """
    canon = canonical_passages(steps)
    if not canon:
        return
    n = len(canon)
    for st in steps:
        if any(g.get("label") for g in st["groups"]):
            continue
        g = st["groups"]
        if len(g) < n:
            continue
        for k, grp in enumerate(g[len(g) - n:]):
            grp["label"] = canon[k]
            grp["label_inherited"] = True
        # 앞쪽(지문이 아닌) 묶음은 **묶음 수가 같은 형제 스텝**의 라벨을 그대로
        # 물려받는다 — 실물의 어법 O/X 앞 두 면이 `본문` 인 것이 그 예다.
        lead = len(g) - n
        if lead > 0:
            for sib in steps:
                if sib is st or len(sib["groups"]) != len(g):
                    continue
                src = [x.get("label") for x in sib["groups"][:lead]]
                if all(src):
                    for grp, lab in zip(g[:lead], src):
                        grp["label"] = lab
                        grp["label_inherited"] = True
                    break
        log(f"  [라벨 승계] {st['key']}: 뒤 {n}묶음에 {canon[0]}~{canon[-1]}"
            + (f" · 앞 {lead}묶음 형제 스텝에서" if lead > 0 else ""))



# ── 세로형(사이클 순서) ────────────────────────────────────────────────
# 세로 워크북은 스텝이 아니라 **문제 한 개**가 한 사이클을 차지한다:
# 지문 하나가 P+0~P+9 열 면을 돌고 실전 문제까지 끝난 뒤 다음 지문이 시작한다.
# 지면 짜임·머리말·색은 가로형과 **같다** — 바뀌는 것은 순서뿐이라 데이터에서
# 다시 엮는다(engines/workbook_sero_v2/plan.py 의 _SLOT_STEPS 와 같은 차례).
#
# P+0 만 두 스텝이 한 면에 얹힌다(위=어휘 선택 2단계, 아래=1단계). 그 면의
# 머리말에는 한글 제목이 없다(완성본 실측 — `A1` 만 찍힌다).
CYCLE_PAIR = ("step1_a1_2", "step1_a1")
CYCLE_ORDER = ["step1_a2", "step1_b1", "step1_b2", "step1_c1", "step1_c2",
               "step2_a1", "step2_b1", "step2_c1", "step2_c2", "step3"]


def to_cycles(steps, log=print):
    """스텝 차례 → **사이클 차례**. 지문 하나가 스텝을 다 돌고 다음 지문으로.

    지문 수가 스텝마다 다를 수 있다(하단 문제가 없는 지문 등). 사이클 수는
    **지문이 가장 많은 스텝**에 맞추고, 없는 스텝은 그 사이클에서 건너뛴다 —
    빈 면을 만들지 않기 위해서다.
    """
    by = {st["key"]: st for st in steps}
    n = max((len(st["groups"]) for st in steps), default=0)
    if not n:
        return steps
    # 사이클 수만큼 지문이 없는 스텝(실전 문제는 묶음이 1개다)은 사이클 안에
    # 넣지 않고 **뒤에 한 번** 낸다. 실전 세트와 지문의 대응은 렌더 플랜에
    # 없다 — 짐작으로 쪼개지 않는다(w74 실측: 세트 35개 ↔ 지문 17개).
    tail = [st for st in steps
            if st["key"] not in (CYCLE_PAIR + tuple(CYCLE_ORDER))
            or len(st["groups"]) < n]
    tailk = {id(st) for st in tail}
    out = []
    for i in range(n):
        top, bot = by.get(CYCLE_PAIR[0]), by.get(CYCLE_PAIR[1])
        pair = [g for st in (top, bot)
                if st and i < len(st["groups"]) for g in [st["groups"][i]]]
        if pair:
            meta = dict(by.get(CYCLE_PAIR[1]) or by[CYCLE_PAIR[0]])
            meta["groups"] = pair
            meta["title"] = ""          # 두 단계가 한 면 — 한글 제목 없음(실측)
            meta["cycle"] = i + 1
            out.append(meta)
        for k in CYCLE_ORDER:
            st = by.get(k)
            if not st or id(st) in tailk or i >= len(st["groups"]):
                continue
            one = dict(st)
            one["groups"] = [st["groups"][i]]
            one["cycle"] = i + 1
            out.append(one)
    out += tail
    if tail:
        log("  [세로] 사이클에 못 넣은 스텝 " + ", ".join(t["key"] for t in tail)
            + " — 뒤에 한 번 낸다(지문 대응을 플랜이 안 준다)")
    log(f"  [세로] 사이클 {n}벌 · 면 묶음 {len(out)}개")
    return out


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

    # 세로형 — 스텝 차례를 **사이클 차례**로 다시 엮는다(순서만 바뀐다)
    if (cfg.section("options") or {}).get("order") == "cycle":
        data["steps"] = to_cycles(data["steps"], log)
        data["order"] = "cycle"

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
