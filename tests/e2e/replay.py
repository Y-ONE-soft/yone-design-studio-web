"""편집기 재현 — 단위 하나를 같은 순서로 돌린다 (초안 v0, 아직 안 돌려 봄).

    python3 tests/e2e/replay.py <단위> check|compare|rec|reset

단위 폴더 tests/e2e/replay/<단위>/ 에 make.py(대본 생성기)와 상태.json({"ref": 기준 PDF, "page": 쪽})이 있어야 한다.
단위마다 데이터 폴더를 따로 써서(YONE_CATALOG_DIR) 지우기·병렬이 그 단위에만 미친다.
절차는 docs/편집기_재현/절차.md.
"""
import json, os, shutil, subprocess, sys, time, urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PY = sys.executable
PORT = int(os.environ.get("REPLAY_PORT") or 5101)
BASE = f"http://127.0.0.1:{PORT}"

unit, cmd = sys.argv[1], sys.argv[2]
udir = os.path.join(REPO, "tests", "e2e", "replay", unit)
data = os.path.expanduser(f"~/.cache/yone-replay/{unit}/catalog")
out = os.path.expanduser(f"~/Downloads/편집기재현/{unit}")
state = json.load(open(os.path.join(udir, "상태.json")))


def fresh_data():
    """카탈로그는 링크로, 편집기 저장 데이터(_units)만 시드에서 새로 복사."""
    shutil.rmtree(os.path.dirname(data), ignore_errors=True)
    os.makedirs(data)
    src = os.path.join(REPO, "catalog")
    for n in os.listdir(src):
        if n != "_units":
            os.symlink(os.path.join(src, n), os.path.join(data, n))
    shutil.copytree(os.path.join(src, "_units"), os.path.join(data, "_units"))


def server():
    env = dict(os.environ, YONE_CATALOG_DIR=data)
    p = subprocess.Popen([PY, "-u", "studio_server.py", "--port", str(PORT)], cwd=REPO, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        try:
            urllib.request.urlopen(BASE + "/api/units/library", timeout=1)
            return p
        except Exception:
            time.sleep(0.5)
    p.kill()
    sys.exit("서버가 안 뜸")


def run_steps(fast, video):
    subprocess.run([PY, os.path.join(udir, "make.py")], check=True)          # → steps.json
    env = dict(os.environ, REC_FAST="1" if fast else "0")
    env.setdefault("REC_SPEED", "4")                                     # 녹화는 확인용 — 빠르게
    subprocess.run([PY, "tests/e2e/rec.py", BASE + "/units", os.path.join(udir, "steps.json"),
                    video, "1600", "1000", "8"], cwd=REPO, env=env, check=True)


def page_pdf():
    lib = json.load(urllib.request.urlopen(BASE + "/api/units/library"))
    pid = lib["pages"][-1]["id"]
    urllib.request.urlretrieve(f"{BASE}/api/units/pdf?page={pid}", os.path.join(out, "result.pdf"))
    return pid


if cmd == "reset":
    shutil.rmtree(os.path.dirname(data), ignore_errors=True)
    shutil.rmtree(out, ignore_errors=True)
    for n in ("steps.json", "보고.md"):
        if os.path.exists(os.path.join(udir, n)):
            os.remove(os.path.join(udir, n))
    print("지움:", unit)
    sys.exit()

os.makedirs(out, exist_ok=True)
fresh_data()
srv = server()
try:
    if cmd in ("check", "compare"):
        run_steps(True, os.path.join(out, "_fast.mp4"))
        pid = page_pdf()
        if cmd == "compare":   # 비교·일치율은 ref_png.py 를 기준 경로·출력 폴더를 받게 고쳐서 부른다 (TODO)
            subprocess.run([PY, "tests/e2e/ref_png.py", str(state["page"]), pid, unit], cwd=REPO,
                           env=dict(os.environ, YONE_BASE=BASE))
    elif cmd == "rec":
        run_steps(False, os.path.join(out, unit + ".mp4"))
        page_pdf()
    print("→", out)
finally:
    srv.kill()
