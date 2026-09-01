"""작업대만 눈으로 확인하려고 띄우는 임시 서버 — 인증 없이 5099.

사용자가 쓰는 5010 은 건드리지 않는다(로그인도 하지 않는다).
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault("YONE_SECRET_KEY", "studio-check")

import app as A                                     # noqa: E402

for key in list(A.app.before_request_funcs):
    A.app.before_request_funcs[key] = [
        f for f in A.app.before_request_funcs[key] if f.__name__ != "check_auth"]
A.app.config["TESTING"] = True
A.app.run(host="127.0.0.1", port=5099, debug=False, use_reloader=False,
          threaded=True)
