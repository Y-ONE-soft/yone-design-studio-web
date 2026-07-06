"""도메인별 Flask Blueprint 모음 (C2-9) — app.py에서 분리. 라우트 경로/메소드/응답 무변경.

- auth:    로그인/로그아웃 + 앱 전역 인증 훅(before_app_request) + 보안 헤더(after_app_request)
- pages:   인덱스 페이지 (조판/표지/가공) + /typeset/<material_id>
- typeset: 조판 실행 API (/api/run, /api/stream, /api/cancel, /api/result, /download/<job_id>/pdf)
- folders: 엔진별 폴더 탐색/스캔 API + 학교 관리 API
- tools:   워크북 가공 (페이지+API) + 목업 (페이지+API)
- admin:   서버 진단 (/diagnose, /api/health, /api/diagnose, InDesign 시작, /debug) + 원격 채팅 (/chat*)
"""
from routes.auth import bp as auth_bp
from routes.pages import bp as pages_bp
from routes.typeset import bp as typeset_bp
from routes.folders import bp as folders_bp
from routes.tools import bp as tools_bp
from routes.admin import bp as admin_bp

ALL_BLUEPRINTS = [auth_bp, pages_bp, typeset_bp, folders_bp, tools_bp, admin_bp]
