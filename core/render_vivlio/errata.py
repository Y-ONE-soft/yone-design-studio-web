"""정오표 — 작업대에서 고친 글자가 **원고를 다시 뽑아도 살아남게** 한다.

## 왜 data.json 을 직접 고치면 안 되는가

`data.json` 은 원고에서 만들어진다. 거기 직접 손대면 `bin/viv <책> data` 를 한 번
돌리는 순간 **말없이 되돌아간다** — 고친 사람은 그걸 모른다.

그래서 고친 것은 `<책폴더>/errata.json` 에 따로 쌓고, **data 를 읽는 자리에서**
얹는다. 원고를 다시 뽑아도 정오표는 그대로 얹힌다.

    { "lessons.0.problems.3.stem": "다음 글의 __밑줄 친__ 부분을 …",
      "_note": "작업대에서 고친 것. 원고가 고쳐지면 해당 줄을 지운다." }

## 검수와 어긋나지 않는다

정오표를 **읽는 자리**(`load`)에 얹으므로 조판도 검수도 같은 글을 본다.
계열 게이트가 원고↔PDF 를 대조할 때 쓰는 데이터도 이미 얹힌 것이라 조용히
어긋날 자리가 없다. (중등부 `automation/book.py` 의 `errata` 와 같은 생각이다.)

⚠ 정오표는 **원고가 틀렸을 때의 임시 처방**이다. 교재팀이 원고를 고치면 그 줄을
  지우는 것이 맞다 — 안 지우면 원고와 책이 영영 다른 채로 굳는다.
"""
import json
import os

NAME = "errata.json"


def path(cfg):
    return cfg.path(NAME)


def read(cfg):
    p = path(cfg)
    if not os.path.exists(p):
        return {}
    try:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
    except ValueError:
        return {}
    return {k: v for k, v in d.items() if not k.startswith("_")}


def write(cfg, table, log=None):
    p = path(cfg)
    out = dict(table)
    out["_note"] = ("작업대에서 고친 글. 원고를 다시 뽑아도 얹힌다. "
                    "교재팀이 원고를 고치면 해당 줄을 지울 것.")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, sort_keys=True)
    if log:
        log(f"  정오표 {len(table)}건 → {NAME}")
    return p


# ── 점 경로로 data 안을 오가기 (목록 첨자 포함) ──────────────────
def _walk(data, ref, make=False):
    """`lessons.0.problems.3.stem` → (담고 있는 것, 마지막 열쇠) 또는 (None, None)."""
    cur = data
    parts = ref.split(".")
    for p in parts[:-1]:
        if isinstance(cur, list):
            if not p.isdigit() or int(p) >= len(cur):
                return None, None
            cur = cur[int(p)]
        elif isinstance(cur, dict):
            if p not in cur:
                if not make:
                    return None, None
                cur[p] = {}
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


def apply(data, table, log=None):
    """정오표를 data 에 얹는다. **없는 자리는 조용히 넘기지 않고 알린다.**

    원고가 바뀌어 자리가 사라지면 정오표가 헛돌게 되는데, 조용히 넘기면
    "고쳤는데 왜 안 바뀌지"가 된다.
    """
    hit, miss = 0, []
    for ref, val in (table or {}).items():
        holder, key = _walk(data, ref)
        if holder is None or (isinstance(holder, dict) and key not in holder) \
                or (isinstance(holder, list) and key >= len(holder)):
            miss.append(ref)
            continue
        holder[key] = val
        hit += 1
    if log and hit:
        log(f"  [정오표] {hit}건 얹음")
    if log and miss:
        log(f"  [정오표 경고] 자리를 못 찾은 {len(miss)}건: {', '.join(miss[:4])}"
            f"{' …' if len(miss) > 4 else ''} — 원고가 바뀌었는지 볼 것")
    return data


def load_data(cfg, log=None):
    """`data.json` + 정오표. 모든 계열의 `data.load()` 가 이걸 쓴다."""
    with open(cfg.path("data.json"), encoding="utf-8") as f:
        data = json.load(f)
    table = read(cfg)
    if table:
        apply(data, table, log)
    return data
