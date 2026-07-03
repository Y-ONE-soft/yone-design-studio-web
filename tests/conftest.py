import os
import sys

# 리포지토리 루트를 import 경로에 추가 (config, core, engines)
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)
