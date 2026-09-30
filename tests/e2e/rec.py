"""화면을 녹화한다 — 헤드리스 크롬 + 단계 목록 → mp4.

사용: python3 rec.py <url> <steps.json> <out.mp4> [W H FPS]
단계: {"say": "자막"} · {"js": "..."} · {"wait": ms} · {"shot": "이름.png"}
자막은 다음 say 까지 남는다. 프레임은 wait 동안 FPS 로 찍는다.
"""
import base64, json, os, subprocess, sys, time, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp import CDP, CHROME                                             # noqa: E402

FFMPEG = os.environ.get("FFMPEG") or ("/opt/homebrew/bin/ffmpeg" if os.path.exists("/opt/homebrew/bin/ffmpeg") else "ffmpeg")
SP = os.environ.get("REC_TMP") or os.path.join(os.path.expanduser("~"), ".cache", "yone-rec")
os.makedirs(SP, exist_ok=True)
PORT = 9466
url, steps_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
W = int(sys.argv[4]) if len(sys.argv) > 4 else 1600
H = int(sys.argv[5]) if len(sys.argv) > 5 else 1000
FPS = int(sys.argv[6]) if len(sys.argv) > 6 else 8
frames = os.path.join(SP, "frames_" + os.path.basename(out).split(".")[0])
subprocess.run(["rm", "-rf", frames], capture_output=True)
os.makedirs(frames, exist_ok=True)

NARR = """(() => { let d = document.querySelector('#narr');
  if (!d) { d = document.createElement('div'); d.id = 'narr'; document.body.appendChild(d);
    const st = document.createElement('style'); st.textContent = `
      #narr { position: fixed; left: 50%; bottom: 46px; transform: translateX(-50%); z-index: 99999;
        background: rgba(20,18,30,.92); color: #fff; font: 600 20px/1.5 -apple-system, "Apple SD Gothic Neo", sans-serif;
        padding: 12px 22px; border-radius: 12px; max-width: 78%; text-align: center; box-shadow: 0 8px 30px rgba(0,0,0,.28);
        opacity: 0; transition: opacity .25s; }
      #narr.on { opacity: 1; }`;
    document.head.appendChild(st); }
  return true; })()"""

subprocess.run(["pkill", "-f", f"remote-debugging-port={PORT}"], capture_output=True)
proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                         f"--remote-debugging-port={PORT}", f"--user-data-dir={SP}/chrome-rec",
                         f"--window-size={W},{H}", "about:blank"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
n = [0]
try:
    for _ in range(80):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1)
            break
        except Exception:
            time.sleep(0.25)
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/json/new?{urllib.parse.quote(url, safe='')}", method="PUT")
    tab = json.load(urllib.request.urlopen(req, timeout=30))
    c = CDP(tab["webSocketDebuggerUrl"])
    time.sleep(3.0)
    c.js(NARR)

    def frame():
        d = c.call("Page.captureScreenshot", format="jpeg", quality=72)
        n[0] += 1
        open(os.path.join(frames, f"{n[0]:05d}.jpg"), "wb").write(base64.b64decode(d["data"]))

    def hold(ms):
        t0 = time.time()
        while (time.time() - t0) * 1000 < ms:
            frame()
            left = ms / 1000 - (time.time() - t0)
            time.sleep(max(0, min(1 / FPS, left)))

    for st in json.load(open(steps_path, encoding="utf-8")):
        if "say" in st:
            c.js("(() => { const d = document.querySelector('#narr'); d.textContent = " + json.dumps(st["say"]) +
                 "; d.classList.add('on'); return true; })()")
            hold(st.get("wait", 1800))
        elif "hide" in st:
            c.js("(() => { document.querySelector('#narr').classList.remove('on'); return true; })()")
            hold(st.get("wait", 400))
        elif "js" in st:
            try:
                v = c.js(st["js"])
                if v not in (None, True):
                    print("  js →", str(v)[:120], flush=True)
            except Exception as e:
                print("  ERR", str(e)[:200], flush=True)
            hold(st.get("wait", 500))
        elif "wait" in st:
            hold(st["wait"])
        elif "shot" in st:
            d = c.call("Page.captureScreenshot", format="png")
            open(os.path.join(SP, st["shot"]), "wb").write(base64.b64decode(d["data"]))
finally:
    proc.terminate()

if n[0] < 2:
    raise SystemExit("프레임이 없다")
subprocess.run([FFMPEG, "-y", "-framerate", str(FPS), "-i", os.path.join(frames, "%05d.jpg"),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                "-movflags", "+faststart", out], capture_output=True)
print(f"{out} · 프레임 {n[0]} · {n[0]/FPS:.0f}초")
