"""편집 이력 — 고친 것을 **연산 목록**으로 쌓고, 되돌릴 수 있게 한다.

## 왜 값 표가 아니라 연산 목록인가

앞서 쓰던 정오표(`errata.json`)는 `이 자리 = 이 값` 만 담았다. 글자 하나 고치는
데는 충분하지만 **문단 나누기·합치기·삭제·순서 바꾸기를 담을 수 없다.** 그리고
결정적으로 **되돌릴 수가 없다** — 무엇을 고쳤는지는 남아도 *고치기 전이 무엇이었는지*
가 없기 때문이다. 조판 프로그램에서 실행 취소가 없는 건 못 쓴다는 뜻이다.

그래서 고친 것을 **일어난 순서대로** 쌓고, 읽을 때 그 순서대로 얹는다.
되돌리기는 "마지막 연산을 빼고 다시 얹기" 다.

    <책폴더>/edits.json
    { "head": 3,                       # 여기까지 적용. 되돌리면 줄어든다
      "ops": [ {"op":"set", "ref":"lessons.0.problems.3.stem", "v":…, "at":…}, … ] }

`head` 뒤의 연산은 **지우지 않고 남겨 둔다** — 그게 '다시 실행'이다. 새로 고치면
그때 잘라낸다(편집기가 다 그렇게 한다).

## 연산

    set     그 자리 값을 바꾼다                 ref, v
    split   그 자리 글을 두 단락으로 나눈다      ref, at(글자 위치)
    merge   그 자리와 다음 항목을 합친다         ref
    insert  그 자리 **앞에** 새 항목을 넣는다    ref, v
    delete  그 자리 항목을 지운다                ref

`ref` 는 `lessons.0.problems.3.blocks.0.paras.2` 꼴의 점 경로다(`refs.py` 가 지면에
심는 자리표와 같은 말). 목록 항목을 넣고 빼는 연산은 **뒤 항목의 번호를 밀기**
때문에, 얹기는 언제나 처음부터 순서대로 다시 한다(중간 상태를 캐시하지 않는다).

## 검수와 어긋나지 않는다

`data` 를 **읽는 자리**에서 얹으므로 조판도 검수도 같은 글을 본다.

⚠ 편집은 원고가 틀렸을 때의 임시 처방이다. 교재팀이 원고를 고치면 그 연산을
  지우는 것이 맞다 — 안 지우면 원고와 책이 영영 다른 채로 굳는다.
"""
import copy
import datetime
import json
import os

NAME = "edits.json"
OLD = "errata.json"          # 예전 값 표 — 처음 읽을 때 연산으로 옮긴다
# 글 연산 — `data` 를 읽을 때 얹는다
TEXT_OPS = ("set", "split", "merge", "insert", "delete")
# 디자인 연산 — **파일을 직접** 고친다(`design_ops.py`). data 에는 안 얹는다.
DESIGN_OPS = ("style", "knob", "css")
OPS = TEXT_OPS + DESIGN_OPS


def path(cfg):
    return cfg.path(NAME)


# ── 점 경로로 오가기 ────────────────────────────────────────────
def _walk(data, ref):
    """`…paras.2` → (담고 있는 것, 마지막 열쇠). 못 찾으면 (None, None)."""
    cur = data
    parts = ref.split(".")
    for p in parts[:-1]:
        if isinstance(cur, list):
            if not p.isdigit() or int(p) >= len(cur):
                return None, None
            cur = cur[int(p)]
        elif isinstance(cur, dict):
            if p not in cur:
                return None, None
            cur = cur[p]
        else:
            return None, None
    last = parts[-1]
    if isinstance(cur, list):
        if not last.isdigit() or int(last) >= len(cur):
            return None, None
        return cur, int(last)
    if isinstance(cur, dict):
        return cur, last
    return None, None


def get(data, ref, default=None):
    holder, key = _walk(data, ref)
    if holder is None:
        return default
    try:
        return holder[key]
    except (KeyError, IndexError):
        return default


def exists(data, ref):
    _MISS = object()
    return get(data, ref, _MISS) is not _MISS


# ── 연산 하나 얹기 ──────────────────────────────────────────────
def _plain(v):
    from core.render_vivlio import richtext as rt
    return rt.plain(v)


def apply_op(data, op, log=None):
    """연산 하나. 얹었으면 True. 자리를 못 찾으면 **조용히 넘기지 않고** 알린다."""
    kind, ref = op.get("op"), op.get("ref") or ""
    holder, key = _walk(data, ref)
    bad = (holder is None
           or (isinstance(holder, dict) and key not in holder)
           or (isinstance(holder, list) and key >= len(holder)))
    if bad and kind != "insert":
        if log:
            log(f"  [편집 경고] 자리를 못 찾음: {ref} ({kind}) — 원고가 바뀌었는가")
        return False
    if kind == "set":
        holder[key] = op.get("v")
    elif kind == "delete":
        if not isinstance(holder, list):
            if log:
                log(f"  [편집 경고] 목록이 아니라 지울 수 없다: {ref}")
            return False
        holder.pop(key)
    elif kind == "insert":
        holder2, key2 = _walk(data, ref) if not bad else (holder, key)
        if holder2 is None or not isinstance(holder2, list):
            # 목록 끝에 붙이는 경우 — 부모 목록을 다시 찾는다
            parent, idx = _parent_list(data, ref)
            if parent is None:
                if log:
                    log(f"  [편집 경고] 넣을 자리가 없다: {ref}")
                return False
            parent.insert(min(idx, len(parent)), op.get("v"))
            return True
        holder2.insert(key2, op.get("v"))
    elif kind == "split":
        if not isinstance(holder, list):
            if log:
                log(f"  [편집 경고] 목록이 아니라 나눌 수 없다: {ref}")
            return False
        text = _plain(holder[key])
        at = max(0, min(int(op.get("at") or 0), len(text)))
        holder[key] = text[:at].rstrip()
        holder.insert(key + 1, text[at:].lstrip())
    elif kind == "merge":
        if not isinstance(holder, list) or key + 1 >= len(holder):
            if log:
                log(f"  [편집 경고] 합칠 다음 항목이 없다: {ref}")
            return False
        holder[key] = (_plain(holder[key]).rstrip() + " "
                       + _plain(holder[key + 1]).lstrip())
        holder.pop(key + 1)
    else:
        if log:
            log(f"  [편집 경고] 모르는 연산: {kind}")
        return False
    return True


def _parent_list(data, ref):
    """`…paras.7` 에서 `paras` 목록과 7 을 돌려준다(끝에 붙일 때 쓴다)."""
    head, _, last = ref.rpartition(".")
    if not last.isdigit():
        return None, 0
    lst = get(data, head)
    return (lst, int(last)) if isinstance(lst, list) else (None, 0)


# ── 파일 읽고 쓰기 ──────────────────────────────────────────────
def _migrate_old(cfg):
    """예전 `errata.json`(값 표) → 연산 목록. 한 번만."""
    p = cfg.path(OLD)
    if not os.path.exists(p):
        return []
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
    except ValueError:
        return []
    return [{"op": "set", "ref": k, "v": v, "at": "", "note": "errata.json 에서"}
            for k, v in d.items() if not k.startswith("_")]


def read(cfg):
    p = path(cfg)
    if not os.path.exists(p):
        ops = _migrate_old(cfg)
        return {"head": len(ops), "ops": ops}
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
    except ValueError:
        return {"head": 0, "ops": []}
    ops = [o for o in (d.get("ops") or []) if o.get("op") in OPS]
    head = d.get("head")
    head = len(ops) if head is None else max(0, min(int(head), len(ops)))
    return {"head": head, "ops": ops}


def write(cfg, state, log=None):
    p = path(cfg)
    out = dict(state)
    out["_note"] = ("작업대에서 고친 것. 일어난 순서대로 쌓이고 `head` 까지 적용된다. "
                    "원고를 다시 뽑아도 얹힌다. 교재팀이 원고를 고치면 그 줄을 지울 것.")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    if log:
        log(f"  편집 {state['head']}/{len(state['ops'])}건 → {NAME}")
    # 예전 표는 옮겨 담았으니 치운다(두 곳에 있으면 어느 쪽이 참인지 모른다)
    old = cfg.path(OLD)
    if os.path.exists(old):
        os.replace(old, old + ".bak")
    return p


def push(cfg, op, log=None):
    """새 연산. **되돌린 뒤 새로 고치면 앞으로 갈 것은 잘라 낸다**(편집기 관례).

    디자인 연산이면 고치기 전 값을 `prev` 로 담고 **파일에 바로 얹는다.**
    """
    from core.render_vivlio import design_ops as dops
    st = read(cfg)
    op = dict(op)
    op.setdefault("at", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    if op.get("op") in DESIGN_OPS:
        op.setdefault("prev", dops.current(cfg, op))
        dops.apply(cfg, op)
    st["ops"] = st["ops"][:st["head"]] + [op]
    st["head"] = len(st["ops"])
    write(cfg, st, log)
    return st


def undo(cfg, n=1, log=None):
    """되돌리기. 디자인 연산은 **파일을 도로 쓴다**(글은 읽을 때 안 얹으면 끝)."""
    from core.render_vivlio import design_ops as dops
    st = read(cfg)
    for _ in range(n):
        if st["head"] <= 0:
            break
        op = st["ops"][st["head"] - 1]
        if op.get("op") in DESIGN_OPS:
            dops.revert(cfg, op)
        st["head"] -= 1
    write(cfg, st, log)
    return st


def redo(cfg, n=1, log=None):
    from core.render_vivlio import design_ops as dops
    st = read(cfg)
    for _ in range(n):
        if st["head"] >= len(st["ops"]):
            break
        op = st["ops"][st["head"]]
        if op.get("op") in DESIGN_OPS:
            dops.apply(cfg, op)
        st["head"] += 1
    write(cfg, st, log)
    return st


def apply_all(data, state, log=None):
    """`head` 까지 순서대로. 목록을 넣고 빼면 뒤 번호가 밀리므로 늘 처음부터.

    ⚠ 디자인 연산은 **건너뛴다** — 그건 이미 `config.json`·`overrides.css` 에
      들어가 있다. 여기서 또 얹으면 두 번 먹는다.
    """
    ok = 0
    for op in (state.get("ops") or [])[:state.get("head", 0)]:
        if op.get("op") in DESIGN_OPS:
            continue
        if apply_op(data, op, log):
            ok += 1
    if log and ok:
        log(f"  [편집] {ok}건 얹음")
    return data


def load_data(cfg, log=None):
    """`data.json` + 편집 이력. 모든 계열의 `data.load()` 가 이걸 쓴다."""
    with open(cfg.path("data.json"), encoding="utf-8") as f:
        data = json.load(f)
    st = read(cfg)
    if st["head"]:
        apply_all(data, st, log)
    return data


def preview(cfg, state=None):
    """이력을 얹은 data 사본 — 편집기가 '지금 값'을 물을 때."""
    with open(cfg.path("data.json"), encoding="utf-8") as f:
        raw = json.load(f)
    return apply_all(copy.deepcopy(raw), state or read(cfg)), raw
