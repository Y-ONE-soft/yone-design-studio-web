#!/bin/bash
# coord_read 헬퍼 빌드 (재현용).
#
#   bash bin/build_coord_read.sh
#
# 산출: bin/coord_read (리포 추적 — 작아서 OK). 소스는 bin/coord_read.swift.
# Universal(arm64+x86_64) 시도 → 실패하면 네이티브 아치로 폴백.
# swiftc는 /usr/bin/swiftc (Command Line Tools). 실서비스 Python 3.9와 무관.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$HERE/coord_read.swift"
OUT="$HERE/coord_read"

if ! command -v swiftc >/dev/null 2>&1; then
    echo "swiftc 없음 — Xcode Command Line Tools 필요 (xcode-select --install)" >&2
    exit 1
fi

echo "빌드: $SRC → $OUT"
if swiftc -O -target arm64-apple-macos11 -o "$OUT.arm64" "$SRC" 2>/dev/null \
   && swiftc -O -target x86_64-apple-macos11 -o "$OUT.x86_64" "$SRC" 2>/dev/null \
   && lipo -create -output "$OUT" "$OUT.arm64" "$OUT.x86_64" 2>/dev/null; then
    rm -f "$OUT.arm64" "$OUT.x86_64"
    echo "Universal 바이너리 생성 완료"
else
    rm -f "$OUT.arm64" "$OUT.x86_64"
    echo "Universal 실패 → 네이티브 아치로 빌드"
    swiftc -O -o "$OUT" "$SRC"
fi

chmod +x "$OUT"
echo "완료: $OUT"
file "$OUT" || true
