"""화면을 녹화한다 — 헤드리스 크롬에 **진짜 마우스·키보드**를 넣고 프레임을 모아 mp4.

사용: python3 tests/e2e/rec.py <url> <steps.json> <out.mp4> [W H FPS]

단계 (모두 실제 입력이다 — js 는 되도록 쓰지 않는다):
  {"say": "자막", "wait": ms}          자막 (다음 say 까지 남는다)
  {"move": 자리}                        마우스 옮기기
  {"click": 자리, "shift": true}        누르기(시프트 = 더 고르기) · {"dbl": 자리} 두 번
  {"drag": {"from": 자리, "to": 자리}}   끌기
  {"draw": {"tool": "rect", "from": …, "to": …}}  도구 고르고 그리기(확인·재시도)
  {"type": "글"}                        키보드로 치기   · {"key": "Enter"} 키
  {"fill": {"at": "#sel", "value": "216"}}  칸을 눌러 다 지우고 쳐 넣기
  {"write": {"at": {"mm": [30, 20]}, "value": "A1"}}  지면의 글상자를 두 번 눌러 글 치기
  {"pick": {"at": 자리, "value": "wb216"}}  select 을 눌러 키보드로 고르기
  {"clickif": {"at": "#tg-side", "when": "!view.side"}}   조건이 맞을 때만 누르기
  {"answer": "이름"}                     다음에 뜨는 묻는 창에 칠 글 — 창을 여는 누르기는 그다음 단계에서
  {"wait": ms} · {"shot": "이름.png"} · {"js": "…"}(마지막 수단)

자리: "#sel" (그 요소 가운데) · [x, y] (화면 픽셀) · {"mm": [x, y]} (지면 좌표)
커서는 화면에 점으로 그려 준다 — 헤드리스는 진짜 커서가 안 찍힌다.
"""
import base64, json, math, os, shutil, subprocess, sys, time, urllib.parse, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp import CDP, CHROME                                             # noqa: E402

FFMPEG = os.environ.get("FFMPEG") or ("/opt/homebrew/bin/ffmpeg" if os.path.exists("/opt/homebrew/bin/ffmpeg") else "ffmpeg")
SP = os.environ.get("REC_TMP") or os.path.join(os.path.expanduser("~"), ".cache", "yone-rec")
os.makedirs(SP, exist_ok=True)
PORT = int(os.environ.get("REC_PORT") or 9466)
url, steps_path, out = sys.argv[1], sys.argv[2], sys.argv[3]
W = int(sys.argv[4]) if len(sys.argv) > 4 else 1600
H = int(sys.argv[5]) if len(sys.argv) > 5 else 1000
FPS = int(sys.argv[6]) if len(sys.argv) > 6 else 8
FAST = os.environ.get("REC_FAST") == "1"        # 빠른 모드 — 기다리지 않고 프레임도 안 찍는다 (대본 검사용)
SPEED = float(os.environ.get("REC_SPEED", "2"))  # 녹화 배율 — 2 면 기다림·타이핑이 절반 (영상도 절반 길이)
frames = os.path.join(SP, "frames_" + os.path.basename(out).split(".")[0])
subprocess.run(["rm", "-rf", frames], capture_output=True)
os.makedirs(frames, exist_ok=True)

CHROME_SETUP = """(() => {
  if (document.querySelector('#cur')) return true;
  const st = document.createElement('style'); st.textContent = `
    #cur { position: fixed; z-index: 99999; width: 18px; height: 18px; margin: -9px 0 0 -9px; border-radius: 50%;
      background: rgba(125,42,232,.28); border: 2px solid #7d2ae8; pointer-events: none; transition: left .06s linear, top .06s linear; }
    #cur.down { background: rgba(125,42,232,.6); transform: scale(.7); }
    #narr { position: fixed; left: 50%; bottom: 46px; transform: translateX(-50%); z-index: 99998;
      background: rgba(20,18,30,.92); color: #fff; font: 600 20px/1.5 -apple-system, "Apple SD Gothic Neo", sans-serif;
      padding: 12px 22px; border-radius: 12px; max-width: 78%; text-align: center; box-shadow: 0 8px 30px rgba(0,0,0,.28);
      opacity: 0; transition: opacity .25s; pointer-events: none; }   /* 자막이 아래 쪽 줄(＋ 쪽 단추)을 가려 눌리지 않던 것 — 쪽 8개부터 */
    #narr.on { opacity: 1; }`;
  document.head.appendChild(st);
  const c = document.createElement('div'); c.id = 'cur'; c.style.left = '-50px'; c.style.top = '-50px'; document.body.appendChild(c);
  const n = document.createElement('div'); n.id = 'narr'; document.body.appendChild(n);
  window.__cur = (x, y, down) => { const e = document.querySelector('#cur'); e.style.left = x + 'px'; e.style.top = y + 'px'; e.classList.toggle('down', !!down); };
  return true; })()"""

subprocess.run(["pkill", "-f", f"remote-debugging-port={PORT}"], capture_output=True)
time.sleep(1.5)                                      # 앞 크롬이 프로필을 놓을 때까지
PROF = f"{SP}/chrome-rec-{PORT}-{int(time.time())}"  # 프로필은 실행마다 새로 — 잠금 충돌 방지
proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
                         f"--remote-debugging-port={PORT}", f"--user-data-dir={PROF}",
                         f"--window-size={W},{H}", "about:blank"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
n = [0]
pos = [W / 2, H / 2]
try:
    for _ in range(80):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1)
            break
        except Exception:
            time.sleep(0.25 / SPEED)
    req = urllib.request.Request(f"http://127.0.0.1:{PORT}/json/new?{urllib.parse.quote(url, safe='')}", method="PUT")
    tab = json.load(urllib.request.urlopen(req, timeout=30))
    c = CDP(tab["webSocketDebuggerUrl"])
    c.call("Page.enable")                                    # 묻는 창(prompt)을 받아 답을 친다 — {"answer": "…"} (cdp.CDP.call)
    time.sleep(3.0)
    c.js(CHROME_SETUP)

    fc = [0]

    def frame(force=False):
        if FAST:
            return
        fc[0] += 1
        if not force and SPEED > 1 and fc[0] % int(round(SPEED)) != 0:
            return                                  # 배속 — 동작 프레임을 솎는다
        d = c.call("Page.captureScreenshot", format="jpeg", quality=72)
        n[0] += 1
        open(os.path.join(frames, f"{n[0]:05d}.jpg"), "wb").write(base64.b64decode(d["data"]))

    def hold(ms):
        ms = ms / SPEED
        if FAST:
            time.sleep(min(ms, 300) / 1000.0)      # 화면이 따라올 최소한만
            return
        t0 = time.time()
        while (time.time() - t0) * 1000 < ms:
            frame(True)
            left = ms / 1000 - (time.time() - t0)
            time.sleep(max(0, min(1 / FPS, left)))

    def at(spot):
        """자리 → 화면 픽셀."""
        if isinstance(spot, (list, tuple)):
            return float(spot[0]), float(spot[1])
        if isinstance(spot, dict) and "mm" in spot:
            r = c.js("(() => { const p = document.querySelector('#paper'); const b = p.getBoundingClientRect(); return [b.left, b.top, scale]; })()")
            return r[0] + spot["mm"][0] * r[2], r[1] + spot["mm"][1] * r[2]
        r = c.js("(() => { const e = document.querySelector(" + json.dumps(spot) + "); if (!e) return null; "
                  "let d = e.closest('details'); while (d) { d.open = true; d = d.parentElement && d.parentElement.closest('details'); } "   # 접힌 칸은 펴고 쓴다
                  "e.scrollIntoView({block:'center'}); const b = e.getBoundingClientRect(); return [b.left + b.width/2, b.top + b.height/2]; })()")
        if not r:
            raise RuntimeError(f"못 찾음 {spot}")
        return float(r[0]), float(r[1])

    def cursor(x, y, down=False):
        c.js(f"__cur({x:.0f},{y:.0f},{'true' if down else 'false'})")

    def move(x, y, steps=12, shoot=True):
        x0, y0 = pos
        for i in range(1, steps + 1):
            cx, cy = x0 + (x - x0) * i / steps, y0 + (y - y0) * i / steps
            c.call("Input.dispatchMouseEvent", type="mouseMoved", x=cx, y=cy, button="none", clickCount=0)
            cursor(cx, cy)
            if shoot and i % max(1, steps // 6) == 0:
                frame()
        pos[0], pos[1] = x, y

    def press(x, y, count=1):
        c.call("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=count, buttons=1)
        cursor(x, y, True)
        frame()

    def release(x, y, count=1):
        c.call("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=count, buttons=0)
        cursor(x, y, False)
        frame()

    def click(spot, count=1, mod=0):
        x, y = at(spot)
        move(x, y)
        if mod:
            c.call("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=count, buttons=1, modifiers=mod)
            cursor(x, y, True); frame()
            c.call("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=count, buttons=0, modifiers=mod)
            cursor(x, y, False); frame()
            return
        press(x, y, count)
        release(x, y, count)
        if count == 2:
            press(x, y, 2); release(x, y, 2)

    def drag(a, b, steps=16):
        x0, y0 = at(a)
        x1, y1 = at(b)
        move(x0, y0)
        press(x0, y0)
        for i in range(1, steps + 1):
            cx, cy = x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps
            c.call("Input.dispatchMouseEvent", type="mouseMoved", x=cx, y=cy, button="left", buttons=1, clickCount=0)
            cursor(cx, cy, True)
            if i % 3 == 0:
                frame()
        release(x1, y1)
        pos[0], pos[1] = x1, y1

    def typetext(t, per=0.035):
        per = per / SPEED
        for ch in t:
            if ch == " ":                                # 줄 나눔 — Shift+Enter 를 진짜로 누른다
                key("Enter", shift=True)
                continue
            c.call("Input.insertText", text=ch)
            if len(t) < 40 or ord(ch) % 3 == 0:
                frame()
            time.sleep(per)
        frame()

    def key(name, shift=False):
        codes = {"Enter": (13, "Enter"), "Escape": (27, "Escape"), "Tab": (9, "Tab"),
                 "ArrowDown": (40, "ArrowDown"), "ArrowUp": (38, "ArrowUp")}
        code, k = codes.get(name, (0, name))
        mod = 8 if shift else 0
        c.call("Input.dispatchKeyEvent", type="rawKeyDown", windowsVirtualKeyCode=code, key=k, code=k, modifiers=mod)
        c.call("Input.dispatchKeyEvent", type="keyUp", windowsVirtualKeyCode=code, key=k, code=k, modifiers=mod)
        frame()

    def wipe(times=14):
        """칸 안의 글을 지운다 — 백스페이스·딜리트를 사람처럼 눌러서. 횟수는 속도와 무관(덜 지우면 글이 섞인다)."""
        for _ in range(times):
            for t in ("rawKeyDown", "keyUp"):
                c.call("Input.dispatchKeyEvent", type=t, windowsVirtualKeyCode=8, key="Backspace", code="Backspace")
            for t in ("rawKeyDown", "keyUp"):
                c.call("Input.dispatchKeyEvent", type=t, windowsVirtualKeyCode=46, key="Delete", code="Delete")
        frame()

    def fill_in(spot, value):
        """칸을 눌러 고르고, 다 지우고, 쳐 넣고, 확정 — 사람이 하는 그대로."""
        for tryn in range(2):
            click(spot, 2)
            n = c.js("(() => { const e = document.querySelector(" + json.dumps(spot) + "); return e ? String(e.value).length : 0; })()") if isinstance(spot, str) else 0
            wipe(max(14, (n or 0) + 2))
            typetext(str(value))
            key("Enter")                                 # 칸은 Enter 로 확정된다
            time.sleep(0.25 / SPEED)
            frame()
            got = c.js("(() => { const e = document.querySelector(" + json.dumps(spot) + "); return e ? String(e.value) : null; })()")
            same = str(got).strip() == str(value).strip()
            try:
                same = same or abs(float(got) - float(value)) < 0.01       # 98 과 98.0 은 같다
            except (TypeError, ValueError):
                pass
            if got is None or same:
                return
        print(f"  ! {spot} 에 {value} 대신 {got}", flush=True)

    def pick(spot, value):
        """select 을 눌러 고른다 — 헤드리스는 목록이 안 그려지므로 누른 뒤 값을 넣는다(누르는 건 진짜)."""
        click(spot)
        sel = spot if isinstance(spot, str) else None
        ok = c.js("(() => { const e = document.querySelector(" + json.dumps(sel) + "); if (!e) return false; "
                  "e.value = " + json.dumps(value) + "; e.dispatchEvent(new Event('change', {bubbles: true})); return e.value === " + json.dumps(value) + "; })()")
        if not ok:
            raise RuntimeError(f"{value} 안 골라짐")
        frame()

    for st in json.load(open(steps_path, encoding="utf-8")):
        try:
            if "say" in st:
                c.js("(() => { const d = document.querySelector('#narr'); d.textContent = " + json.dumps(st["say"]) + "; d.classList.add('on'); return true; })()")
            if "hide" in st:
                c.js("(() => { document.querySelector('#narr').classList.remove('on'); return true; })()")
            if "move" in st:
                x, y = at(st["move"]); move(x, y)
            if "click" in st:
                click(st["click"], mod=8 if st.get("shift") else 0)
            if "clickif" in st:                                   # 조건이 맞을 때만 누른다 (토글 버튼)
                if c.js("!!(" + st["clickif"]["when"] + ")"):
                    click(st["clickif"]["at"])
            if "dbl" in st:
                click(st["dbl"], 2)
            if "drag" in st:
                drag(st["drag"]["from"], st["drag"]["to"])
            if "draw" in st:                                   # 도구 고르고 끌어 그리기 — 안 생기면 한 번 더
                d = st["draw"]
                for tryn in range(2):
                    n0 = c.js("page.items.length")
                    click(f'[data-tool="{d["tool"]}"]')
                    time.sleep(0.25 / SPEED)
                    drag(d["from"], d["to"])
                    time.sleep(0.4 / SPEED)
                    if c.js("page.items.length") > n0:
                        break
                    print(f"  ! {d['tool']} 안 그려짐 — 다시", flush=True)
            if "answer" in st:                                 # 다음 누르기가 여는 묻는 창에 칠 글(새 단락 스타일 이름 등)
                c.answer = str(st["answer"])
            if "type" in st:
                typetext(st["type"])
            if "fill" in st:
                fill_in(st["fill"]["at"], st["fill"]["value"])
            if "write" in st:                                  # 지면의 글상자를 두 번 눌러 글을 친다
                want = st["write"]["value"]
                for tryn in range(3):
                    click(st["write"]["at"], 2)
                    time.sleep(0.4 / SPEED)
                    if not c.js("!!(document.querySelector('#tedit') && document.querySelector('#tedit').offsetParent)"):
                        print("  ! 글 편집칸이 안 열렸다 — 다시", flush=True)
                        continue
                    wipe(40)
                    typetext(want)
                    click(st.get("away") or [W - 60, H - 120])     # 칸 밖을 눌러 확정 (Esc 는 취소다)
                    click(st["write"]["at"])                       # 방금 쓴 글상자를 다시 고른다
                    got = c.js("(() => { const it = page.items[sel]; return it && it.atom ? String(it.atom.text || '') : null; })()")
                    if got is not None and want[:6] in got:
                        break
                    print(f"  ! 글이 「{str(got)[:14]}」 — 다시", flush=True)
            if "key" in st:
                key(st["key"])
            if "pick" in st:
                pick(st["pick"]["at"], st["pick"]["value"])
            if "js" in st:
                v = c.js(st["js"])
                if v not in (None, True):
                    print("  js →", str(v)[:140], flush=True)
            if "upload" in st:                                 # 파일 고르기 — 사람이 창에서 고르는 것과 같다
                u = st["upload"]
                doc = c.call("DOM.getDocument")
                node = c.call("DOM.querySelector", nodeId=doc["root"]["nodeId"], selector=u["at"])
                if not node.get("nodeId"):
                    raise RuntimeError(f"파일 칸 없음 {u['at']}")
                c.call("DOM.setFileInputFiles", files=[u["path"]], nodeId=node["nodeId"])
                frame()
            if "shot" in st:
                d = c.call("Page.captureScreenshot", format="png")
                open(os.path.join(SP, st["shot"]), "wb").write(base64.b64decode(d["data"]))
        except Exception as e:
            print("  ERR", json.dumps(st, ensure_ascii=False)[:70], "→", str(e)[:160], flush=True)
            shot1 = os.path.join(SP, "_첫오류.png")                  # 처음 실패한 순간의 화면 — 원인 찾기용
            if not os.path.exists(shot1):
                try:
                    open(shot1, "wb").write(base64.b64decode(c.call("Page.captureScreenshot", format="png")["data"]))
                    print("  첫 오류 화면:", shot1, flush=True)
                except Exception:
                    pass
        hold(st.get("wait", 600))
finally:
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()
    shutil.rmtree(PROF, ignore_errors=True)                         # 실패해도 지운다 — 판마다 새 프로필이라 남기면 쌓여 디스크가 찼다(25GB, 2026-10-09)

if n[0] < 2:
    raise SystemExit("프레임이 없다")
subprocess.run([FFMPEG, "-y", "-framerate", str(FPS), "-i", os.path.join(frames, "%05d.jpg"),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2",
                "-movflags", "+faststart", out], capture_output=True)
print(f"{out} · 프레임 {n[0]} · {n[0]/FPS:.0f}초")
