"""기준 쪽과 우리 면을 나란히 놓고 다른 데를 숫자로 — 녹화 전에 여기서 맞춘다.

    python3 tests/e2e/ref_png.py <기준쪽> <우리 지면id> [이름]
기준은 catalog/workbook/designs/d1/reference.pdf (216×303), 우리는 A4(210×297) 라
크기를 맞춰 겹친 뒤 어긋난 화소 비율을 센다.
"""
import os
import subprocess
import sys
import urllib.request

import fitz

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REF = os.path.join(REPO, "catalog", "workbook", "designs", "d1", "reference.pdf")
BASE = os.environ.get("YONE_BASE", "http://127.0.0.1:5099")
pno = int(sys.argv[1])
pid = sys.argv[2]
name = sys.argv[3] if len(sys.argv) > 3 else "cmp"

d = fitz.open(REF)
ref = d[pno - 1].get_pixmap(dpi=110)
ref.save(f"/tmp/{name}_ref.png")

urllib.request.urlretrieve(f"{BASE}/api/units/pdf?page={pid}", f"/tmp/{name}_my.pdf")
my = fitz.open(f"/tmp/{name}_my.pdf")[0].get_pixmap(dpi=110)
my.save(f"/tmp/{name}_my.png")

# 같은 크기로 맞춰 다른 화소를 센다
import PIL.Image as I
a = I.open(f"/tmp/{name}_ref.png").convert("RGB")
b = I.open(f"/tmp/{name}_my.png").convert("RGB").resize(a.size)
import PIL.ImageChops as C
diff = C.difference(a, b).convert("L").point(lambda v: 255 if v > 48 else 0)
bad = sum(diff.histogram()[1:])
tot = a.size[0] * a.size[1]
side = I.new("RGB", (a.size[0] * 2 + 20, a.size[1]), "white")
side.paste(a, (0, 0))
side.paste(b, (a.size[0] + 20, 0))
side.save(f"/tmp/{name}_side.png")
diff.save(f"/tmp/{name}_diff.png")
print(f"다른 화소 {bad * 100.0 / tot:.1f}%  ·  나란히 /tmp/{name}_side.png  ·  차이 /tmp/{name}_diff.png")
