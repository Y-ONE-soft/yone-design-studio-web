#!/usr/bin/env python3
"""리포의 카탈로그(이미지의 /app/catalog.seed) → 볼륨(/data/catalog)에 **새것만** 보탠다.

볼륨이 정본이다(화면에서 디렉토리를 옮기고 디자인을 등록한다). 그래서 덮어쓰지 않고:
  · 볼륨에 없는 틀(catalog.json 의 키)          → 항목을 더한다
  · 볼륨에 없는 디렉토리(dirs.json 의 id)        → 기타 앞에 더한다
  · 볼륨에 없는 디자인 폴더(<틀>/designs/<id>/)  → 폴더째 복사한다
  · 볼륨에 없는 틀 폴더                          → 폴더째 복사한다
  · 디자인 단위 시드(_units/<kind>.json) → 없는 파일은 복사, 있는 파일엔 새 항목·스타일·구간만 보탠다(core/units/seed.py)
이미 있는 파일은 손대지 않는다 — 리포에서 디자인을 고쳤으면(overrides.css 등) 화면의
「디자인 등록」이나 fly ssh 로 따로 옮긴다.

사용: catalog_sync.py <seed_dir> <volume_dir>   (entrypoint 가 기동 때마다 부른다)
"""
import json
import os
import shutil
import sys


def _load(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def main(seed, vol):
    added_series, added_designs = [], []

    # ① catalog.json — 없는 틀 항목만
    sc, vc = _load(os.path.join(seed, "catalog.json")), _load(os.path.join(vol, "catalog.json"))
    if isinstance(sc, dict) and isinstance(vc, dict):
        new = {k: v for k, v in sc.items() if k not in vc}
        if new:
            vc.update(new)
            with open(os.path.join(vol, "catalog.json"), "w", encoding="utf-8") as f:
                json.dump(vc, f, ensure_ascii=False, indent=2)
            added_series += list(new)

    # ①-2 dirs.json — 없는 디렉토리(관리 화면의 폴더)만, 기타(etc) 앞에. 화면에서 고친 폴더는 그대로
    sd, vd = _load(os.path.join(seed, "dirs.json")), _load(os.path.join(vol, "dirs.json"))
    if isinstance(sd, list) and isinstance(vd, list):
        have = {d.get("id") for d in vd}
        new = [d for d in sd if d.get("id") not in have]
        if new:
            at = next((i for i, d in enumerate(vd) if d.get("id") == "etc"), len(vd))
            vd[at:at] = new
            with open(os.path.join(vol, "dirs.json"), "w", encoding="utf-8") as f:
                json.dump(vd, f, ensure_ascii=False, indent=2)
            added_series += [f"폴더 {d.get('id')}" for d in new]

    # ② 틀 폴더 · 디자인 폴더 — 없는 것만 통째로
    for series in sorted(os.listdir(seed)):
        sdir = os.path.join(seed, series)
        if not os.path.isdir(sdir) or series.startswith("_"):
            continue
        vdir = os.path.join(vol, series)
        if not os.path.isdir(vdir):
            shutil.copytree(sdir, vdir)
            added_designs += [f"{series}/*"]
            continue
        sdes, vdes = os.path.join(sdir, "designs"), os.path.join(vdir, "designs")
        if not os.path.isdir(sdes):
            continue
        os.makedirs(vdes, exist_ok=True)
        for d in sorted(os.listdir(sdes)):
            if os.path.isdir(os.path.join(sdes, d)) and not os.path.exists(os.path.join(vdes, d)):
                shutil.copytree(os.path.join(sdes, d), os.path.join(vdes, d))
                added_designs.append(f"{series}/{d}")

    # ③ 디자인 단위 시드(_units/<kind>.json) — 없는 파일은 통째로, 있는 파일엔 **새로 생긴 항목·스타일·구간만** 보탠다
    #    (core/units/seed.py). 화면에서 고친 항목은 그대로.
    su, vu = os.path.join(seed, "_units"), os.path.join(vol, "_units")
    if os.path.isdir(su):
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from core.units.seed import upgrade
        added_designs.extend(upgrade(vu, su))

    if added_series or added_designs:
        print("■ 카탈로그 보탬 — 틀:", ", ".join(added_series) or "-", "· 디자인:", ", ".join(added_designs) or "-")
    else:
        print("■ 카탈로그 — 리포에 새 틀·디자인 없음(볼륨 그대로)")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("사용: catalog_sync.py <seed_dir> <volume_dir>")
    main(sys.argv[1], sys.argv[2])
