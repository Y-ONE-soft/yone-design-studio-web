"""편집기 재현 — 단위 하나를 늘 같은 순서로 돌린다. 절차: docs/편집기_재현/절차.md

    python3 tests/e2e/replay.py <단위> check     만들기(녹화 없음) + 원본과 비교 → 일치율
    python3 tests/e2e/replay.py <단위> rec       같은 대본으로 녹화(기본 4배속) + 비교
    python3 tests/e2e/replay.py <단위> reset     그 단위의 데이터·그림·영상 지우기 (make.py 는 남김)

단위 폴더 tests/e2e/replay/<단위>/ 에
  make.py   대본 생성기 — 실행하면 같은 폴더에 steps.json 을 쓴다
  상태.json  {"ref": "catalog/workbook/designs/d1/reference.pdf", "pages": [1, 2]}
             pages = 원본 쪽. 대본이 새로 만든 지면과 차례대로 맞댄다.
단위마다 데이터 폴더를 따로 써서(YONE_CATALOG_DIR) 지우기·병렬이 그 단위에만 미친다.
병렬: REPLAY_PORT(서버, 기본 5101) · REC_PORT(크롬, 기본 9466) 를 세션마다 다르게.
"""
import json, os, shutil, subprocess, sys, time, urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PY = sys.executable
PORT = int(os.environ.get("REPLAY_PORT") or 5101)
BASE = f"http://127.0.0.1:{PORT}"
DPI = 110

unit, cmd = sys.argv[1], sys.argv[2]
udir = os.path.join(REPO, "tests", "e2e", "replay", unit)
data = os.path.expanduser(f"~/.cache/yone-replay/{unit}/catalog")
out = os.path.expanduser(f"~/Downloads/편집기재현/{unit}")


def fresh_data():
    """카탈로그는 리포를 가리키는 링크로, 편집기 저장 데이터(_units)만 리포 시드에서 새로 복사."""
    shutil.rmtree(os.path.dirname(data), ignore_errors=True)
    os.makedirs(data)
    src = os.path.join(REPO, "catalog")
    for n in os.listdir(src):
        if n != "_units":
            os.symlink(os.path.join(src, n), os.path.join(data, n))
    shutil.copytree(os.path.join(src, "_units"), os.path.join(data, "_units"))


def server():
    env = dict(os.environ, YONE_CATALOG_DIR=data, YONE_AUTH="off")
    log = open(os.path.join(out, "server.log"), "w")
    p = subprocess.Popen([PY, "-u", "studio_server.py", "--port", str(PORT)], cwd=REPO, env=env, stdout=log, stderr=log)
    for _ in range(80):
        try:
            urllib.request.urlopen(BASE + "/api/units/library", timeout=1)
            return p
        except Exception:
            time.sleep(0.5)
    p.kill()
    sys.exit(f"서버가 안 뜸 — {out}/server.log")


def page_ids():
    return [p["id"] for p in json.load(urllib.request.urlopen(BASE + "/api/units/library"))["pages"]]


def run_steps(fast, video):
    subprocess.run([PY, os.path.join(udir, "make.py")], check=True)          # → steps.json
    env = dict(os.environ, REC_FAST="1" if fast else "0")
    env.setdefault("REC_SPEED", "4")                                         # 녹화는 확인용 — 빠르게
    r = subprocess.run([PY, "tests/e2e/rec.py", BASE + "/units", os.path.join(udir, "steps.json"),
                        video, "1600", "1000", "8"], cwd=REPO, env=env, capture_output=True, text=True)
    open(os.path.join(out, "rec.log"), "w").write(r.stdout + r.stderr)
    bad = [ln for ln in (r.stdout + r.stderr).splitlines() if "ERR" in ln or "Traceback" in ln or ln.startswith("!")]
    if fast and "프레임이 없다" in r.stdout + r.stderr:                         # 빠른 모드는 프레임을 안 찍는다 — 실패 아님
        r.returncode = 0
    if r.returncode or bad:
        print("대본 실패 —", f"{out}/rec.log")
        print("\n".join(bad[-8:]))
        return False
    return True


def compare(new_ids, state):
    """원본 쪽과 만든 지면을 같은 크기로 겹쳐 같은 화소 비율(%)을 낸다. 나란히·차이 그림을 남긴다."""
    import pymupdf
    from PIL import Image, ImageChops
    ref = pymupdf.open(os.path.join(REPO, state["ref"]))
    rows = []
    for k, rp in enumerate(state["pages"]):
        if k >= len(new_ids):
            rows.append((rp, None))
            continue
        pdf = os.path.join(out, f"p{rp}_my.pdf")
        urllib.request.urlretrieve(f"{BASE}/api/units/pdf?page={new_ids[k]}", pdf)
        ref[rp - 1].get_pixmap(dpi=DPI).save(os.path.join(out, f"p{rp}_ref.png"))
        pymupdf.open(pdf)[0].get_pixmap(dpi=DPI).save(os.path.join(out, f"p{rp}_my.png"))
        a = Image.open(os.path.join(out, f"p{rp}_ref.png")).convert("RGB")
        b = Image.open(os.path.join(out, f"p{rp}_my.png")).convert("RGB").resize(a.size)
        diff = ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v > 48 else 0)
        bad = sum(diff.histogram()[1:])
        side = Image.new("RGB", (a.size[0] * 2 + 20, a.size[1]), "white")
        side.paste(a, (0, 0))
        side.paste(b, (a.size[0] + 20, 0))
        side.save(os.path.join(out, f"p{rp}_side.png"))
        red = Image.new("RGB", a.size, (230, 40, 40))
        Image.composite(red, a.convert("L").convert("RGB"), diff).save(os.path.join(out, f"p{rp}_diff.png"))
        rows.append((rp, 100 * (1 - bad / (a.size[0] * a.size[1]))))
    for rp, pct in rows:
        print(f"  원본 p{rp}: " + ("만든 지면 없음" if pct is None else f"일치 {pct:.1f}%  → p{rp}_side.png · p{rp}_diff.png"))
    return rows


if cmd == "reset":
    shutil.rmtree(os.path.dirname(data), ignore_errors=True)
    shutil.rmtree(out, ignore_errors=True)
    for n in ("steps.json",):
        if os.path.exists(os.path.join(udir, n)):
            os.remove(os.path.join(udir, n))
    print("지움:", unit, "(make.py · 상태.json 은 남김)")
    sys.exit()

state = json.load(open(os.path.join(udir, "상태.json"), encoding="utf-8"))
os.makedirs(out, exist_ok=True)
fresh_data()
srv = server()
try:
    before = set(page_ids())
    t0 = time.time()
    ok = run_steps(cmd != "rec", os.path.join(out, unit + ".mp4") if cmd == "rec" else os.path.join(out, "_fast.mp4"))
    new_ids = [i for i in page_ids() if i not in before]
    print(f"{unit} {cmd} — {time.time() - t0:.0f}초 · 새 지면 {len(new_ids)}개")
    compare(new_ids, state)
    if cmd == "rec" and ok:
        print("  영상:", os.path.join(out, unit + ".mp4"))
    print("→", out)
finally:
    srv.kill()
