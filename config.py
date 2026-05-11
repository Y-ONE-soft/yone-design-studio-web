import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOBS_DIR = os.path.join(BASE_DIR, "jobs")
PORT = 5010
DEBUG = True

# Y.ONE STUDIO 루트
#   환경변수 YONE_STUDIO_ROOT가 있으면 그걸 사용 (각 컴퓨터별 데이터 폴더 위치 다른 경우 대응).
#   없으면 통합웹사이트의 상위 폴더를 기본값으로 사용 (기존 동작 유지).
STUDIO_ROOT = os.environ.get("YONE_STUDIO_ROOT", os.path.dirname(BASE_DIR))

# 교재 루트 경로
MATERIALS_ROOT = os.path.join(STUDIO_ROOT, "조판", "교재")

# 목업 앱 연동
MOCKUP_IN_DIR = os.path.join(STUDIO_ROOT, "디자인", "목업", "IN")
MOCKUP_URL    = "http://localhost:8501"
