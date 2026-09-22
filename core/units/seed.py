"""시드 보태기 — 리포의 `catalog/_units/<kind>.json`(시드)에 **새로 생긴 것만** 라이브(볼륨·로컬 라이브러리)에 더한다.

라이브는 화면에서 고친 정본이라 있는 항목은 손대지 않는다. 더하는 것:
  · 시드에만 있는 항목(id 기준) — 부품·블록·지면·틀·옷·규격·세트
  · 옷: 시드 옷에 있고 라이브 옷에 없는 단락 스타일(styles.{이름}) — 같은 id 옷끼리, 없으면 첫 시드 옷의 것
  · 부품: 같은 id·같은 자리(bind)의 글 원자에 시드가 style 을 달았고 라이브엔 없으면 단다
  · 틀: 시드 틀의 구간(id)이 라이브 틀에 없으면 뒤에 붙인다(정답 구간). 지면 반복 규칙(repeat)이 없으면 once
표준 라이브러리만 쓴다 — deploy/catalog_sync.py 가 기동 때마다 부른다. 리포 = 라이브(로컬)면 아무 일도 없다.

    upgrade(live_dir, seed_dir) → [바뀐 것 설명]
"""
import json
import os

KINDS = ("parts", "blocks", "pages", "specs", "plans", "skins", "sets")


def _load(p):
    try:
        with open(p, encoding="utf-8") as f:
            v = json.load(f)
        return v if isinstance(v, list) else []
    except (OSError, ValueError):
        return []


def _save(p, items):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1)
    os.replace(tmp, p)


def upgrade(live_dir, seed_dir):
    if os.path.abspath(live_dir) == os.path.abspath(seed_dir):
        return []
    os.makedirs(live_dir, exist_ok=True)
    changes = []
    for kind in KINDS:
        sp, lp = os.path.join(seed_dir, kind + ".json"), os.path.join(live_dir, kind + ".json")
        if not os.path.exists(sp):
            continue
        seed = _load(sp)
        if not os.path.exists(lp):
            _save(lp, seed)
            changes.append(f"_units/{kind}.json 통째로")
            continue
        live = _load(lp)
        ids = {x.get("id") for x in live}
        dirty = False
        for x in seed:
            if x.get("id") not in ids:
                live.append(json.loads(json.dumps(x)))
                ids.add(x.get("id"))
                changes.append(f"{kind}/{x.get('id')}")
                dirty = True
        seed_by = {x.get("id"): x for x in seed}
        if kind == "skins":
            first = next((x for x in seed if x.get("styles")), None)
            for sk in live:
                src = seed_by.get(sk.get("id")) or first
                for name, st in ((src or {}).get("styles") or {}).items():
                    if name not in (sk.get("styles") or {}):
                        sk.setdefault("styles", {})[name] = json.loads(json.dumps(st))
                        changes.append(f"skins/{sk.get('id')}.styles.{name}")
                        dirty = True
        elif kind == "parts":
            for pt in live:
                sd = seed_by.get(pt.get("id"))
                if not sd:
                    continue
                styled = {a.get("bind"): a["style"] for a in sd.get("atoms") or [] if a.get("t") == "text" and a.get("style") and a.get("bind")}
                for a in pt.get("atoms") or []:
                    if a.get("t") == "text" and not a.get("style") and a.get("bind") in styled:
                        a["style"] = styled[a["bind"]]
                        changes.append(f"parts/{pt.get('id')}.{a['bind']}.style")
                        dirty = True
        elif kind == "plans":
            for pl in live:
                for sec in pl.get("sections") or []:
                    for pg in sec.get("pages") or []:
                        if "repeat" not in pg:
                            pg["repeat"] = "once"
                            dirty = True
                sd = seed_by.get(pl.get("id"))
                if not sd:
                    continue
                have = {s.get("id") for s in pl.get("sections") or []}
                for sec in sd.get("sections") or []:
                    if sec.get("id") not in have:
                        pl.setdefault("sections", []).append(json.loads(json.dumps(sec)))
                        changes.append(f"plans/{pl.get('id')}.sections.{sec.get('id')}")
                        dirty = True
        if dirty:
            _save(lp, live)
    return changes
