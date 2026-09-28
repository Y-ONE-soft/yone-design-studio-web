"""단위 라이브러리 — `catalog/_units/<kind>.json` 하나에 그 종류 전부(목록).

배포에선 `YONE_CATALOG_DIR`(볼륨)이 정본이고, 리포의 `catalog/_units/` 는 시드다
(`deploy/catalog_sync.py` 가 볼륨에 없는 폴더만 통째로 보탠다).
"""
import json
import os
import re
import threading
import time

from routes.catalog import CATALOG

KINDS = ("parts", "blocks", "pages", "specs", "plans", "skins", "sets", "groups")
_DEF = {"parts": "part", "blocks": "block", "pages": "page", "specs": "spec", "plans": "plan", "skins": "skin", "sets": "set", "groups": "group"}
# 요소 카테고리 — 파일이 아직 없을 때만 이 기본값을 쓴다(배포 볼륨에도 없으니 같은 목록이 나온다).
# 한 번이라도 고치면 파일이 생기고, 그 뒤로는 파일이 정본이다(다 지우면 빈 목록 그대로).
DEFAULT_GROUPS = [
    {"id": "passage", "name": "지문"},
    {"id": "question", "name": "문항"},
    {"id": "drill", "name": "드릴"},
    {"id": "chrome", "name": "머리 · 꼬리 · 간지 · 표지"},
]
_RE_ID = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_SCHEMA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "schema", "units.schema.json")


def udir():
    return os.path.join(CATALOG, "_units")


def _path(kind):
    if kind not in KINDS:
        raise KeyError(kind)
    return os.path.join(udir(), kind + ".json")


_LOCK = threading.RLock()                 # 읽고-고쳐-쓰기는 한 번에 하나 (같이 저장하면 한쪽이 사라진다)


def _read(p):
    """목록 파일 하나 → 목록. 없으면 None. **못 읽으면 예외** — 빈 목록으로 갈음하면 뒤이은 저장이 다 날린다.

    iCloud·구글 드라이브에서 EDEADLK/EAGAIN 이 나므로 몇 번 다시 해 본다(webdata 와 같은 규칙).
    """
    last = None
    for i in range(5):
        try:
            with open(p, encoding="utf-8") as f:
                v = json.load(f)
            return v if isinstance(v, list) else []
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as e:
            last = e
            time.sleep(0.05 * (i + 1))
    raise RuntimeError(f"{os.path.basename(p)} 를 못 읽었다 ({last}) — 덮어쓰지 않는다")


def load(kind):
    v = _read(_path(kind))
    if v is None:
        return [dict(g) for g in DEFAULT_GROUPS] if kind == "groups" else []
    return v


def save(kind, items):
    os.makedirs(udir(), exist_ok=True)
    p = _path(kind)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def library():
    return {k: load(k) for k in KINDS}


def by_id(items):
    return {x.get("id"): x for x in items if isinstance(x, dict) and x.get("id")}


def get(kind, uid):
    return by_id(load(kind)).get(uid)


def norm_page(page):
    """지면 규칙 하나 — **자리는 요소가 갖고 원자는 0,0**.

    분해해서 넣은 지면처럼 절대좌표가 원자에 박혀 있으면 요소로 옮긴다. 안 그러면 「원고 자리가 자라면
    아래를 민다」가 원자 전부를 자란 것으로 보고 지면을 밀어 버린다.
    """
    for it in page.get("items") or []:
        a = it.get("atom")
        if not isinstance(a, dict):
            continue
        if abs(float(it.get("x") or 0)) > 0.001 or abs(float(it.get("y") or 0)) > 0.001:
            continue
        if a.get("t") == "line":
            ax, ay = min(a.get("x1", 0), a.get("x2", 0)), min(a.get("y1", 0), a.get("y2", 0))
        else:
            ax, ay = a.get("x", 0), a.get("y", 0)
        if abs(ax) < 0.001 and abs(ay) < 0.001:
            continue
        it["x"], it["y"] = round(ax, 3), round(ay, 3)
        if a.get("t") == "line":
            for k, d in (("x1", ax), ("x2", ax), ("y1", ay), ("y2", ay)):
                if k in a:
                    a[k] = round(a[k] - d, 3)
        else:
            a["x"], a["y"] = round(a.get("x", 0) - ax, 3), round(a.get("y", 0) - ay, 3)
    return page


def put(kind, item, after=None):
    """같은 id 는 덮어쓴다(자리 유지). 없으면 끝에.

    after 를 주면 그 id 바로 뒤로 옮긴다("" 이면 맨 앞). 목록 순서 = 문서 순서(지면 띠).
    """
    if kind == "pages":
        norm_page(item)
    with _LOCK:
        return _put_locked(kind, item, after)


def _put_locked(kind, item, after):
    items = load(kind)
    for i, x in enumerate(items):
        if x.get("id") == item["id"]:
            items[i] = item
            break
    else:
        items.append(item)
    if after is not None:
        items = [x for x in items if x.get("id") != item["id"]]
        pos = 0 if after == "" else next((i + 1 for i, x in enumerate(items) if x.get("id") == after), len(items))
        items.insert(pos, item)
    save(kind, items)
    return item


def delete(kind, uid):
    with _LOCK:
        items = load(kind)
        rest = [x for x in items if x.get("id") != uid]
        if len(rest) != len(items):
            save(kind, rest)
        return len(rest) != len(items)


_schema_cache = {}


def validate(kind, item):
    """스키마 대조 — 어긋나면 첫 오류 한 줄, 맞으면 None."""
    if kind not in KINDS:
        return f"모르는 종류 {kind}"
    if not isinstance(item, dict):
        return "객체가 아니다"
    sid = str(item.get("id", ""))
    if kind == "sets":
        if not (0 < len(sid) <= 40) or "/" in sid:
            return "세트 id 는 1~40자, / 금지 (지문 번호·회차)"
    elif not _RE_ID.match(sid):
        return "id 는 영문 소문자로 시작, [a-z0-9_] 40자 이내"
    import jsonschema
    if not _schema_cache:
        with open(_SCHEMA, encoding="utf-8") as f:
            _schema_cache["s"] = json.load(f)
    s = _schema_cache["s"]
    sub = {"$ref": "#/definitions/" + _DEF[kind], "definitions": s["definitions"]}
    try:
        jsonschema.validate(item, sub)
    except jsonschema.ValidationError as e:
        where = ".".join(str(p) for p in e.absolute_path) or "(루트)"
        return f"{where}: {e.message}"[:300]
    return None
