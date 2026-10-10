"""문서 묶음 — 편집기 문서 하나를 파일 하나로(인디자인 패키지처럼).

묶음 = {"kind": "yone-units-doc", "v": 1, "plan", "pages", "parts", "blocks", "skin", "specs", "images"}
- 문서가 쓰는 쪽·부품·블록·브랜드(문서 브랜드, 없으면 base)·판형과 브랜드 그림(base64)을 다 담는다.
- 가져올 때는 쪽·부품·블록 id 를 새로 매겨 이 편집기에 이미 있는 것과 안 겹친다(참조도 같이 바꾼다).
  「이 문서 끝에」로 가져오면 쪽을 그 문서 끝에 붙인다 — 글 잇기 이야기 이름이 겹치면 뒤에 번호를 붙인다.
  브랜드는 같은 id 가 있으면 없는 스타일·견본·그림만 보탠다(있는 값은 안 바꾼다 — 바뀌면 그 문서 모양이 바뀐다).
쓰는 곳: 편집기 문서 패널 「문서 파일로 내보내기 / 가져오기」, 관리 등록(디자인 폴더의 units.json).
"""
import base64
import copy
import os
import secrets

from core.units import content, store

KIND = "yone-units-doc"
REF_KEYS = ("part", "block")


def _walk(o, fn):
    """dict·list 를 끝까지 돌며 (dict, key, value) 마다 fn"""
    if isinstance(o, dict):
        for k, v in list(o.items()):
            fn(o, k, v)
            _walk(v, fn)
    elif isinstance(o, list):
        for v in o:
            _walk(v, fn)


def _refs(objs, key):
    out = set()
    _walk(objs, lambda d, k, v: out.add(v) if k == key and isinstance(v, str) else None)
    return out


def export(lib, plan_id):
    plans = store.by_id(lib["plans"])
    plan = plans.get(plan_id)
    if not plan:
        raise KeyError(plan_id)
    pages_by = store.by_id(lib["pages"])
    pages = [pages_by[i] for i in dict.fromkeys(content.plan_page_ids(plan)) if i in pages_by]
    blocks_by, parts_by = store.by_id(lib["blocks"]), store.by_id(lib["parts"])
    blocks = [blocks_by[b] for b in sorted(_refs(pages, "block")) if b in blocks_by]
    want, parts = _refs([pages, blocks], "part"), {}
    while want:                                                          # 부품 안 부품(글 끝에 붙인 부품 등)까지
        pid = want.pop()
        if pid in parts or pid not in parts_by:
            continue
        parts[pid] = parts_by[pid]
        want |= _refs(parts_by[pid], "part") - set(parts)
    skins = store.by_id(lib["skins"])
    skin = skins.get(plan.get("skin") or "") or skins.get("base") or {}
    specs_by = store.by_id(lib["specs"])
    spec_ids = {plan.get("spec") or "a4"} | {p.get("spec") for p in pages if p.get("spec")}
    images = {}
    for key, rel in (skin.get("images") or {}).items():
        path = rel if os.path.isabs(rel) else os.path.join(store.udir(), rel)
        try:
            with open(path, "rb") as fh:
                images[key] = {"name": os.path.basename(rel), "b64": base64.b64encode(fh.read()).decode()}
        except OSError:
            pass
    from core.units import fonts as _fonts                              # 이 편집기에 올려 등록한 서체 중 문서가 쓰는 것 — 다른 편집기(서버)에도 같이 간다
    used = set()
    _walk([pages, list(parts.values()), skin], lambda d, k, v: used.add(v) if k == "font" and isinstance(v, str) and not v.startswith("$") else None)
    used |= {v for v in ((skin.get("tokens") or {}).get("font") or {}).values() if isinstance(v, str)}
    fonts_b64 = {}
    for f in _fonts.system_fonts():
        if f["src"] == "upload" and f["family"] in used:
            with open(f["path"], "rb") as fh:
                fonts_b64[f["file"]] = base64.b64encode(fh.read()).decode()
    return {"kind": KIND, "v": 1, "plan": plan, "pages": pages, "parts": list(parts.values()), "blocks": blocks,
            "skin": skin, "specs": [specs_by[s] for s in spec_ids if s in specs_by], "images": images, "fonts": fonts_b64}


def _new_id(prefix, taken):
    while True:
        nid = f"{prefix}_{secrets.token_hex(4)}"
        if nid not in taken:
            taken.add(nid)
            return nid


def load(pkg, into=None, name=None):
    """묶음을 이 편집기에 넣는다 → (문서 id, 보고). into = 붙일 문서 id(없으면 새 문서). 저장까지 한다."""
    if not isinstance(pkg, dict) or pkg.get("kind") != KIND:
        raise ValueError("문서 묶음 파일이 아니다(kind: yone-units-doc)")
    lib = store.library()
    pkg = copy.deepcopy(pkg)
    taken = {x.get("id") for k in ("pages", "parts", "blocks", "plans") for x in lib[k]}
    pmap = {p["id"]: _new_id("page", taken) for p in pkg.get("pages") or []}
    rmap = {"part": {p["id"]: _new_id("part", taken) for p in pkg.get("parts") or []},
            "block": {b["id"]: _new_id("block", taken) for b in pkg.get("blocks") or []}}

    def fix(d, k, v):
        if k in REF_KEYS and isinstance(v, str) and v in rmap[k]:
            d[k] = rmap[k][v]
    target = store.by_id(lib["plans"]).get(into) if into else None
    if into and not target:
        raise KeyError(into)
    used_stories = set()
    if target:
        pages_by = store.by_id(lib["pages"])
        used_stories = {(it.get("atom") or {}).get("story") for i in content.plan_page_ids(target) for it in (pages_by.get(i) or {}).get("items") or []}
        used_stories.discard(None)
    renames = {}
    for s in sorted({(it.get("atom") or {}).get("story") for p in pkg.get("pages") or [] for it in p.get("items") or []} - {None}):
        if s in used_stories:
            n = 2
            while f"{s} ({n})" in used_stories:
                n += 1
            renames[s] = f"{s} ({n})"
            used_stories.add(renames[s])
    for kind in ("parts", "blocks"):
        for x in pkg.get(kind) or []:
            x["id"] = rmap[kind[:-1]][x["id"]]
            _walk(x, fix)
            err = store.validate(kind, x)
            if err:
                raise ValueError(f"{kind} {x['id']}: {err}")
    for p in pkg.get("pages") or []:
        p["id"] = pmap[p["id"]]
        if p.get("cont") in pmap:
            p["cont"] = pmap[p["cont"]]
        else:
            p.pop("cont", None)
        for it in p.get("items") or []:
            a = it.get("atom") or {}
            if a.get("story") in renames:
                a["story"] = renames[a["story"]]
        _walk(p, fix)
        err = store.validate("pages", p)
        if err:
            raise ValueError(f"쪽 {p['id']}: {err}")
    # 브랜드 — 없으면 그대로, 있으면 빈 칸만 채운다
    skin, added = pkg.get("skin") or {}, []
    if skin.get("id"):
        have = store.by_id(lib["skins"]).get(skin["id"])
        img_dir = os.path.join(store.udir(), "_img")
        for key, im in (pkg.get("images") or {}).items():
            os.makedirs(img_dir, exist_ok=True)
            path = os.path.join(img_dir, os.path.basename(im.get("name") or key))
            if not os.path.exists(path):
                with open(path, "wb") as fh:
                    fh.write(base64.b64decode(im.get("b64") or ""))
        if not have:
            store.put("skins", skin)
        else:
            merged = copy.deepcopy(have)
            for sec in ("styles", "images"):
                for k, v in (skin.get(sec) or {}).items():
                    if k not in (merged.get(sec) or {}):
                        merged.setdefault(sec, {})[k] = v
                        added.append(f"{sec}.{k}")
            for grp, vals in (skin.get("tokens") or {}).items():
                for k, v in (vals or {}).items():
                    if k not in ((merged.get("tokens") or {}).get(grp) or {}):
                        merged.setdefault("tokens", {}).setdefault(grp, {})[k] = v
                        added.append(f"tokens.{grp}.{k}")
            if added:
                store.put("skins", merged)
    if pkg.get("fonts"):                                                # 문서가 쓰는 올린 서체 — 이 편집기에 없으면 등록
        from core.units import fonts as _fonts
        have = {f["file"] for f in _fonts.system_fonts()}
        for fn, b64 in pkg["fonts"].items():
            if fn not in have:
                _fonts.register(fn, base64.b64decode(b64))
    specs_by = store.by_id(lib["specs"])
    for sp in pkg.get("specs") or []:
        if sp.get("id") and sp["id"] not in specs_by:
            store.put("specs", sp)
    for kind in ("parts", "blocks", "pages"):
        for x in pkg.get(kind) or []:
            store.put(kind, x)
    src = pkg.get("plan") or {}
    ids = [pmap[i] for i in content.plan_page_ids(src) if i in pmap]
    if target:
        sec = (target.get("sections") or [{"id": "s1", "name": "본문", "pages": []}])
        target["sections"] = sec
        rep = {e["page"] if isinstance(e, dict) else e: e for s in src.get("sections") or [] for e in s.get("pages") or []}
        inv = {v: k for k, v in pmap.items()}
        for i in ids:
            e = rep.get(inv[i])
            sec[-1].setdefault("pages", []).append(dict(e, page=i) if isinstance(e, dict) else {"page": i, "repeat": "once"})
        plan = target
    else:
        plan = copy.deepcopy(src)
        plan["id"] = _new_id("plan", taken)
        if name:
            plan["name"] = name

        def remap_ids(lst):
            return [pmap[i] for i in lst or [] if i in pmap]
        plan["front"], plan["back"] = remap_ids(plan.get("front")), remap_ids(plan.get("back"))
        for s in plan.get("sections") or []:
            if s.get("divider") in pmap:
                s["divider"] = pmap[s["divider"]]
            s["pages"] = [dict(e, page=pmap[e["page"]]) if isinstance(e, dict) else {"page": pmap[e], "repeat": "once"}
                          for e in s.get("pages") or [] if (e["page"] if isinstance(e, dict) else e) in pmap]
        if skin.get("id") and skin["id"] != "base":
            plan["skin"] = skin["id"]
    err = store.validate("plans", plan)
    if err:
        raise ValueError(f"문서: {err}")
    store.put("plans", plan)
    return plan["id"], {"pages": len(ids), "parts": len(pkg.get("parts") or []), "blocks": len(pkg.get("blocks") or []),
                        "stories_renamed": renames, "skin_added": added, "into": bool(target)}
