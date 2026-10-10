#!/bin/sh
# 시스템 서체(core/units/fonts.system_fonts — 디자인 config·계열 코드 서체 + 편집기에서 올려 등록한 catalog/_fonts)를 fonts.tgz 로 묶는다.
# 상용 서체는 리포·이미지에 넣지 않고 Fly 볼륨(/data/fonts)에만 올린다:
#   deploy/fonts-pack.sh
#   fly ssh sftp put fonts.tgz /data/fonts.tgz
#   fly ssh console -C "sh -c 'tar xzf /data/fonts.tgz -C /data/fonts && rm /data/fonts.tgz && ls /data/fonts | wc -l'"
#
# 서체 목록의 출처 둘: ① 디자인 config 의 `fonts` ② 계열 코드가 직접 적은 `FONTS`
# (core/render_vivlio/series/<계열>/render.py — 워크북·포켓북). ②를 빼먹어 Fly 에서
# 워크북 조판이 "[서체 없음] YeongdoOTF.otf …" 로 죽었다(2026-09-18 실측).
set -e
cd "$(dirname "$0")/.."
python3 - <<'PY'
import os, sys, tarfile
sys.path.insert(0, ".")
from core.units.fonts import system_fonts, missing_pack       # 시스템 서체 — 편집기·PDF·검사와 같은 목록 (묶음 서체 + 올려 등록한 서체)
fs = system_fonts()
with tarfile.open("fonts.tgz", "w:gz") as t:
    for f in sorted(fs, key=lambda f: f["file"]):
        t.add(f["path"], arcname=f["file"])
print(f"fonts.tgz: {len(fs)}개, {os.path.getsize('fonts.tgz')/1e6:.0f} MB")
miss = missing_pack()
if miss:
    print("⚠ 서체 폴더에 없어 못 넣은 서체:", ", ".join(miss))
PY
