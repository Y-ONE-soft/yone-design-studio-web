"""다시 그려 재기 — 화면 조작(대본)은 다시 하지 않고, replay.py 가 남긴 편집기 데이터를 지금 코드로 다시 그려 원본과 맞댄다.
그리기(render.py · units_compose.js · pdf.py)만 고쳤을 때 단위 전체를 몇 분 안에 다시 확인한다. 대본·편집기 화면을 고쳤으면 replay.py check.

    python3 tests/e2e/rerender.py <단위> [<단위> …]
"""
import json, os, subprocess, sys, tempfile, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, REPO)
sys.path.insert(0, HERE)
import pagecmp                                                                  # noqa: E402
from core.units import content                                                 # noqa: E402

PY = sys.executable
PORT = int(os.environ.get("RERENDER_PORT") or 5160)
BASE = f"http://127.0.0.1:{PORT}"


def one(unit):
    data = os.path.expanduser(f"~/.cache/yone-replay/{unit}/catalog")
    out = os.path.expanduser(f"~/Downloads/편집기재현/{unit}")
    udir = os.path.join(HERE, "replay", unit)
    state = json.load(open(os.path.join(udir, "상태.json"), encoding="utf-8"))
    elems = json.load(open(os.path.join(udir, "elems.json"), encoding="utf-8"))
    plans = json.load(open(os.path.join(data, "_units", "plans.json"), encoding="utf-8"))
    plan = next((p for p in plans if p.get("content")), plans[0] if plans else None)
    ids = content.plan_page_ids(plan) if plan else []
    if not ids:                                                                 # 문서 없이 만든 단위 — 저장된 지면 순서
        ids = [p["id"] for p in json.load(open(os.path.join(data, "_units", "pages.json"), encoding="utf-8"))]
    env = dict(os.environ, YONE_CATALOG_DIR=data, YONE_AUTH="off")
    log = open(os.path.join(tempfile.gettempdir(), f"rerender_{PORT}.log"), "w")
    srv = subprocess.Popen([PY, "-u", "studio_server.py", "--port", str(PORT)], cwd=REPO, env=env, stdout=log, stderr=log)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(BASE + "/api/v1/health", timeout=2)
                break
            except Exception:
                time.sleep(0.5)
        fill = "&fill=auto" if state.get("fill") else ""
        n = bad = 0
        lines = []
        for k, rp in enumerate(state["pages"]):
            if k >= len(ids) or str(k + 1) not in elems:
                continue
            pdf = os.path.join(out, f"p{rp}_my.pdf")
            urllib.request.urlretrieve(f"{BASE}/api/units/pdf?page={ids[k]}{fill}", pdf)
            res = pagecmp.measure(os.path.join(REPO, state["ref"]), rp, pdf, elems[str(k + 1)])
            n += len(res)
            for r in res:
                if not r["ok"]:
                    bad += 1
                    sh = f" · 잉크 {r['ink']:.2f} 겹침 {r['iou']:.2f}" if r.get("ink") is not None else ""
                    lines.append(f"  ✗ p{rp} {r['id']:10s} " + (f"dx {r['dx']:+.2f} dy {r['dy']:+.2f} dw {r['dw']:+.2f} dh {r['dh']:+.2f}{sh}" if r.get("my") and r.get("ref") else "못 찾음"))
        print(f"{unit}: {n - bad}/{n}")
        if lines:
            print("\n".join(lines))
    finally:
        srv.kill()


for u in sys.argv[1:]:
    one(u)
