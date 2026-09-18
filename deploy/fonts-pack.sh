#!/bin/sh
# 카탈로그 디자인이 쓰는 서체만 ~/Library/Fonts 에서 골라 fonts.tgz 로 묶는다 (2026-09 기준 37개 · 137MB).
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
import glob, json, os, re, tarfile
want = {}
for p in glob.glob("catalog/**/config.json", recursive=True) + glob.glob("docs/인계_20260914/책별_설정/**/config.json", recursive=True):
    try: c = json.load(open(p, encoding="utf-8"))
    except Exception: continue
    for f in c.get("fonts") or []:
        fn = f.get("file") if isinstance(f, dict) else f
        if fn: want[fn] = True
for p in glob.glob("core/render_vivlio/series/*/render.py") + glob.glob("core/render_vivlio/series/*/__init__.py"):
    for fn in re.findall(r'"([^"/]+\.(?:otf|ttf|OTF|TTF))"', open(p, encoding="utf-8").read()):
        want[fn] = True
dirs = [os.path.expanduser("~/Library/Fonts"), "/Library/Fonts", "/System/Library/Fonts",
        "/System/Library/Fonts/Supplemental"]          # stage.FONT_DIRS 와 같은 순서 + 맥 보조 서체
found = {}
for f in want:
    for d in dirs:
        if os.path.exists(os.path.join(d, f)):
            found[f] = os.path.join(d, f); break
have, miss = list(found), [f for f in want if f not in found]
with tarfile.open("fonts.tgz", "w:gz") as t:
    for f in sorted(have):
        t.add(found[f], arcname=f)
print(f"fonts.tgz: {len(have)}개, {os.path.getsize('fonts.tgz')/1e6:.0f} MB")
if miss:
    print("⚠ ~/Library/Fonts 에 없어 못 넣은 서체:", ", ".join(miss))
PY
