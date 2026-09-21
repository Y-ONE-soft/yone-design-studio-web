"""단위 라이브러리 — `catalog/_units/<kind>.json` 하나에 그 종류 전부(목록).

배포에선 `YONE_CATALOG_DIR`(볼륨)이 정본이고, 리포의 `catalog/_units/` 는 시드다
(`deploy/catalog_sync.py` 가 볼륨에 없는 폴더만 통째로 보탠다).
"""
import json
import os
import re

from routes.catalog import CATALOG

KINDS = ("parts", "blocks", "pages", "specs", "plans", "skins", "sets")
_DEF = {"parts": "part", "blocks": "block", "pages": "page", "specs": "spec", "plans": "plan", "skins": "skin", "sets": "set"}
_RE_ID = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_SCHEMA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "schema", "units.schema.json")


def udir():
    return os.path.join(CATALOG, "_units")


def _path(kind):
    if kind not in KINDS:
        raise KeyError(kind)
    return os.path.join(udir(), kind + ".json")


def load(kind):
    try:
        with open(_path(kind), encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, list) else []
    except (OSError, ValueError):
        return []


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


def put(kind, item):
    """같은 id 는 덮어쓴다(자리 유지). 없으면 끝에."""
    items = load(kind)
    for i, x in enumerate(items):
        if x.get("id") == item["id"]:
            items[i] = item
            break
    else:
        items.append(item)
    save(kind, items)
    return item


def delete(kind, uid):
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
