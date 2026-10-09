#!/bin/sh
# 대본을 빠르게 돌려 결과를 PDF 그림으로 — 녹화 전에 여기서 틀린 걸 잡는다.
#   tests/e2e/check_page.sh <대본.json> <결과이름>
set -e
PY=/Users/juwoongkim/.pyenv/versions/3.14.3/bin/python3
BASE=${BASE:-http://127.0.0.1:5099}
$PY tests/e2e/rec.py "$BASE/units" tests/e2e/steps/wipe.json /tmp/_w.mp4 800 600 2 >/dev/null 2>&1 || true
REC_FAST=1 $PY tests/e2e/rec.py "$BASE/units" "$1" /tmp/_c.mp4 1500 950 4 2>&1 | grep -E "js →|ERR|!" || true
PG=$(curl -s "$BASE/api/units/library" | $PY -c 'import json,sys; p=json.load(sys.stdin)["pages"]; print(p[-1]["id"] if p else "")')
[ -n "$PG" ] || { echo "지면 없음"; exit 1; }
curl -s "$BASE/api/units/pdf?page=$PG" -o "/tmp/$2.pdf"
$PY -c "import fitz, sys; d=fitz.open('/tmp/$2.pdf'); d[0].get_pixmap(dpi=110).save('/tmp/$2.png'); print('→ /tmp/$2.png')" 2>&1 | grep -v fitz
