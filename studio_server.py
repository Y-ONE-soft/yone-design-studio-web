# -*- coding: utf-8 -*-
"""카탈로그 + 내지 작업대 단독 실행기 — 통합웹(app.py, 로그인) 없이 로컬에서 띄운다.

    python3 studio_server.py            # http://127.0.0.1:5099/book-studio
    python3 studio_server.py --port 8080
    python3 studio_server.py --host 0.0.0.0   # 같은 네트워크의 다른 기기에서도

원래 리포에서는 `routes/__init__.py` 가 이 blueprint 를 통합웹 Flask 앱에 붙이고
`routes/auth.py` 가 로그인·CSP 를 건다. 스냅샷에는 그 껍데기가 없으므로 여기서
blueprint 만 그대로 물려 돌린다. **인증이 없다** — 기본값이 127.0.0.1 인 이유다.

⚠ CSP 를 걸지 않으므로 뷰어 번들의 `eval` 도 그대로 된다. 원래 리포는
  `/book-studio/viewer`·`/frame` 경로에만 `unsafe-eval` 을 허용한다(`auth.py:230`).
  이 서버를 바깥에 노출하려면 그 경계를 다시 세워야 한다.
"""
import argparse
import os
import sys

REPO = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, REPO)

from flask import Flask, jsonify, redirect, request  # noqa: E402

from routes.book_studio import bp  # noqa: E402
from routes.catalog import bp as catalog_bp  # noqa: E402
from routes.intake import bp as intake_bp, have_key  # noqa: E402
from routes.books import bp as books_bp  # noqa: E402


def create_app():
    app = Flask(__name__, template_folder=os.path.join(REPO, "templates"),
                static_folder=os.path.join(REPO, "static"))
    # 통합웹의 base.html(로그인 머리띠) 대신 단독 실행용 base.html 을 먼저 찾는다.
    # 나머지 템플릿(book_studio·catalog*)은 templates/ 것을 그대로 쓴다.
    from jinja2 import ChoiceLoader, FileSystemLoader
    app.jinja_loader = ChoiceLoader([FileSystemLoader(os.path.join(REPO, "templates_local")),
                                     FileSystemLoader(os.path.join(REPO, "templates"))])
    app.register_blueprint(bp)
    app.register_blueprint(catalog_bp)
    app.register_blueprint(intake_bp)
    app.register_blueprint(books_bp)

    @app.route("/")
    def home():
        return redirect("/catalog")

    @app.errorhandler(404)
    def _lost(_e):
        # 주소를 잘못 쳤거나 링크에 글자가 딸려 온 경우(`/book-studio)에서도` 같은 것) —
        # 화면 주소면 작업대로 보낸다. 자원·API 경로(`/book-studio/…`, `/api/…`)는 그대로 404.
        path = request.path
        if path.rstrip("/") == "/book-studio":
            return redirect("/book-studio")
        if path.rstrip("/") == "/catalog":
            return redirect("/catalog")
        if path.startswith("/book-studio/") or path.startswith("/api/"):
            return jsonify({"error": "없는 경로", "path": path}), 404
        return redirect("/book-studio")

    @app.after_request
    def _no_cache(resp):
        # build/ 산출은 렌더마다 덮어써진다 — 브라우저가 옛 지면을 들고 있으면 안 된다
        if resp.mimetype in ("text/html", "text/css", "application/json"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    return app


def main():
    ap = argparse.ArgumentParser(description="내지 작업대 단독 서버")
    ap.add_argument("--host", default=os.environ.get("YONE_STUDIO_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("YONE_STUDIO_PORT", "5099")))
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()

    from core.render_vivlio.config import _studio_root
    root = _studio_root()
    print(f"■ 스튜디오 루트: {root}")
    print(f"■ 책 폴더:      {os.path.join(root, '조판', '교재')}")
    print(f"■ 카탈로그:     http://{a.host}:{a.port}/catalog")
    print(f"■ 클로드:       {'켜짐 (' + os.environ.get('YONE_ASSIST_MODEL', 'claude-opus-5') + ')' if have_key() else '꺼짐 — ANTHROPIC_API_KEY 없음 (PDF 판정·작업대 클로드 칸 안 됨)'}")
    print(f"■ 책 목록:      http://{a.host}:{a.port}/books")
    print(f"■ 작업대:       http://{a.host}:{a.port}/book-studio")
    app = create_app()
    # threaded: 렌더(subprocess)가 도는 동안에도 정적 자원·썸네일 요청을 받는다
    app.run(host=a.host, port=a.port, debug=a.debug, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
