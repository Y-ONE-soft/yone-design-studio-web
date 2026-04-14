import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
JOBS_DIR = os.path.join(BASE_DIR, "jobs")
PORT = 5010
DEBUG = True

# Y.ONE STUDIO 루트 (어느 컴퓨터에서든 자동 감지)
STUDIO_ROOT = os.path.dirname(BASE_DIR)

# 교재 루트 경로
MATERIALS_ROOT = os.path.join(STUDIO_ROOT, "조판", "교재")

# 목업 앱 연동
MOCKUP_IN_DIR = os.path.join(STUDIO_ROOT, "디자인", "목업", "IN")
MOCKUP_URL    = "http://localhost:8501"
