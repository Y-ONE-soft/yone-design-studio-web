#!/bin/bash
# SlimBuild.jsx 재생성 — 통합웹 엔진 JSX가 원본(single source of truth).
#
# 왜 필요한가: 수동본과 엔진본을 따로 고치면 두 벌이 갈라진다. 실제로
# 2026-08-17 엔진에만 고친 3건(분할선 적응·실행 순서·멱등 가드)이 수동본에
# 반영되지 않아, 수동 실행이 'isRight is not a function'으로 죽었다.
set -e
cd "$(dirname "$0")"
/usr/bin/python3 "$(dirname "$0")/rebuild_slimbuild.py"
