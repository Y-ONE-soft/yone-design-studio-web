# -*- coding: utf-8 -*-
"""카탈로그 + 내지 작업대 단독 실행기 — 통합웹(app.py, 로그인) 없이 로컬에서 띄운다.

    python3 studio_server.py            # http://127.0.0.1:5099/book-studio
    python3 studio_server.py --port 8080
    python3 studio_server.py --host 0.0.0.0   # 같은 네트워크의 다른 기기에서도

원래 리포에서는 `routes/__init__.py` 가 이 blueprint 를 통합웹 Flask 앱에 붙이고
`routes/auth.py` 가 로그인·CSP 를 건다. 여기서는 blueprint 만 그대로 물려 돌린다.

인증은 `core/webauth.py` — **Y.OS 계정(HMAC 링크 토큰)** 으로 검사한다. `YOS_LINK_SECRET` 이
있으면 켜지고(CSP·CORS·보안 헤더도 그때 붙는다), 없으면 로컬처럼 꺼진다. 꺼진 채로
`--host 0.0.0.0` 은 `YONE_AUTH=off` 를 명시해야만 된다.

바깥(contents·core·design·앱)은 `/api/v1` (`routes/api_v1.py`) 을 부른다. 배포는 Fly.io —
`deploy/README.md`, 리포 루트 `Dockerfile`·`fly.toml`.
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
from routes.make import bp as make_bp  # noqa: E402
from routes.units import bp as units_bp  # noqa: E402
from routes import api_v1  # noqa: E402
from routes.analysis_edit import bp as analysis_edit_bp  # noqa: E402
from core import jobs, webauth  # noqa: E402


def create_app():
    app = Flask(__name__, template_folder=os.path.join(REPO, "templates"),
                static_folder=os.path.join(REPO, "static"))
    # 통합웹의 base.html(로그인 머리띠) 대신 단독 실행용 base.html 을 먼저 찾는다.
    # 나머지 템플릿(book_studio·catalog*)은 templates/ 것을 그대로 쓴다.
    from jinja2 import ChoiceLoader, FileSystemLoader
    app.jinja_loader = ChoiceLoader([FileSystemLoader(os.path.join(REPO, "templates_local")),
                                     FileSystemLoader(os.path.join(REPO, "templates"))])
    # 업로드 상한 — 원고 폴더째(docx·pdf 수십 개)가 온다.
    app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("YONE_MAX_UPLOAD_MB", "512")) * 1024 * 1024
    app.json.sort_keys = False          # 단위 JSON 편집기가 id·name 을 앞에 보이게 — 적은 순서 그대로
    # 인증·CORS·보안 헤더 — YOS_LINK_SECRET 이 없으면 꺼짐(로컬 그대로)
    webauth.install(app)
    app.register_blueprint(bp)
    app.register_blueprint(catalog_bp)
    app.register_blueprint(intake_bp)
    app.register_blueprint(books_bp)
    app.register_blueprint(make_bp)
    app.register_blueprint(units_bp)
    app.register_blueprint(analysis_edit_bp)   # 분석본 지면 위 고치기 — contents 분석본 NEW 가 끼워 쓴다
    api_v1.install(app)                 # /api/v1 — contents·core·앱이 부르는 계약
    jobs.mark_lost_on_boot()            # 재시작 전에 돌던 잡은 lost 로

    @app.context_processor
    def _intake_badge():
        # 머리띠 "PDF 판정" 옆 개수 — 판정은 됐는데 결정 안 한 것 + 새 틀 요청
        from routes.catalog import DIR_COLORS
        from routes.intake import new_requests, pending
        try:
            n = len(pending()) + len(new_requests())
        except Exception:
            n = 0
        return {"intake_open": n, "dir_colors": DIR_COLORS}   # dir_colors: base.html 의 폴더 시트 색 고르기

    # 메뉴 = 구성요소 셋(편집기 · 간편 제작 · 관리). 홈은 없다 — 첫 화면은 편집기.
    @app.route("/")
    def home():
        return redirect("/units")

    @app.route("/easy")
    def easy():
        """간편 제작 — 만들어 둔 블록을 단계별로 붙여 만드는 곳. 아직 자리만(준비 중)."""
        from flask import render_template
        return render_template("easy.html", active_nav="간편 제작")

    @app.route("/api/studio/restart", methods=["POST"])
    def restart():
        """새 틀 코드가 main 에 머지된 뒤 서버를 다시 띄운다 — 같은 명령줄로 자기 자신을 다시 실행(exec).
        로컬(인증 꺼짐)에서만. 응답을 보내고 1초 뒤 바꾼다."""
        import threading
        if webauth.mode() != "off":
            return jsonify({"error": "배포 서버에선 못 한다 — fly deploy"}), 400

        def _exec():
            import time
            time.sleep(1)
            os.execv(sys.executable, [sys.executable] + sys.argv)
        threading.Thread(target=_exec, daemon=True).start()
        return jsonify({"ok": True, "note": "2~3초 뒤 새로고침"})

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
        return redirect("/")

    @app.after_request
    def _no_cache(resp):
        # build/ 산출은 렌더마다 덮어써진다 — 브라우저가 옛 지면을 들고 있으면 안 된다
        if resp.mimetype in ("text/html", "text/css", "application/json"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    # 디자인마다 '구성'(기준 PDF 면 묶음)을 미리 계산해 둔다 — 첫 방문이 5~20초 걸리던 것(배포·규칙 바뀐 뒤)을 없앤다.
    # 이미 계산해 둔 것은 캐시라 바로 넘어간다. 서버 기동을 막지 않게 뒤에서.
    import threading
    from routes.catalog import warm_layouts
    threading.Thread(target=warm_layouts, daemon=True, name="warm-layouts").start()
    return app


def main():
    ap = argparse.ArgumentParser(description="내지 작업대 단독 서버")
    ap.add_argument("--host", default=os.environ.get("YONE_STUDIO_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("YONE_STUDIO_PORT", "5099")))
    ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()

    # 인증이 꺼진 채로 바깥에 여는 것은 사고다 — 일부러 그러려면 YONE_AUTH=off 를 적어야 한다.
    if a.host not in ("127.0.0.1", "localhost", "::1") and webauth.mode() == "off" \
            and os.environ.get("YONE_AUTH", "").strip().lower() != "off":
        print(f"✗ --host {a.host} 인데 인증이 꺼져 있다. YOS_LINK_SECRET 을 주거나, "
              "사무실 안에서만 쓸 거면 YONE_AUTH=off 를 명시할 것.")
        sys.exit(2)

    from core.render_vivlio.config import _studio_root
    root = _studio_root()
    print(f"■ 스튜디오 루트: {root}")
    print(f"■ 책 폴더:      {os.path.join(root, '조판', '교재')}")
    print(f"■ 인증:         {webauth.describe()}")
    print(f"■ 카탈로그:     http://{a.host}:{a.port}/catalog")
    print(f"■ 클로드:       {'켜짐 (' + os.environ.get('YONE_ASSIST_MODEL', 'claude-opus-5') + ')' if have_key() else '꺼짐 — ANTHROPIC_API_KEY 없음 (PDF 판정·작업대 클로드 칸 안 됨)'}")
    print(f"■ 책 목록:      http://{a.host}:{a.port}/books")
    print(f"■ 작업대:       http://{a.host}:{a.port}/book-studio")
    app = create_app()
    # threaded: 렌더(subprocess)가 도는 동안에도 정적 자원·썸네일 요청을 받는다
    app.run(host=a.host, port=a.port, debug=a.debug, threaded=True, use_reloader=False)


if __name__ == "__main__":
    main()
