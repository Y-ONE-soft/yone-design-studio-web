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
  {"pick": {"at": 자리, "value": "wb216"}}  select 을 눌러 고르기 · {"pick": {"at": 자리, "text": "보이는 글자"}}
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
# 바로 넣기 — 검증한 동작만 쓰는 대본을 빠르게(tests/e2e/actions.py 가 가른다). 같은 칸·같은 단추·같은 지면 자리를 쓰되
# 마우스를 한 번에 옮기고, 글은 한꺼번에 넣고(Input.insertText), 목록은 편집기 목록이 고를 때와 같은 신호(input·change)로 고르고,
# 패널이 멈추길 0.2초만 본다. 녹화 없이(REC_FAST 와 같이) 쓴다. 판정은 사람 조작 검사와 같다(2026-10-11)
DIRECT = os.environ.get("REC_DIRECT") == "1"
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
    c.call("Page.setInterceptFileChooserDialog", enabled=True)   # 파일 고르기 창 — 단추를 누르면 뜬 창을 받아 파일을 고른다(upload)
    try:                                                     # 붙여넣기 — 클립보드에 글을 올리고 ⌘V 를 누른다
        c.call("Browser.grantPermissions", permissions=["clipboardReadWrite", "clipboardSanitizedWrite"], origin=url.split("/units")[0])
    except Exception:
        pass
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
        if DIRECT:
            time.sleep(min(ms, 60) / 1000.0)
            return
        if FAST:
            time.sleep(min(ms, 300) / 1000.0)      # 화면이 따라올 최소한만
            return
        t0 = time.time()
        while (time.time() - t0) * 1000 < ms:
            frame(True)
            left = ms / 1000 - (time.time() - t0)
            time.sleep(max(0, min(1 / FPS, left)))

    def settle(limit=10):
        """화면이 다 그려질 때까지 — 지면 그림의 요소 수가 실제 요소 수와 같아질 때까지 기다린다(사람은 보이고 나서 누른다).
        새 문서의 첫 그리기는 서버에서 그림을 받아 오느라 늦다 — 안 기다리고 누르면 바탕 종이가 눌린다."""
        t_end = time.time() + limit
        while time.time() < t_end:
            if c.js("(() => { try { return !page || document.querySelectorAll('#svgwrap g[data-fi]').length >= page.items.length; } catch (e) { return true; } })()"):
                return
            time.sleep(0.1)

    def quiet(limit=8):
        """오른쪽 패널이 다시 그려지는 중이면 멈출 때까지 — 사람은 패널이 바뀌는 걸 보고 기다렸다 누른다
        (값을 고르면 패널을 조금 뒤에 다시 그린다 — 그 사이 펼친 목록은 닫힌다)."""
        last, same, t_end = None, 0, time.time() + limit
        while time.time() < t_end:
            cur = c.js("(() => { const s = document.querySelector('#side'); return (window.__busy || 0) + '|' + (s ? s.innerHTML.length + ':' + s.scrollTop : ''); })()")
            if not str(cur).startswith("0|"):                # 서버와 주고받는 중 — 그림·패널이 아직 바뀐다
                same = 0
                time.sleep(0.1)
                continue
            same = same + 1 if cur == last else 0
            if same >= (2 if DIRECT else 8):                              # 0.8초 그대로 — 값을 넣으면 편집기가 0.5초쯤 뒤에 패널을 다시 그린다(그 사이 연 목록은 닫힌다)
                return
            last = cur
            time.sleep(0.1)

    def at(spot):
        """자리 → 화면 픽셀."""
        if isinstance(spot, (list, tuple)):
            return float(spot[0]), float(spot[1])
        if isinstance(spot, dict) and "mm" in spot:
            settle()
            for _ in range(40):                              # 지면의 그 점이 화면 밖이면 사람처럼 그림판 위에서 휠로 굴린다
                r = c.js("(() => { const p = document.querySelector('#paper'); const b = p.getBoundingClientRect(); "
                         "const a = document.querySelector('#area').getBoundingClientRect(); return [b.left, b.top, scale, a.top, a.bottom, (a.left + a.right) / 2]; })()")
                x, y = r[0] + spot["mm"][0] * r[2], r[1] + spot["mm"][1] * r[2]
                dy = -1 if y < r[3] + 8 else (1 if y > r[4] - 8 else 0)  # (A5 둘째 쪽 — 연속 보기에서 새 쪽 아래가 잘려 보였다, 2026-10-12)
                if not dy:
                    return x, y
                wx, wy = r[5], (r[3] + r[4]) / 2
                move(wx, wy, steps=4, shoot=False)
                c.call("Input.dispatchMouseEvent", type="mouseWheel", x=wx, y=wy, deltaX=0, deltaY=dy * min(240, max(60, abs(y - wy))))
                time.sleep(0.08)
                frame()
            raise RuntimeError(f"굴려도 안 보임 {spot}")
        t_end = time.time() + 5                              # 칸이 늦게 그려지면(스타일 창이 값 바꾼 뒤 다시 그림) 나올 때까지 — 사람도 칸이 보이면 누른다
        while time.time() < t_end and not c.js("!!document.querySelector(" + json.dumps(spot) + ")"):   # (8배속에서 밑줄 켠 뒤 두께 칸을 바로 찾아 「못 찾음」, 2026-10-15)
            time.sleep(0.2)
        for _ in range(4):                                   # 접힌 칸(details) — 사람처럼 머리(summary)를 눌러 편다
            sm = c.js("(() => { const e = document.querySelector(" + json.dumps(spot) + "); if (!e) return null; "
                      "const ds = []; let d = e.closest('details'); while (d) { if (!d.open) ds.push(d); d = d.parentElement && d.parentElement.closest('details'); } "
                      "const top = ds.pop(); if (!top) return null; const s = top.querySelector(':scope > summary'); s.scrollIntoView({block:'nearest'}); "
                      "const b = s.getBoundingClientRect(); return [b.left + Math.min(b.width/2, 60), b.top + b.height/2]; })()")
            if not sm:
                break
            move(sm[0], sm[1]); press(sm[0], sm[1]); release(sm[0], sm[1])
        for _ in range(60):                                  # 화면 밖이면 휠로 굴린다(그 요소를 품은 스크롤 영역 위에서)
            r = c.js("(() => { const e = document.querySelector(" + json.dumps(spot) + "); if (!e) return null; const b = e.getBoundingClientRect(); "
                     "let p = e.parentElement; while (p && !(p.scrollHeight > p.clientHeight + 2 && /(auto|scroll)/.test(getComputedStyle(p).overflowY))) p = p.parentElement; "
                     "const v = p ? p.getBoundingClientRect() : {top: 0, bottom: innerHeight, left: 0, right: innerWidth}; "
                     "const top = Math.max(v.top, 0), bot = Math.min(v.bottom, innerHeight); const cx = b.left + b.width/2, cy = b.top + b.height/2; "
                     "const dy = cy < top + 8 ? -1 : (cy > bot - 8 ? 1 : 0); "
                     "return [cx, cy, dy, (v.left + v.right) / 2, (top + bot) / 2, Math.abs(cy - (top + bot) / 2)]; })()")
            if not r:
                raise RuntimeError(f"못 찾음 {spot}")
            if not r[2]:
                time.sleep(0.12)                         # 굴린 뒤 부드러운 스크롤이 아직 움직이는 중이면 옛 자리를 누른다 — 자리가 멈출 때까지
                r2 = c.js("(() => { const b = document.querySelector(" + json.dumps(spot) + ").getBoundingClientRect(); return [b.left + b.width/2, b.top + b.height/2]; })()")
                if abs(r2[0] - r[0]) > 0.5 or abs(r2[1] - r[1]) > 0.5:
                    continue
                hit = c.js("(() => { const e = document.querySelector(" + json.dumps(spot) + "); const t = document.elementFromPoint(" + f"{r[0]:.1f}, {r[1]:.1f}" + "); "
                           "return !!t && (t === e || e.contains(t) || (e.labels && [...e.labels].some(l => l.contains(t)))); })()")
                if hit:
                    return float(r[0]), float(r[1])
                c.js("(() => { const e = document.querySelector(" + json.dumps(spot) + "); if (e) e.scrollIntoView({block: 'center'}); })()")   # 화면 안인데 다른 것(아래 해설 띠 · 창 머리)이 덮었다 — 가운데로
                time.sleep(0.1)                          # (정본 본문 O/X 「부정어 밑줄」 밑줄 칸이 아래 해설 띠에 가려 안 눌렸다, 2026-10-15)
                continue
            wx, wy = r[3], r[4]
            move(wx, wy, steps=4, shoot=False)
            c.call("Input.dispatchMouseEvent", type="mouseWheel", x=wx, y=wy, deltaX=0, deltaY=r[2] * min(240, max(60, r[5])))
            time.sleep(0.05)
            frame()
        raise RuntimeError(f"굴려도 안 보임 {spot}")

    def cursor(x, y, down=False):
        c.js(f"__cur({x:.0f},{y:.0f},{'true' if down else 'false'})")

    def move(x, y, steps=12, shoot=True):
        if DIRECT:
            steps = 1
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

    CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"

    def hangul_states(ch):
        """한 음절을 입력기로 칠 때 보이는 조합 단계 — 스 → (ㅅ, 스), 텝 → (ㅌ, 테, 텝)"""
        o = ord(ch) - 0xAC00
        cho, jung, jong = o // 588, (o % 588) // 28, o % 28
        st = [CHO[cho], chr(0xAC00 + cho * 588 + jung * 28)]
        if jong:
            st.append(ch)
        return st

    def typetext(t, per=0.035):
        """사람처럼 친다 — 영문·숫자·기호는 키를 하나씩 누르고 떼고, 한글은 입력기 조합(자모 → 음절)으로, 줄 나눔은 키로."""
        per = per / SPEED
        if DIRECT:                                       # 한꺼번에 — 새 문단(Enter)·줄 나눔(Shift+Enter)만 키로
            for i, part in enumerate(t.split("\n")):
                if i:
                    key("Enter")
                for j, seg in enumerate(part.split(" ")):
                    if j:
                        key("Enter", shift=True)
                    if seg:
                        c.call("Input.insertText", text=seg)
            return
        for ch in t:
            if ch == "\u2028":                          # 줄 나눔 — Shift+Enter
                key("Enter", shift=True)
                continue
            if ch == "\n":                              # 새 문단 — Enter
                key("Enter")
                continue
            if "\uac00" <= ch <= "\ud7a3":            # 한글 음절 — 입력기가 조합하듯 단계를 보여 주고 확정
                for stg in hangul_states(ch):
                    c.call("Input.imeSetComposition", text=stg, selectionStart=len(stg), selectionEnd=len(stg))
                c.call("Input.insertText", text=ch)
            elif ch.isascii() and ch.isprintable():      # 키 하나 — 누르고(글자) 떼고
                kc = ord(ch.upper()) if ch.isalnum() else 0
                c.call("Input.dispatchKeyEvent", type="keyDown", key=ch, text=ch, unmodifiedText=ch, windowsVirtualKeyCode=kc)
                c.call("Input.dispatchKeyEvent", type="keyUp", key=ch, windowsVirtualKeyCode=kc)
            else:                                        # 기호(ⓐ · ⁅ …) — 입력기 기호표에서 고르듯 그 글자를 넣는다
                c.call("Input.imeSetComposition", text=ch, selectionStart=1, selectionEnd=1)
                c.call("Input.insertText", text=ch)
            if len(t) < 40 or ord(ch) % 3 == 0:
                frame()
            time.sleep(per)
        frame()

    def paste(t):
        """붙여넣기 — 클립보드에 올리고 ⌘V(또는 Ctrl+V)를 누른다. 긴 원고는 사람도 치지 않고 붙인다"""
        c.js("navigator.clipboard.writeText(" + json.dumps(t) + ").then(() => true)")
        mod = 4 if sys.platform == "darwin" else 2
        c.call("Input.dispatchKeyEvent", type="rawKeyDown", key="v", code="KeyV", windowsVirtualKeyCode=86, modifiers=mod, commands=["paste"])
        c.call("Input.dispatchKeyEvent", type="keyUp", key="v", code="KeyV", windowsVirtualKeyCode=86, modifiers=mod)
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
        got = None
        for tryn in range(3):
            click(spot, 2)
            if isinstance(spot, str) and not c.js("(() => { const e = document.querySelector(" + json.dumps(spot) + "); return !!e && document.activeElement === e; })()"):
                print(f"  ~ {spot} 칸이 안 골라졌다 — 지우기(Backspace) 없이 다시", flush=True)   # 다른 데가 눌렸는데 지우면 고른 개체가 지워진다 · 「~」= 다시 해서 된 것(끝내 안 되면 아래 「!」)
                c.js("(() => { const e = document.querySelector(" + json.dumps(spot) + "); if (e) e.scrollIntoView({block: 'center'}); })()")
                time.sleep(0.3)
                continue
            n = c.js("(() => { const e = document.querySelector(" + json.dumps(spot) + "); return e ? String(e.value).length : 0; })()") if isinstance(spot, str) else 0
            if (n or 0) > 200:                           # 긴 글이 든 칸 — 전체 선택(Ctrl/⌘+A) 뒤 지우기
                c.call("Input.dispatchKeyEvent", type="rawKeyDown", windowsVirtualKeyCode=65, key="a", code="KeyA", modifiers=4 if sys.platform == "darwin" else 2, commands=["selectAll"])
                c.call("Input.dispatchKeyEvent", type="keyUp", windowsVirtualKeyCode=65, key="a", code="KeyA", modifiers=4 if sys.platform == "darwin" else 2)
                wipe(1)
            else:
                wipe(max(14, (n or 0) + 2))
            if len(str(value)) > 2000:                   # 긴 원고(JSON)는 붙여넣기 — 사람도 치지 않고 붙인다(9만 자를 한 자씩 치면 15분)
                paste(str(value))
            else:
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

    def pick(spot, value, text=None):
        """목록(select) 고르기 — 사람처럼 목록을 눌러 펼치고(편집기 화면 안 목록) 그 항목을 마우스로 누른다(안 보이면 목록 위에서 휠로 굴린다).
        고른 뒤 패널이 다 바뀌면 골라진 값을 본다 — 틀렸으면(펼친 사이 패널이 다시 그려져 목록이 바뀐 때) 사람처럼 다시 펼쳐 고른다(3번까지).
        text 를 주면 보이는 글자로 찾는다(값이 그때그때 만들어지는 id 일 때 — 쪽 「이어 갈 면」)."""
        sel = json.dumps(spot)
        find = ("[...e.options].findIndex(o => o.textContent.trim() === " + json.dumps(text) + ")") if text else \
               ("[...e.options].findIndex(o => o.value === " + json.dumps(value) + ")")
        chk = ("(e.options[e.selectedIndex] || {}).textContent.trim() === " + json.dumps(text)) if text else ("e.value === " + json.dumps(value))
        fm = ("[...m.children].find(d => d.textContent.trim() === " + json.dumps(text) + ")") if text else \
             ("[...m.children].find(d => d.dataset.value === " + json.dumps(value) + ")")
        got = None
        if DIRECT:                                       # 편집기 목록이 고를 때와 같은 신호 — 안 되면 아래 사람 조작으로
            quiet()
            r = c.js("(() => { const e = document.querySelector(" + sel + "); if (!e) return null; const i = " + find + "; if (i < 0) return null; "
                     "if (e.selectedIndex !== i) { e.selectedIndex = i; e.dispatchEvent(new Event('input', {bubbles: true})); "
                     "e.dispatchEvent(new Event('change', {bubbles: true})); } return true; })()")
            quiet()
            if r and ((str(value).startswith("__") and not text) or
                      c.js("(() => { const e = document.querySelector(" + sel + "); return e ? " + chk + " : false; })()")):
                return
        for attempt in range(3):
            quiet()
            want = c.js("(() => { const e = document.querySelector(" + sel + "); return e ? " + find + " : null; })()")
            if want is None or want < 0:
                raise RuntimeError(f"{text or value} 목록에 없음")
            if c.js("(() => { const e = document.querySelector(" + sel + "); return e ? " + chk + " : false; })()"):
                return                                   # 이미 그 값 — 고를 것 없다
            prev = c.js("(() => { const e = document.querySelector(" + sel + "); return e ? e.value : null; })()")
            click(spot)
            if not c.js("!!document.querySelector('.selmenu')"):
                continue
            i = c.js("(() => { const m = document.querySelector('.selmenu'); const d = m && " + fm + "; return d ? +d.dataset.i : -1; })()")
            if i is None or i < 0:
                raise RuntimeError(f"{text or value} 펼친 목록에 없음")
            if not c.js("!!document.querySelector('.selmenu .opt[data-i=\"" + str(i) + "\"]')"):
                print(f"  ~ {text or value} — 목록이 닫혔다, 다시 펼친다", flush=True)
                continue
            try:
                click(f'.selmenu .opt[data-i="{i}"]')    # 펼친 목록에서 그 항목을 눌러 고른다
            except RuntimeError:                         # 누르러 가는 사이 목록이 닫혔다 — 다시 펼친다
                print(f"  ~ {text or value} — 목록이 닫혔다, 다시 펼친다", flush=True)
                continue
            quiet()
            if c.js("(() => { const e = document.querySelector(" + sel + "); return e ? " + chk + " : null; })()"):
                frame()
                return
            got = c.js("(() => { const e = document.querySelector(" + sel + "); return e ? e.value : null; })()")
            if not text and str(value).startswith("__") and got not in (None, prev) and not str(got).startswith("__"):
                frame()                                  # 「새 …」처럼 만드는 항목 — 고르면 만든 것(새 이야기 「이야기1」)으로 값이 바뀐다. 다시 고르면 또 만든다
                return
            print(f"  ~ {text or value} 대신 {got} — 다시 고른다", flush=True)
        raise RuntimeError(f"{text or value} 안 골라짐 — 지금 {got}")

    for st in json.load(open(steps_path, encoding="utf-8")):
        try:
            if "say" in st:
                c.js("(() => { const d = document.querySelector('#narr'); d.textContent = " + json.dumps(st["say"]) + "; d.classList.add('on'); return true; })()")
            if "hide" in st:
                c.js("(() => { document.querySelector('#narr').classList.remove('on'); return true; })()")
            if "move" in st:
                x, y = at(st["move"]); move(x, y)
            if "click" in st:
                if isinstance(st["click"], str):                   # 창이 늦게 뜨면(스타일 창 등) 단추가 나올 때까지 잠깐(최대 5초) 기다린다 — 사람도 창이 뜬 걸 보고 누른다
                    t_end = time.time() + 5
                    while time.time() < t_end and not c.js("!!document.querySelector(" + json.dumps(st["click"]) + ")"):
                        time.sleep(0.2)
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
                    print(f"  ~ {d['tool']} 안 그려짐 — 다시", flush=True)            # 「~」= 다시 해서 된 것
                else:
                    print(f"  ! {d['tool']} 두 번 끌어도 안 그려짐", flush=True)
            if "answer" in st:                                 # 다음 누르기가 여는 묻는 창에 칠 글(새 단락 스타일 이름 등)
                c.answer = str(st["answer"])
            if "type" in st:
                typetext(st["type"])
            if "fill" in st:
                fill_in(st["fill"]["at"], st["fill"]["value"])
            if "write" in st:                                  # 지면의 글상자를 두 번 눌러 글을 친다
                want, got = st["write"]["value"], None
                for tryn in range(3):
                    click(st["write"]["at"], 2)
                    time.sleep(0.4 / SPEED)
                    if not c.js("!!(document.querySelector('#tedit') && document.querySelector('#tedit').offsetParent)"):
                        print("  ! 글 편집칸이 안 열렸다 — 다시", flush=True)
                        continue
                    wipe(40)
                    if len(want) > 300:                        # 긴 글은 붙여넣기(사람도 긴 글은 붙인다)
                        paste(want)
                    else:
                        typetext(want)
                    if os.environ.get("REC_DEBUG"):
                        print("  ? 친 뒤", c.js("(() => { const t = document.querySelector('#tedit'); const a = document.activeElement; return JSON.stringify([t && t.innerText, t && t.style.display, a && (a.tagName + '#' + a.id + '.' + a.className)]); })()"), flush=True)
                    click(st.get("away") or [W - 60, H - 120])     # 칸 밖을 눌러 확정 (Esc 는 취소다)
                    click(st["write"]["at"])                       # 방금 쓴 글상자를 다시 고른다
                    got = c.js("(() => { const it = page.items[sel]; return it && it.atom ? String(it.atom.text || '') : null; })()")
                    if got is not None and want[:6] in got:
                        break
                    print(f"  ! 글이 「{str(got)[:14]}」 — 다시 ({st['write']['at']})", flush=True)
                else:                                          # 세 번 쳐도 안 들어가면 대본 오류 — 기본 문구가 남은 채 넘어가지 않는다
                    raise RuntimeError(f"글 안 들어감 {st['write']['at']} — 지금 「{str(got)[:20]}」")
            if "select" in st:                                # 글 고치기 칸에서 글자 고르기 — 그 글의 첫 글자에서 끝 글자까지 마우스로 끈다(사람처럼)
                q = st["select"]
                r = c.js("(() => { const box = document.querySelector('#tedit'); const want = " + json.dumps(q["text"]) + ", nth = " + str(int(q.get("nth", 0))) + "; "
                         "const w = document.createTreeWalker(box, NodeFilter.SHOW_TEXT); let n, k = 0; "
                         "while ((n = w.nextNode())) { let i = -1; while ((i = n.data.indexOf(want, i + 1)) >= 0) { if (k++ === nth) { "
                         "const a = document.createRange(); a.setStart(n, i); a.setEnd(n, i + 1); const b = document.createRange(); b.setStart(n, i + want.length - 1); b.setEnd(n, i + want.length); "
                         "const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect(); return [ra.left + 0.5, (ra.top + ra.bottom) / 2, rb.right - 0.5, (rb.top + rb.bottom) / 2]; } } } return null; })()")
                if not r:
                    raise RuntimeError(f"고를 글 없음 {q['text']}")
                click([r[0], r[1]])                            # 먼저 한 번 눌러 고른 것을 푼다 — 골라진 글 위에서 끌면 크롬은 「글 옮기기」로 받는다(창을 열면 글 전체가 골라져 있다)
                time.sleep(0.3)
                drag([r[0], r[1]], [r[2], r[3]], steps=8)
                got = c.js("String(getSelection())")
                if got != q["text"]:
                    raise RuntimeError(f"고른 글이 「{got}」 — 「{q['text']}」 이어야")
            if "key" in st:
                key(st["key"])
            if "pick" in st:
                pick(st["pick"]["at"], st["pick"].get("value"), st["pick"].get("text"))
            if "until" in st:                                  # 화면이 그 상태가 될 때까지 기다린다(최대 60초) — 서버가 바쁠 때 새 문서 열기 등
                t_end = time.time() + 60
                while not c.js("(() => { try { return !!(" + st["until"] + "); } catch (e) { return false; } })()") and time.time() < t_end:
                    time.sleep(0.25)
            if "js" in st:
                v = c.js(st["js"])
                if v not in (None, True):
                    print("  js →", str(v)[:140], flush=True)
            if "upload" in st:                                 # 파일 올리기 — 단추(또는 칸을 품은 라벨)를 진짜로 누르고, 뜬 파일 창에서 고른다
                u = st["upload"]
                inp = u["at"].split()[-1]
                btn = u.get("click") or (f"label:has({inp})" if c.js(f"!!document.querySelector('label:has({inp})')") else None)
                if not btn:
                    raise RuntimeError(f"파일 단추 없음 {u['at']} — 「click」 으로 여는 단추를 적을 것")
                c.events = []
                click(btn)
                t_end = time.time() + 5
                while not c.events and time.time() < t_end:
                    c.js("1")
                    time.sleep(0.1)
                if not c.events:
                    raise RuntimeError(f"파일 창이 안 떴다 — {btn}")
                ev = c.events.pop(0)["params"]
                c.call("DOM.setFileInputFiles", files=[u["path"]], backendNodeId=ev["backendNodeId"])
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
