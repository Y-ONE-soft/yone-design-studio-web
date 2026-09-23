"""캔버스 전체 감사 — 사용자가 하듯 **진짜 마우스·키보드 입력**(CDP Input.dispatch*)으로 기능 하나하나를 돌려 보고 PASS/FAIL 을 적는다.

    python3 tests/e2e/canvas_audit.py http://127.0.0.1:5099        (서버가 떠 있어야 한다. 감사 문서를 하나 만들고 끝에 지운다)

실패는 스크린샷(tests/e2e/out/audit_<n>_<이름>.png)과 out/audit_result.json. 요소에 직접 dispatchEvent 하는 시험은
"코드는 도는데 화면엔 안 보이는" 버그(display:none 위에 style.display="" 등)를 못 잡는다 — 여기선 elementFromPoint 로 마우스에 잡히는지까지 본다.
새 기능을 넣으면 여기에 한 단계 더한다. 52단계: 시작 화면·페이지 띠·요소 넣기·선택/이동·손잡이·키보드·글 편집·오른쪽 클릭·자/확대/손·레이어/속성·저장·브랜드/원고/미리보기/검수/PDF·요소 저장.
"""
import base64, json, os, subprocess, sys, time, traceback, urllib.parse, urllib.request
SP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
os.makedirs(SP, exist_ok=True)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp import CDP, CHROME, PORT
BASE = sys.argv[1].rstrip("/")
CTRL, SHIFT, ALT, META = 2, 8, 1, 4
R = []          # (name, ok, note)
shot_n = [0]

def wait_server():
    for _ in range(40):
        try:
            urllib.request.urlopen(BASE + "/api/v1/health", timeout=2); return
        except Exception:
            time.sleep(0.5)

wait_server()
proc = subprocess.Popen([CHROME, "--headless=new", "--disable-gpu", f"--remote-debugging-port={PORT}", "--window-size=1600,1000", "--user-data-dir=/tmp/yone-canvas-audit", "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    for _ in range(50):
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version"); break
        except Exception:
            time.sleep(0.2)
    tab = json.load(urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{PORT}/json/new?{urllib.parse.quote(BASE + '/units', safe='')}", method="PUT")))
    c = CDP(tab["webSocketDebuggerUrl"])
    c.call("Page.enable")
    c.call("Page.addScriptToEvaluateOnNewDocument", source="window.confirm = () => true; window.prompt = (m, d) => window.__promptv || ((d != null && d !== '') ? d : 'x'); window.alert = (m) => { window.__alert = m; }; window.open = (u) => { window.__opened = u; }; window.__errs = []; window.addEventListener('error', e => __errs.push(e.message)); window.addEventListener('unhandledrejection', e => __errs.push('rej ' + (e.reason && e.reason.message || e.reason)));")
    c.call("Page.reload")
    time.sleep(3)

    def js(x): return c.js(x)
    def shot(tag):
        shot_n[0] += 1
        tag = "".join(ch if ch not in '/\\:' else "_" for ch in tag)
        d = c.call("Page.captureScreenshot", format="png")
        open(f"{SP}/audit_{shot_n[0]}_{tag}.png", "wb").write(base64.b64decode(d["data"]))
        return f"audit_{shot_n[0]}_{tag}.png"
    def rec(name, ok, note=""):
        s = ""
        if not ok:
            s = shot(name.replace(" ", "_")[:30])
        R.append((name, bool(ok), (note + (" → " + s if s else "")).strip()))
        print(("PASS " if ok else "FAIL ") + name + ("  | " + note if note else "") + ("  | " + s if s else ""), flush=True)
    def step(name, fn):
        try:
            r = fn()
            if isinstance(r, tuple): rec(name, r[0], r[1])
            else: rec(name, r)
        except Exception as e:
            rec(name, False, "예외 " + str(e).splitlines()[0][:160])
    def wait(cond, t=8.0, every=0.2):
        end = time.time() + t
        while time.time() < end:
            try:
                if js(cond): return True
            except Exception:
                pass
            time.sleep(every)
        return False
    def mouse(t, x, y, button="left", mods=0, clicks=1):
        c.call("Input.dispatchMouseEvent", type=t, x=x, y=y, button=button, modifiers=mods, clickCount=clicks)
    def click(x, y, mods=0, button="left"):
        mouse("mouseMoved", x, y, mods=mods); mouse("mousePressed", x, y, button, mods); mouse("mouseReleased", x, y, button, mods); time.sleep(0.35)
    def dbl(x, y):
        mouse("mousePressed", x, y); mouse("mouseReleased", x, y); mouse("mousePressed", x, y, clicks=2); mouse("mouseReleased", x, y, clicks=2); time.sleep(0.4)
    def drag(x0, y0, x1, y1, mods=0, button="left", steps=8):
        mouse("mouseMoved", x0, y0, mods=mods); mouse("mousePressed", x0, y0, button, mods)
        for i in range(1, steps + 1):
            mouse("mouseMoved", x0 + (x1 - x0) * i / steps, y0 + (y1 - y0) * i / steps, mods=mods); time.sleep(0.02)
        mouse("mouseReleased", x1, y1, button, mods); time.sleep(0.5)
    def key(k, mods=0, code=None, text=None):
        kw = {"modifiers": mods, "key": k}
        if code: kw["code"] = code
        if text: kw["text"] = text
        c.call("Input.dispatchKeyEvent", type="keyDown", **kw)
        c.call("Input.dispatchKeyEvent", type="keyUp", **kw)
        time.sleep(0.3)
    def rect(sel):
        return js(f"(() => {{ const el = document.querySelector({json.dumps(sel)}); if (!el) return null; const r = el.getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; }})()")
    def center(sel):
        r = rect(sel); return (r[0] + r[2] / 2, r[1] + r[3] / 2) if r else None
    def visible(sel):
        return js(f"(() => {{ const el = document.querySelector({json.dumps(sel)}); if (!el) return false; const cs = getComputedStyle(el); const r = el.getBoundingClientRect(); return cs.display !== 'none' && cs.visibility !== 'hidden' && r.width > 0 && r.height > 0; }})()")
    def at(x, y):
        return js(f"(() => {{ const el = document.elementFromPoint({x}, {y}); return el ? (el.tagName + (el.id ? '#' + el.id : '') + '.' + (el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className)) : null; }})()")
    def grect(i):
        return js(f"(() => {{ const g = gOf({i}); if (!g) return null; const r = g.getBoundingClientRect(); return [r.left, r.top, r.width, r.height]; }})()")
    def item(i): return js(f"JSON.stringify(page.items[{i}] || null)")
    def ensure(i):
        for _ in range(3):
            r, a = grect(i), rect("#area")
            if r and a and r[1] >= a[1] and r[1] + r[3] <= a[1] + a[3]: return r
            js(f"(() => {{ const g = gOf({i}), a = document.querySelector('#area'); if (!g) return; const r = g.getBoundingClientRect(), ar = a.getBoundingClientRect(); a.scrollTop += (r.top + r.height / 2) - (ar.top + a.clientHeight / 2); flowLock = Date.now() + 1200; }})()")
            time.sleep(0.5)
        return grect(i)
    def pick(i):
        """요소 i 가 실제로 마우스에 잡히는 점 — 떠 있는 도구 막대·손잡이에 가리지 않은 곳"""
        r = grect(i)
        if not r: return None
        for fx, fy in [(.5, .5), (.3, .7), (.7, .7), (.3, .3), (.7, .3), (.5, .9), (.1, .5), (.9, .5)]:
            x, y = r[0] + r[2] * fx, r[1] + r[3] * fy
            if js(f"(() => {{ const el = document.elementFromPoint({x}, {y}); const g = el && el.closest && el.closest('g[data-fi]'); return !!g && +g.dataset.fi === {i}; }})()"):
                return (x, y)
        return None
    def paper_pt(mmx, mmy):
        pr = rect("#paper"); sc = js("scale"); return (pr[0] + mmx * sc, pr[1] + mmy * sc)
    def mm_of(x, y):
        pr = rect("#paper"); sc = js("scale"); return ((x - pr[0]) / sc, (y - pr[1]) / sc)
    def n_items(): return js("page.items.length")
    def errs(): return js("__errs.splice(0)")

    # ───────── A. 시작 화면 ─────────
    step("A1 시작 화면 — 내 문서 목록이 보인다", lambda: (visible("#start") and js("document.querySelectorAll('#pcards .pcard').length") >= 2, f"cards={js('document.querySelectorAll(\"#pcards .pcard\").length')}"))
    NAME = "감사문서" + str(int(time.time()) % 100000)
    def a2():
        js(f"window.__promptv = {json.dumps(NAME)}"); c0 = center("#pcards .pcard.new"); t0 = time.time(); click(*c0); js("window.__promptv = null")
        ok = wait("!!(plan && page && document.querySelector('#svgwrap svg g[data-fi]'))", 30); took = round(time.time() - t0, 1)
        rec("A2b 새 문서가 3초 안에 열린다", took < 3, f"{took}s")
        return (ok and js("docPages().length") == 1 and not visible("#start"), f"opened={ok} plan={js('plan && plan.id')} pages={js('docPages().length')} start={visible('#start')} name={js('plan && plan.name')}")
    step("A2 ＋ 새 문서 → 바로 1쪽이 열린다", a2)
    PLAN = js("plan.id")
    def a3():
        click(*center("#p-home")); ok = wait("document.querySelector('#start').style.display !== 'none'", 5)
        cards = js(f"[...document.querySelectorAll('#pcards .pcard')].findIndex(d => d.textContent.includes({json.dumps(NAME)}))")
        js(f"document.querySelector('#pcards .pcard:nth-child({max(cards, 0) + 1})').scrollIntoView({{block: 'center'}})"); time.sleep(0.3)
        r = rect(f"#pcards .pcard:nth-child({max(cards, 0) + 1})")
        click(r[0] + r[2] / 2, r[1] + r[3] / 2)
        t0 = time.time(); ok2 = wait(f"!!(plan && plan.id === {json.dumps(PLAN)} && document.querySelector('#svgwrap svg g[data-fi]'))", 30)
        return (ok and ok2, f"home={ok} open={ok2} {round(time.time() - t0, 1)}s")
    step("A3 내 문서 화면 ↔ 문서 열기 (카드 클릭)", a3)

    # ───────── B. 페이지 띠 ─────────
    def b0():
        if js("!!view.strip"): click(*center("#tg-strip")); time.sleep(0.5)       # 접힌 상태에서 시작
        folded = not js("!!view.strip") and not visible("#rail .addpg")
        add, cnt = center("#f-addpg"), center("#f-cnt")
        if not add or not cnt: return (False, f"상태 줄 단추 없음 ＋쪽={bool(add)} 쪽수={bool(cnt)}")
        n0 = js("docPages().length"); click(*add); ok1 = wait(f"docPages().length === {n0 + 1}", 10)
        if ok1:
            js("deletePage(docPages()[docPages().length - 1])"); wait(f"docPages().length === {n0}", 10)
        if not js("!!view.strip"): click(*cnt)
        time.sleep(0.8); ok2 = visible("#rail .addpg")
        return (folded and ok1 and ok2, f"접으면 썸네일 숨음={folded} 상태줄 ＋쪽={ok1} 쪽수 눌러 폄={ok2} 쪽 {n0}→{js('docPages().length')}")
    step("B0 쪽 띠 접힘 — 상태 줄 ＋ 쪽 · 쪽수 눌러 펴기", b0)
    def b1():
        n0 = js("docPages().length"); r = rect("#rail .addpg"); click(r[0] + r[2] / 2, r[1] + r[3] / 2)
        time.sleep(0.5)
        menu = visible("#rail .addpg .menu")
        m = center('#rail .addpg .menu [data-new="body"]')
        if menu and m: click(*m)
        ok = wait(f"docPages().length === {n0 + 1}", 8)
        return (ok, f"{n0}→{js('docPages().length')} menu={menu}")
    step("B1 ＋ 페이지 추가", b1)
    def b2():
        cards = js("document.querySelectorAll('#rail .pg').length"); r = rect("#rail .pg:nth-child(1)")
        if not r: return (False, "카드 없음")
        click(r[0] + r[2] / 2, r[1] + r[3] / 2); ok = wait("page && page.id === docPages()[0].id", 5)
        return (ok and cards >= 2, f"cards={cards} page={js('page.id')}")
    step("B2 띠에서 페이지 클릭 → 그 페이지로", b2)
    def b3():
        r = rect("#rail .pg:nth-child(2)")
        if not r: return (False, "페이지 2 없음(B1 실패)")
        click(r[0] + r[2] / 2, r[1] + r[3] / 2); wait("page && page.id === docPages()[1].id", 5)
        mouse("mouseMoved", r[0] + r[2] / 2, r[1] + r[3] / 2); time.sleep(0.3)      # ✕ 는 썸네일에 올려야 나온다
        b = center("#rail .pg:nth-child(2) [data-pg-del]")
        if not b: return (False, "썸네일 ✕ 안 나옴")
        n0 = js("docPages().length"); click(*b); ok = wait(f"docPages().length === {n0 - 1}", 8)
        return (ok, f"{n0}→{js('docPages().length')}")
    step("B3 페이지 지우기 (🗑)", b3)
    def b4():
        r = rect("#rail .pg:nth-child(1)")
        mouse("mouseMoved", r[0] + r[2] / 2, r[1] + r[3] / 2); time.sleep(0.3)
        b = center("#rail .pg:nth-child(1) [data-pg-dup]")
        if not b: return (False, "썸네일 ⧉ 안 나옴")
        n0 = js("docPages().length"); click(*b); ok = wait(f"docPages().length === {n0 + 1}", 10)
        return (ok, f"{n0}→{js('docPages().length')}")
    step("B4 페이지 복제 (⧉)", b4)
    def b5():
        ids0 = js("docPages().map(p => p.id)"); r1 = rect("#rail .pg:nth-child(1)"); r2 = rect("#rail .pg:nth-child(2)")
        drag(r1[0] + r1[2] / 2, r1[1] + r1[3] / 2, r2[0] + r2[2] * 0.9, r2[1] + r2[3] / 2, steps=10); time.sleep(0.8)
        ids1 = js("docPages().map(p => p.id)")
        return (ids1 != ids0 and ids1[0] == ids0[1], f"{ids0}→{ids1}")
    step("B5 띠에서 페이지 끌어 순서 바꾸기", b5)
    js("open(docPages()[0])"); time.sleep(1.0)

    # ───────── C. 요소 넣기 ─────────
    def c1():
        n0 = n_items(); b = js("(() => { const el = [...document.querySelectorAll('.g0 button, .pal button, .draw button, button')].find(b => /글상자/.test(b.textContent)); if (!el) return null; const r = el.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()")
        if not b: return (False, "글상자 버튼 없음")
        click(*b)
        if not js("drawTool === 'text'"): return (False, "도구가 안 골라짐")
        x0, y0 = paper_pt(25, 60); x1, y1 = paper_pt(95, 80); drag(x0, y0, x1, y1, steps=10)
        ok = wait(f"page.items.length === {n0 + 1} && !!gOf({n0})", 8)
        it = json.loads(item(n0)) if ok else {}; a = it.get("atom", {})
        return (ok and a.get("t") == "text" and abs(a.get("w", 0) - 70) < 2 and abs(a.get("h", 0) - 20) < 2 and abs(it.get("x", 0) - 25) < 2 and js("sel") == n0 and not js("drawTool"),
                f"items {n0}→{n_items()} {a.get('w')}×{a.get('h')}mm sel={js('sel')}")
    step("C1 「글상자」 고르고 지면에서 끌면 그 크기로 그려진다 (인디자인처럼)", c1)
    def c2():
        n0 = n_items(); cardc = js("(() => { const el = [...document.querySelectorAll('.card')].find(d => /지문 상자/.test(d.textContent)); if (!el) return null; const r = el.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()")
        if not cardc: return (False, "지문 상자 카드 없음")
        tx, ty = paper_pt(30, 100); drag(cardc[0], cardc[1], tx, ty, steps=12)
        ok = wait(f"page.items.length === {n0 + 1}", 8)
        it = json.loads(item(n0)) if ok else {}
        return (ok and it.get("block") == "passage" and abs(it.get("x", 0) - 30) < 3 and abs(it.get("y", 0) - 100) < 3, f"{it}")
    step("C2 팔레트 카드를 끌어 페이지 위 자리에 놓기", c2)
    def c3():
        n0 = n_items(); b = js("(() => { const el = [...document.querySelectorAll('button')].find(b => /^\\s*(면|□)/.test(b.textContent) && b.closest('.upanel, .pal, #pbody')); if (!el) return null; const r = el.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()")
        if not b: return (False, "면 버튼 없음")
        click(*b); px, py = paper_pt(40, 120); click(px, py)
        ok = wait(f"page.items.length === {n0 + 1}", 8); a = json.loads(item(n0)).get("atom", {}) if ok else {}
        return (ok and a.get("t") == "rect" and a.get("w") == 60, item(n0)[:90])
    step("C3 「면」 고르고 지면을 그냥 누르면 기본 크기로 놓인다", c3)
    def c4():
        n0 = n_items(); b = js("(() => { const el = [...document.querySelectorAll('button')].find(b => /표/.test(b.textContent) && b.closest('.upanel, .pal, #pbody')); if (!el) return null; const r = el.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()")
        if not b: return (False, "표 버튼 없음")
        click(*b); time.sleep(0.5)
        # 표 만들기 폼이 뜨면 만들기 버튼
        mk = js("(() => { const el = [...document.querySelectorAll('button')].find(b => /만들기/.test(b.textContent) && b.closest('#setform, .tbl, .tform, #side, .upanel') && !b.id.includes('btn-ai')); if (!el) return null; const r = el.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()")
        if mk: click(*mk)
        ok = wait(f"page.items.length > {n0}", 8); return (ok, f"items {n0}→{n_items()}")
    step("C4 「표」 만들기", c4)

    # ───────── D. 선택·이동 ─────────
    TXT = js("page.items.findIndex(it => it.atom && it.atom.t === 'text')")
    PAS = js("page.items.findIndex(it => it.block === 'passage')")
    RECT = js("page.items.findIndex(it => it.atom && it.atom.t === 'rect')")
    js(f"page.items[{TXT}].x = 30; page.items[{TXT}].y = 40; page.items[{RECT}].x = 120; page.items[{RECT}].y = 40; save(); render()"); time.sleep(1.2)
    def d1():
        js("select([])"); r = grect(TXT); click(r[0] + 5, r[1] + 5)
        ok = wait(f"sel === {TXT}", 3)
        hv = js("[...document.querySelectorAll('#selbox .hd')].filter(h => getComputedStyle(h).display !== 'none' && h.getBoundingClientRect().width > 0).length")
        se = rect('#selbox .hd[data-h="se"]'); hit = at(se[0] + 4, se[1] + 4) if se else None
        return (ok and visible("#selbox") and hv == 8 and hit and "hd" in hit, f"handles={hv} hit={hit} tools={visible('#tools')}")
    step("D1 클릭 → 선택 상자·손잡이 8개·툴바 보이고 손잡이가 마우스에 잡힌다", d1)
    def d2():
        r = grect(TXT); x0 = js(f"page.items[{TXT}].x"); y0 = js(f"page.items[{TXT}].y")
        drag(r[0] + 6, r[1] + 6, r[0] + 6 + 60, r[1] + 6 + 40); time.sleep(0.5)
        x1 = js(f"page.items[{TXT}].x"); y1 = js(f"page.items[{TXT}].y"); sc = js("scale")
        return (x1 > x0 + 50 / sc * 0.8 and y1 > y0 + 30 / sc * 0.8, f"({x0},{y0})→({x1},{y1})")
    step("D2 요소 끌어 옮기기 (진짜 마우스)", d2)
    def d3():
        js("select([])"); a = paper_pt(10, 30); b = paper_pt(200, 130)
        drag(a[0], a[1], b[0], b[1], steps=10)
        n = js("sels.size"); return (n >= 2 and visible("#selbox") and js("document.querySelector('#selbox').classList.contains('multi')"), f"sels={n}")
    step("D3 빈 곳에서 범위 끌기 → 여럿 선택 + 감싸는 상자", d3)
    def d4():
        js(f"select([{TXT}], {TXT})"); pt = pick(RECT)
        if not pt: return (False, f"RECT={RECT} 가 마우스에 안 잡힌다")
        click(*pt, mods=SHIFT)
        return (js("sels.size") == 2, f"sels={js('[...sels]')} TXT={TXT} RECT={RECT}")
    step("D4 Shift+클릭으로 선택에 더하기", d4)
    def d5():
        r = grect(RECT); x0 = js(f"page.items[{RECT}].x"); js(f"select([{RECT}], {RECT})")
        drag(r[0] + 8, r[1] + 8, r[0] + 8 + 80, r[1] + 8 + 60, mods=CTRL)
        return (js(f"page.items[{RECT}].x") == x0 and js("sels.size") >= 1, f"moved={js(f'page.items[{RECT}].x') != x0} sels={js('sels.size')}")
    step("D5 요소 위에서 Ctrl+끌기 = 옮기지 않고 범위 선택", d5)
    def d6():
        js("scrollToActive()"); time.sleep(0.5)
        p = None
        for mmx, mmy in ((150, 60), (100, 90), (180, 120), (60, 150), (190, 20)):
            q = paper_pt(mmx, mmy); a = at(*q) or ""
            if "svg" in a.lower() or a.startswith("DIV#paper") or a.startswith("rect"):
                if not js(f"!!(document.elementFromPoint({q[0]}, {q[1]}) || {{}}).closest && !!document.elementFromPoint({q[0]}, {q[1]}).closest('g[data-fi]')"): p = q; break
        if not p: return (False, "빈 곳을 못 찾음")
        click(*p); return (js("sels.size") == 0 and not visible("#selbox"), f"at={at(*p)}")
    step("D6 빈 곳 클릭 → 선택 해제", d6)

    # ───────── E. 손잡이·회전 ─────────
    def e1():
        js(f"select([{RECT}], {RECT})"); time.sleep(0.3); w0 = js(f"page.items[{RECT}].atom.w"); h0 = js(f"page.items[{RECT}].atom.h")
        se = rect('#selbox .hd[data-h="se"]'); drag(se[0] + 4, se[1] + 4, se[0] + 4 + 60, se[1] + 4 + 40)
        return (js(f"page.items[{RECT}].atom.w") > w0 + 5 and js(f"page.items[{RECT}].atom.h") > h0 + 3, f"{w0}x{h0}→{js(f'page.items[{RECT}].atom.w')}x{js(f'page.items[{RECT}].atom.h')}")
    step("E1 면 모서리 끌기 → 폭·높이", e1)
    def e2():
        js(f"select([{RECT}], {RECT})"); time.sleep(0.3); w0 = js(f"page.items[{RECT}].atom.w"); h0 = js(f"page.items[{RECT}].atom.h")
        se = rect('#selbox .hd[data-h="se"]'); drag(se[0] + 4, se[1] + 4, se[0] + 4 + 80, se[1] + 4 + 10, mods=SHIFT)
        w1 = js(f"page.items[{RECT}].atom.w"); h1 = js(f"page.items[{RECT}].atom.h")
        return (abs(w1 / h1 - w0 / h0) < 0.08, f"비율 {w0 / h0:.2f}→{w1 / h1:.2f}")
    step("E2 Shift+모서리 = 비율 유지", e2)
    def e3():
        js(f"select([{PAS}], {PAS})"); time.sleep(0.3); se = rect('#selbox .hd[data-h="se"]'); drag(se[0] + 4, se[1] + 4, se[0] + 4 + 60, se[1] + 4 + 30)
        s = js(f"page.items[{PAS}].s"); lb = js("document.querySelector('#sellb').textContent")
        return (s and s > 1.05, f"s={s} label={lb}")
    step("E3 요소(지문 상자) 모서리 → 글자까지 균일 배율", e3)
    def e4():
        js(f"select([{PAS}], {PAS})"); time.sleep(0.3); w0 = js(f"page.items[{PAS}].w"); e = rect('#selbox .hd[data-h="e"]'); drag(e[0] + 4, e[1] + 4, e[0] + 4 - 50, e[1] + 4)
        return (js(f"page.items[{PAS}].w") < w0 - 5, f"w {w0}→{js(f'page.items[{PAS}].w')}")
    step("E4 요소 옆 손잡이 → 폭만", e4)
    def e5():
        js(f"select([{RECT}], {RECT})"); time.sleep(0.3); ro = rect("#selbox .rot")
        if not ro or ro[2] == 0: return (False, "회전 손잡이 안 보임")
        b = grect(RECT); cx, cy = b[0] + b[2] / 2, b[1] + b[3] / 2
        drag(ro[0] + 5, ro[1] + 5, cx + 120, cy - 20)
        rot = js(f"page.items[{RECT}].atom.rotate"); return (rot and rot > 5, f"rotate={rot}")
    step("E5 회전 손잡이 끌기", e5)
    js(f"delete page.items[{RECT}].atom.rotate; save(); render()"); time.sleep(0.8)

    # ───────── F. 키보드 ─────────
    def f1():
        js(f"select([{TXT}], {TXT})"); x0 = js(f"page.items[{TXT}].x"); key("ArrowRight", code="ArrowRight"); key("ArrowRight", mods=SHIFT, code="ArrowRight")
        return (abs(js(f"page.items[{TXT}].x") - (x0 + 5.5)) < 0.01, f"{x0}→{js(f'page.items[{TXT}].x')}")
    step("F1 화살표 0.5mm · Shift+화살표 5mm", f1)
    def f2():
        js(f"select([{TXT}], {TXT})"); n0 = n_items(); key("d", mods=CTRL, code="KeyD"); ok1 = wait(f"page.items.length === {n0 + 1}", 4)
        key("Delete", code="Delete"); ok2 = wait(f"page.items.length === {n0}", 4)
        key("z", mods=CTRL, code="KeyZ"); ok3 = wait(f"page.items.length === {n0 + 1}", 4)
        key("z", mods=CTRL | SHIFT, code="KeyZ"); ok4 = wait(f"page.items.length === {n0}", 4)
        return (ok1 and ok2 and ok3 and ok4, f"dup={ok1} del={ok2} undo={ok3} redo={ok4}")
    step("F2 Ctrl+D 복제 · Delete · Ctrl+Z · Ctrl+Shift+Z", f2)
    def f3():
        js(f"select([{TXT}], {TXT})"); n0 = n_items(); key("c", mods=CTRL, code="KeyC"); key("v", mods=CTRL, code="KeyV"); ok1 = wait(f"page.items.length === {n0 + 1}", 4)
        key("x", mods=CTRL, code="KeyX"); ok2 = wait(f"page.items.length === {n0}", 4); key("v", mods=CTRL, code="KeyV"); ok3 = wait(f"page.items.length === {n0 + 1}", 4)
        key("Delete", code="Delete"); wait(f"page.items.length === {n0}", 4)
        return (ok1 and ok2 and ok3, f"copy/paste={ok1} cut={ok2} paste={ok3}")
    step("F3 Ctrl+C/V · Ctrl+X", f3)
    def f4():
        n0 = n_items(); js(f"select([{TXT}, {RECT}], {RECT})"); key("g", mods=CTRL, code="KeyG"); ok1 = wait(f"page.items.length === {n0 - 1} && page.items.some(it => it.part)", 8)
        gi = js("page.items.findIndex(it => it.part && !/^table/.test(it.part))"); js(f"select([{gi}], {gi})"); key("g", mods=CTRL | SHIFT, code="KeyG"); ok2 = wait(f"page.items.length === {n0} && !page.items.some(it => it.part && !/^table/.test(it.part))", 8)
        return (ok1 and ok2, f"group={ok1} ungroup={ok2}")
    step("F4 Ctrl+G 그룹 · Ctrl+Shift+G 풀기", f4)
    TXT = js("page.items.findIndex(it => it.atom && it.atom.t === 'text')"); RECT = js("page.items.findIndex(it => it.atom && it.atom.t === 'rect')"); PAS = js("page.items.findIndex(it => it.block === 'passage')")
    def f5():
        key("a", mods=CTRL, code="KeyA"); n = js("sels.size"); key("Escape", code="Escape"); n2 = js("sels.size")
        js("select([0], 0)"); key("Tab", code="Tab"); s = js("sel")
        return (n == n_items() and n2 == 0 and s == 1, f"all={n} esc={n2} tab→{s}")
    step("F5 Ctrl+A · Esc · Tab", f5)
    def f6():
        js(f"select([{RECT}], {RECT})"); key("l", mods=CTRL, code="KeyL"); lk = js(f"page.items[{RECT}].lock === true")
        r = grect(RECT); x0 = js(f"page.items[{RECT}].x"); drag(r[0] + 8, r[1] + 8, r[0] + 60, r[1] + 8)
        moved = js(f"page.items[{RECT}].x") != x0
        js(f"select([{RECT}], {RECT})"); key("l", mods=CTRL, code="KeyL"); un = js(f"!page.items[{RECT}].lock")
        return (lk and not moved and un, f"lock={lk} moved={moved} unlock={un}")
    step("F6 Ctrl+L 잠금 → 못 옮김 → 풀기", f6)
    def f7():
        js(f"select([0], 0)"); key("]", mods=CTRL, code="BracketRight"); s1 = js("sel"); key("[", mods=CTRL, code="BracketLeft"); s2 = js("sel")
        return (s1 == 1 and s2 == 0, f"{s1},{s2}")
    step("F7 Ctrl+] / Ctrl+[ 한 단계 앞·뒤", f7)

    # ───────── G. 글 바로 고치기 ─────────
    TXT = js("page.items.findIndex(it => it.atom && it.atom.t === 'text')"); RECT = js("page.items.findIndex(it => it.atom && it.atom.t === 'rect')"); PAS = js("page.items.findIndex(it => it.block === 'passage')")
    def g1():
        js("select([])"); r = ensure(TXT); pt = pick(TXT) or (r[0] + 6, r[1] + 6); dbl(*pt)
        ok = wait("document.querySelector('#tedit').style.display !== 'none'", 3)
        if not ok: return (False, f"TXT={TXT} r={r} at={at(*pt)}")
        exp = js(f"(() => {{ const pr = document.querySelector('#paper').getBoundingClientRect(), b = bboxOf({TXT}); return [pr.left + b.x * scale, pr.top + b.y * scale]; }})()")
        tr = rect("#tedit"); over = bool(tr and exp and abs(tr[0] - exp[0]) < 3 and abs(tr[1] - exp[1]) < 3)
        if ok:
            js("(() => { const t = document.querySelector('#tedit'); t.focus(); t.select(); })()")
            c.call("Input.insertText", text="감사 글")
            key("Enter", mods=CTRL, code="Enter")
        ok2 = wait(f"page.items[{TXT}].atom.text === '감사 글'", 4)
        return (ok and over and ok2 and js("document.querySelector('#tedit').style.display === 'none'"),
                f"editor={ok} 자리={over} 저장={ok2} TXT={TXT} 편집칸={tr} 있어야 할 자리={exp} 글={js(f'JSON.stringify(page.items[{TXT}].atom.text)')[:40]}")
    step("G1 글상자 더블클릭 → 제자리 편집 → Ctrl+Enter 저장", g1)
    def g2():
        js(f"select([{TXT}], {TXT})"); key("Enter", code="Enter"); ok = wait("document.querySelector('#tedit').style.display !== 'none'", 3); key("Escape", code="Escape")
        return (ok and js("document.querySelector('#tedit').style.display === 'none'"), "")
    step("G2 Enter 로 편집 · Esc 취소", g2)
    def g3():
        js("select([])"); r = grect(PAS); dbl(r[0] + 10, r[1] + 10)
        ok = wait("!!editing && document.querySelector('#editbar').style.display !== 'none'", 4)
        key("Escape", code="Escape"); ok2 = wait("!editing", 4)
        return (ok and ok2, f"edit={ok} exit={ok2}")
    step("G3 요소 더블클릭 → 안 편집 모드 → Esc", g3)

    # ───────── H. 오른쪽 클릭 메뉴 ─────────
    def h1():
        js("select([])"); r = ensure(RECT); pt = pick(RECT) or (r[0] + 8, r[1] + 8); click(pt[0], pt[1], button="right")
        ok = wait("getComputedStyle(document.querySelector('#cmenu')).display !== 'none'", 3)
        n0 = n_items(); b = js("(() => { const el = [...document.querySelectorAll('#cmenu button')].find(b => /복제/.test(b.textContent)); if (!el) return null; const r = el.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()")
        if b: click(*b)
        ok2 = wait(f"page.items.length === {n0 + 1}", 4)
        if ok2: key("Delete", code="Delete"); wait(f"page.items.length === {n0}", 4)
        return (ok and ok2, f"menu={ok} 복제={ok2}")
    step("H1 오른쪽 클릭 메뉴 → 복제", h1)

    # ───────── I. 자·안내선·격자·확대·손 ─────────
    def i1():
        js("scrollToActive()"); time.sleep(0.5); rt = rect("#rt")
        if not rt or rt[3] == 0: return (False, "가로 자 안 보임")
        hit = at(rt[0] + 300, rt[1] + 5)
        n0 = js("((page.guides || {}).h || []).length"); drag(rt[0] + 300, rt[1] + 5, rt[0] + 300, rt[1] + 200)
        if js("((page.guides || {}).h || []).length") == n0: return (False, f"rt={rt} hit={hit} visible={visible('#rt')}")
        n1 = js("((page.guides || {}).h || []).length"); drawn = js("document.querySelectorAll('#guides .guide').length")
        return (n1 == n0 + 1 and drawn >= 1, f"guides {n0}→{n1} drawn={drawn}")
    step("I1 자에서 끌어 안내선 만들기", i1)
    def i2():
        click(*center("#tg-grid")); g1_ = js("document.querySelector('#paper').classList.contains('grid')"); click(*center("#tg-grid"))
        m0 = js("document.querySelector('#paper').classList.contains('mg')"); click(*center("#tg-mg"))
        m1 = js("document.querySelector('#paper').classList.contains('mg')"); click(*center("#tg-mg"))
        m2 = js("document.querySelector('#paper').classList.contains('mg')")
        return (g1_ and not js("document.querySelector('#paper').classList.contains('grid')") and m1 == (not m0) and m2 == m0, f"grid={g1_} 여백선 {m0}→{m1}→{m2}")
    step("I2 격자·여백 토글 버튼", i2)
    def i3():
        z0 = js("zoom"); ar = rect("#area"); p = (ar[0] + ar[2] / 2, ar[1] + ar[3] / 2); c.call("Input.dispatchMouseEvent", type="mouseWheel", x=p[0], y=p[1], deltaX=0, deltaY=-120, modifiers=CTRL); time.sleep(0.4)
        z1 = js("zoom"); click(*center("#zoomv")); time.sleep(0.3); z2 = js("zoom")
        r = rect("#zoom"); drag(r[0] + r[2] * 0.3, r[1] + r[3] / 2, r[0] + r[2] * 0.7, r[1] + r[3] / 2); z3 = js("zoom"); click(*center("#zoomv")); time.sleep(0.3)
        return (z1 > z0 and abs(z2 - 1) < 0.01 and z3 > 1.2, f"{z0}→{z1}→{z2} slider→{z3}")
    step("I3 Ctrl+휠 확대 · 100% 로 · 슬라이더", i3)
    def i4():
        js("setZoom(2)"); time.sleep(0.4); s0 = js("document.querySelector('#area').scrollLeft"); ar = rect("#area"); p = (ar[0] + ar[2] / 2, ar[1] + ar[3] / 2)
        c.call("Input.dispatchKeyEvent", type="keyDown", key=" ", code="Space"); drag(p[0], p[1], p[0] - 150, p[1] - 100); c.call("Input.dispatchKeyEvent", type="keyUp", key=" ", code="Space")
        s1 = js("document.querySelector('#area').scrollLeft"); js("setZoom(1)"); time.sleep(0.3)
        return (s1 > s0, f"scrollLeft {s0}→{s1}")
    step("I4 Space+끌기 손 도구", i4)
    def i5():
        js("setZoom(2)"); time.sleep(0.4); js("document.querySelector('#area').scrollTop = 100"); s0 = js("document.querySelector('#area').scrollTop"); ar = rect("#area"); p = (ar[0] + ar[2] / 2, ar[1] + ar[3] / 2)
        drag(p[0], p[1], p[0], p[1] - 120, button="middle"); s1 = js("document.querySelector('#area').scrollTop"); js("setZoom(1)"); time.sleep(0.3)
        js("scrollToActive()"); time.sleep(0.5)
        return (s1 > s0, f"scrollTop {s0}→{s1}")
    step("I5 가운데 버튼 끌기 손 도구", i5)

    # ───────── J. 레이어·속성 ─────────
    TXT = js("page.items.findIndex(it => it.atom && it.atom.t === 'text')"); RECT = js("page.items.findIndex(it => it.atom && it.atom.t === 'rect')")
    def j1():
        js("select([])"); time.sleep(0.3); rows = js("document.querySelectorAll('#side .layers .li').length")
        r = rect("#side .layers .li:nth-child(1)");
        if not r: return (False, f"레이어 줄 없음 rows={rows}")
        click(r[0] + r[2] / 2, r[1] + r[3] / 2); ok = wait("sel != null", 3)
        return (ok, f"rows={rows} sel={js('sel')}")
    step("J1 레이어 줄 클릭 → 선택", j1)
    def j2():
        i = js("sel"); eye = rect("#side .layers .li:nth-child(1) [data-eye]")
        if not eye: return (False, "눈 아이콘 없음")
        click(eye[0] + eye[2] / 2, eye[1] + eye[3] / 2); hid = wait(f"page.items[{i}].hide === true", 3); gone = wait(f"!gOf({i})", 4)
        eye = rect("#side .layers .li:nth-child(1) [data-eye]"); click(eye[0] + eye[2] / 2, eye[1] + eye[3] / 2); back = wait(f"!page.items[{i}].hide && !!gOf({i})", 4)
        return (hid and gone and back, f"hide={hid} gone={gone} back={back}")
    step("J2 레이어 눈 → 숨김 → 다시 보임", j2)
    def j3():
        js(f"select([{TXT}], {TXT})"); time.sleep(0.4); r = rect('#side input[data-it="x"]')
        if not r: return (False, "x 입력 없음")
        js("(() => { const i = document.querySelector('#side input[data-it=\"x\"]'); i.value = 77; i.dispatchEvent(new Event('change')); })()")
        ok = wait(f"page.items[{TXT}].x === 77", 3)
        js("(() => { const t = document.querySelector('#side textarea[data-a=\"text\"]'); t.value = '속성에서 고침'; t.dispatchEvent(new Event('change')); })()")
        ok2 = wait(f"page.items[{TXT}].atom.text === '속성에서 고침'", 3)
        return (ok and ok2, f"x={ok} text={ok2}")
    step("J3 속성 칸 (x · 글) 고치면 반영", j3)

    # ───────── K. 저장·다시 열기 ─────────
    def k1():
        snap0 = js("JSON.stringify(page.items)"); pid = js("page.id"); time.sleep(1.5); st = js("document.querySelector('#st').textContent")
        t0 = time.time(); c.call("Page.navigate", url=f"{BASE}/units?plan={PLAN}&page={pid}"); time.sleep(2)
        ok = wait("!!(page && document.querySelector('#svgwrap svg g[data-fi]'))", 40); took = round(time.time() - t0, 1)
        rec("K1b 링크로 열 때 3초 안에 그려진다", took < 3, f"{took}s (요소 {js('page && page.items.length')}개)")
        return (ok and js("JSON.stringify(page.items)") == snap0, f"same={js('JSON.stringify(page.items)') == snap0} st={st} n={js('page.items.length')}")
    step("K1 새로고침 후 그대로 (자동 저장)", k1)

    # ───────── L. 브랜드·원고·미리보기·검수·PDF ─────────
    def l1():
        click(*center("#s-skin-edit")); time.sleep(0.6); r = rect('input[data-col="cream"]')
        if not r: return (False, "색 입력 없음 (브랜드 창)")
        js("(() => { const i = document.querySelector('input[data-col=\"cream\"]'); i.value = '#ff0000'; i.dispatchEvent(new Event('input')); })()")
        ok = wait("document.querySelector('#svgwrap svg').innerHTML.includes('#ff0000')", 6)
        js("(() => { const i = document.querySelector('input[data-col=\"cream\"]'); i.value = '#f6f1e6'; i.dispatchEvent(new Event('input')); })()"); time.sleep(1)
        click(*center("#sheet-x")); time.sleep(0.3)
        return (ok and not visible(".sheet-bg.on"), "창 열고 색 → 캔버스 → 닫기")
    step("L1 브랜드 색 바꾸면 캔버스에 바로", l1)
    def l2():
        click(*center("#s-set-edit")); time.sleep(0.6); click(*center("#set-paste")); time.sleep(0.3)
        js("document.querySelector('#ms-text').value = '# 77\\nThis is a long enough English passage for the audit of the manuscript parser feature set.\\n윗글의 주제는?\\n① a ② b ③ c\\n답: ②'")
        click(*center("#ms-go")); ok = wait("LIB.sets.some(s => s.id === '77') && curSet === '77'", 8)
        ok2 = wait("document.querySelector('#svgwrap svg').innerHTML.includes('audit of the manuscript')", 8)
        if visible(".sheet-bg.on"): click(*center("#sheet-x")); time.sleep(0.3)
        return (ok and ok2, f"set={ok} shown={ok2}")
    step("L2 원고 붙여넣기 → 세트 → 캔버스에 그 원고", l2)
    def l3():
        click(*center("#p-preview")); ok = wait("document.querySelectorAll('#pvbody .sheet').length >= 1", 20)
        n = js("document.querySelectorAll('#pvbody .sheet').length"); click(*center("#pvclose")); return (ok and not visible("#pv"), f"sheets={n} info={js('document.querySelector(\"#pvinfo\").textContent')[:60]}")
    step("L3 📖 미리보기 → 면들이 그려지고 닫힌다", l3)
    def l4():
        click(*center("#p-check")); ok = wait("!!document.querySelector('#chk .it')", 20); t = js("(document.querySelector('#chk h4') || {}).textContent || ''")
        b = js("(() => { const el = document.querySelector('#chk button'); if (!el) return null; const r = el.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()")
        if b: click(*b)
        return (ok and not js("!!document.querySelector('#chk')"), t[:60])
    step("L4 ✓ 검수 패널 → 닫기", l4)
    def l5():
        js("window.__opened = null"); click(*center("#p-pdf")); time.sleep(0.3); u = js("window.__opened"); ok = False
        if u:
            try:
                r = urllib.request.urlopen(BASE + u, timeout=120); ok = r.status == 200 and r.headers.get("Content-Type", "").startswith("application/pdf")
            except Exception as e:
                return (False, str(e)[:100])
        js("window.__opened = null"); click(*center("#p-print")); time.sleep(0.3); u2 = js("window.__opened"); ok2 = False
        if u2:
            try:
                r = urllib.request.urlopen(BASE + u2, timeout=300); ok2 = r.status == 200
            except Exception as e:
                return (False, "print " + str(e)[:100])
        return (ok and ok2, f"pdf={u and u[:40]} print={ok2}")
    step("L5 ⬇ PDF · 🖨 인쇄용 → PDF 가 나온다", l5)

    # ───────── M. 요소로 저장 · 설명으로 만들기 ─────────
    def m1():
        js(f"select([{TXT}, {RECT}], {RECT})"); time.sleep(0.4); nb = js("LIB.blocks.length")
        b = center("#t-up") if visible("#t-up") else None
        if not b: return (False, "★ 요소로 저장 버튼 안 보임")
        click(*b); time.sleep(1.0)
        k = js("(() => { const d = [...document.querySelectorAll('#sbody [data-kind]')].find(x => x.dataset.kind !== '__new'); if (!d) return null; const r = d.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()")
        if k:
            click(*k)                                            # ★ 요소로 저장 → 유형 고르기 창에서 하나 고른다
        ok = wait(f"LIB.blocks.length === {nb + 1}", 12)
        return (ok and js("page.items.some(it => it.block && it.block.startsWith('x'))") or ok, f"blocks {nb}→{js('LIB.blocks.length')}")
    step("M1 둘 골라 ★ 요소로 저장 → 팔레트에 새 요소", m1)
    def m2():
        r = rect("#ai");
        if not r: return (False, "설명 입력 없음")
        js("document.querySelector('#ai').value = '파란 제목 띠와 번호 원'"); click(*center("#btn-ai")); ok = wait("document.querySelector('#ainote') && /만드|없|오류|키|error/i.test(document.querySelector('#ainote').textContent) || LIB.blocks.some(b => b.id.startsWith('ai_'))", 60)
        return (ok, js("(document.querySelector('#ainote') || {}).textContent || ''")[:80])
    step("M2 설명으로 요소 만들기 (클로드) — 응답 또는 안내", m2)

    # ───────── N. 세로로 이어 보기 · 도형 모양 ─────────
    def n1():
        if not js("!!view.flow"): click(*center("#tg-flow")); time.sleep(0.6)
        if js("docPages().length") < 2: click(*center("#f-addpg")); wait("docPages().length >= 2", 10)
        js("scrollToActive()"); time.sleep(0.6)
        slots = js("document.querySelectorAll('#pages .pslot').length"); n = js("docPages().length")
        i0 = js("idx()")
        js("(() => { const a = document.querySelector('#area'); a.scrollTop += a.clientHeight + 20; })()")
        ok = wait(f"idx() !== {i0}", 8)
        paper_in = js("!!document.querySelector('#pages .pslot.cur #paper')")
        return (ok and slots == n and paper_in, f"칸 {slots}개(쪽 {n}) · {i0 + 1}쪽에서 굴리니 {js('idx()') + 1}쪽 · 지면이 그 칸에={paper_in}")
    step("N1 굴리면 다음 쪽 (세로 이어 보기)", n1)
    def n2():
        js("setZoom(0.5)"); time.sleep(0.8); js("scrollToActive()"); time.sleep(0.7)
        cur = js("String(idx())")
        seen = js("(() => { const a = document.querySelector('#area').getBoundingClientRect(); return [...document.querySelectorAll('#pages .pslot')].filter(d => { const r = d.getBoundingClientRect(); return Math.min(r.bottom, a.bottom) - Math.max(r.top, a.top) > 60; }).map(d => d.dataset.i); })()")
        other = [x for x in seen if x != cur]
        if not other:
            js("setZoom(1)"); return (False, f"줄여도 이웃 칸이 안 보인다 (보임={seen} 지금={cur})")
        r, a = rect(f'#pages .pslot[data-i="{other[0]}"]'), rect("#area")
        top, bot = max(r[1], a[1] + 4), min(r[1] + r[3], a[1] + a[3] - 4)
        click(r[0] + r[2] / 2, (top + bot) / 2)
        ok = wait(f"idx() === {int(other[0])}", 6); at2 = js("idx()")
        js("setZoom(1)"); time.sleep(0.6)
        return (ok, f"50% 로 줄이니 {len(seen)}칸 보임 · 이웃 눌러 {at2 + 1}쪽")
    step("N2 이웃 쪽 눌러서 열기", n2)
    def n3():
        vis = "[...document.querySelectorAll('#pages .prow')].filter(d => getComputedStyle(d).display !== 'none').length"
        click(*center("#tg-flow")); time.sleep(0.7); one = js(vis)
        click(*center("#tg-flow")); time.sleep(0.7); many = js(vis)
        return (one == 1 and many > 1, f"끄면 {one}줄(지금 쪽·펼침면만) · 켜면 {many}줄")
    step("N3 연속 껐다 켜기", n3)
    def n4():
        click(*center('#trail [data-tool="path"]')); time.sleep(0.5)
        btns = js("[...document.querySelectorAll('#thint [data-shp]')].map(b => b.textContent)")
        if not btns: return (False, "모양 고르개가 안 나온다")
        b = center('#thint [data-shp]:nth-child(4)')                      # 별
        nm = js("(document.querySelector('#thint [data-shp]:nth-child(4)') || {}).textContent")
        click(*b); time.sleep(0.2)
        n0 = n_items(); pr = rect("#paper"); sc = js("scale")
        drag(pr[0] + 40 * sc, pr[1] + 150 * sc, pr[0] + 70 * sc, pr[1] + 175 * sc, steps=8)
        ok = wait(f"page.items.length === {n0 + 1}", 6)
        d = js("(() => { const it = page.items[page.items.length - 1]; return it && it.atom ? it.atom.d || '' : ''; })()")
        star = js("(() => { const it = page.items[page.items.length - 1]; return !!(it && it.atom && it.atom.t === 'path'); })()")
        return (ok and star and d.startswith("M0.5 0 L0.62"), f"모양 {len(btns)}개 · 고른 것={nm} · 그린 것 d={d[:22]}")
    step("N4 도형 — 모양 고르고 그리면 그 모양", n4)

    def n5():
        while js("docPages().length") < 3:
            click(*center("#f-addpg")); time.sleep(1.2)
        if not js("!!view.spread"): click(*center("#tg-spread")); time.sleep(1.2)
        js("scrollToActive()"); time.sleep(0.8)
        rows = js("[...document.querySelectorAll('#pages .prow')].map(r => [...r.querySelectorAll('.pslot')].map(d => +d.dataset.i + 1))")
        blank = js("!!document.querySelector('#pages .prow:first-child .pblank')")
        two = any(len(r) == 2 for r in rows)
        return (blank and two and rows[0] == [1], f"줄 {rows} · 1쪽 오른쪽(빈 자리)={blank}")
    step("N5 펼침면 — 2·3쪽이 한 장, 1쪽은 오른쪽", n5)
    def n6():
        js("(() => { const r = document.querySelector('#pages .prow:nth-child(2) .pslot'); if (r) openPage(byId('pages')[r.dataset.id], false, +r.dataset.i); })()"); time.sleep(1.2)
        row = js("[...document.querySelector('#pages .prow.cur').querySelectorAll('.pslot')].map(d => +d.dataset.i + 1)")
        o = rect("#pages .prow.cur .pslot:not(.cur)")
        if not o: return (False, f"맞은편 쪽이 없다 (줄 {row})")
        i0 = js("idx()"); click(o[0] + o[2] / 2, o[1] + o[3] / 2)
        ok = wait(f"idx() !== {i0}", 6)
        paper_here = js("!!document.querySelector('#pages .prow.cur .pslot.cur #paper')")
        return (ok and paper_here, f"줄 {row} · 맞은편 눌러 {js('idx()') + 1}쪽 · 지면이 그 칸에={paper_here}")
    step("N6 맞은편 쪽 눌러 고치기", n6)
    def n7():
        w0 = js("Math.round(document.querySelector('.paper').getBoundingClientRect().width)")
        click(*center("#tg-spread")); time.sleep(1.5)
        one = js("document.querySelectorAll('#pages .prow:first-child .pslot').length")
        board1 = js("(document.querySelector('#svgwrap svg') || {}).dataset ? (document.querySelector('#svgwrap svg').dataset.board || '0') : '?'")
        click(*center("#tg-spread")); time.sleep(1.5)
        two = js("[...document.querySelectorAll('#pages .prow')].some(r => r.querySelectorAll('.pslot').length === 2)")
        board2 = js("(document.querySelector('#svgwrap svg') || {}).dataset ? (document.querySelector('#svgwrap svg').dataset.board || '0') : '?'")
        return (one == 1 and two and float(board1) > 0 and float(board2) == 0,
                f"끄면 한 줄 한 쪽(대지 {board1}mm) · 켜면 두 쪽(대지 {board2}mm) · 지면 폭 {w0}")
    step("N7 펼침 껐다 켜기 (끄면 대지가 돌아온다)", n7)

    def n8():
        js("select([])"); time.sleep(0.5)
        b = center("#s-facing")
        if not b: return (False, "문서 칸에 「페이지 마주보기」가 없다")
        if not js("!!view.spread"): click(*center("#tg-spread")); time.sleep(1.0)
        rows0 = js("[...document.querySelectorAll('#pages .prow')].map(r => r.querySelectorAll('.pslot').length)")
        click(*b); ok = wait("plan.facing === false", 6); time.sleep(1.5)          # 문서 설정에서 끄기
        rows1 = js("[...document.querySelectorAll('#pages .prow')].map(r => r.querySelectorAll('.pslot').length)")
        off = js("!!document.querySelector('#tg-spread').disabled")
        board = js("((document.querySelector('#svgwrap svg') || {}).dataset || {}).board || '0'")
        js("select([])"); time.sleep(0.4); click(*center("#s-facing")); wait("plan.facing === true", 6); time.sleep(1.5)
        rows2 = js("[...document.querySelectorAll('#pages .prow')].map(r => r.querySelectorAll('.pslot').length)")
        return (ok and max(rows0) == 2 and max(rows1) == 1 and off and float(board) > 0 and max(rows2) == 2,
                f"켬 {rows0} → 끔 {rows1}(펼침 단추 꺼짐={off}, 대지 {board}mm) → 다시 켬 {rows2}")
    step("N8 문서 설정 「페이지 마주보기」 끄고 켜기 (문서에 저장)", n8)

    # ───────── O. 요소 카테고리 ─────────
    def into(sel):                      # 요소 패널은 길어서 스크롤한다 — 보이게 한 뒤 누른다
        js(f"(() => {{ const el = document.querySelector({json.dumps(sel)}); if (el) el.scrollIntoView({{block: 'center'}}); }})()")
        time.sleep(0.4); return rect(sel)
    def hover(sel):                     # ✎ ✕ ▾ 는 올려야 나온다
        r = into(sel)
        if not r: return None
        mouse("mouseMoved", r[0] + r[2] / 2, r[1] + r[3] / 2); time.sleep(0.35); return r
    def headsel(word):                  # 그 이름을 가진 카테고리 머리
        i = js(f"[...document.querySelectorAll('#pbody h3')].findIndex(x => x.textContent.replace(/[▾▸✎✕]/g, '').includes({json.dumps(word)}))")
        return f"#pbody h3:nth-of-type({i + 1})" if i >= 0 else None
    def o1():
        js("window.__promptv = '감사분류'")
        r = into("#g-new")
        if not r: return (False, "＋ 카테고리 단추가 없다")
        n0 = js("LIB.groups.length"); click(r[0] + r[2] / 2, r[1] + r[3] / 2); ok = wait(f"LIB.groups.length === {n0 + 1}", 8)
        js("window.__promptv = null")
        head = js("[...document.querySelectorAll('#pbody h3')].map(h => h.textContent.replace(/[▾▸✎✕]/g, ''))")
        return (ok and any("감사분류" in h for h in head), f"카테고리 {n0}→{js('LIB.groups.length')} · 줄 {head}")
    step("O1 ＋ 카테고리 로 만들기", o1)
    def o2():
        gid = js("(LIB.groups.find(g => g.name === '감사분류') || {}).id")
        if not hover("#pbody .card"): return (False, "카드가 없다")
        c = center("#pbody .card .cact")
        if not c: return (False, "카드에 ▾ 가 없다")
        click(*c); time.sleep(0.5)
        b = js("(() => { const el = [...document.querySelectorAll('#gmenu button')].find(x => x.textContent.startsWith('감사분류')); if (!el) return null; const r = el.getBoundingClientRect(); return [r.left + r.width / 2, r.top + r.height / 2]; })()")
        if not b: return (False, "옮기기 메뉴에 그 카테고리가 없다")
        click(*b); ok = wait(f"LIB.blocks.some(b => b.group === {json.dumps(gid)})", 8)
        moved = js(f"LIB.blocks.filter(b => b.group === {json.dumps(gid)}).map(b => b.name)")
        return (ok, f"옮긴 요소 {moved} → {gid}")
    step("O2 카드 ▾ 로 다른 카테고리에 옮기기", o2)
    def o3():
        sel = headsel("감사분류")
        if not sel: return (False, "그 카테고리 줄이 없다")
        js("window.__promptv = '감사분류2'"); hover(sel)
        b = center(sel + " [data-gren]")
        if not b: return (False, "✎ 가 안 나온다")
        click(*b); ok = wait("LIB.groups.some(g => g.name === '감사분류2')", 8)
        js("window.__promptv = null")
        return (ok, f"이름 {js('JSON.stringify(LIB.groups.map(g => g.name))')}")
    step("O3 카테고리 이름 바꾸기 (✎)", o3)
    def o4():
        gid = js("(LIB.groups.find(g => g.name === '감사분류2') || {}).id")
        sel = headsel("감사분류2")
        if not sel: return (False, "그 카테고리 줄이 없다")
        hover(sel); b = center(sel + " [data-gdel]")
        if not b: return (False, "✕ 가 안 나온다")
        click(*b); ok = wait("!LIB.groups.some(g => g.name === '감사분류2')", 8)
        alive = js(f"LIB.blocks.filter(b => b.group === {json.dumps(gid)}).length")
        head = js("[...document.querySelectorAll('#pbody h3')].map(h => h.textContent.replace(/[▾▸✎✕]/g, ''))")
        js(f"(async () => {{ for (const b of LIB.blocks.filter(b => b.group === {json.dumps(gid)})) {{ delete b.group; await api('/api/units/blocks', b); }} }})()"); time.sleep(1.2)
        return (ok and alive >= 1 and any("내가 만든 요소" in h for h in head),
                f"지운 뒤 줄 {head} · 그 안에 있던 요소 {alive}개는 살아서 「내가 만든 요소」로")
    step("O4 카테고리 지우기 (✕) — 요소는 안 지운다", o4)

    def o5():
        js("localStorage.removeItem('units.gfold')")
        sel = "#pbody h3.fold"
        n = js(f"document.querySelectorAll({json.dumps(sel)}).length")
        if n < 2: return (False, f"접을 수 있는 줄이 {n}개")
        r = into("#pbody h3.fold:nth-of-type(2)")
        if not r: return (False, "두 번째 줄이 없다")
        vis0 = js("[...document.querySelectorAll('#pbody .grid, #pbody .atoms5')].filter(g => getComputedStyle(g).display !== 'none').length")
        click(r[0] + r[2] / 2, r[1] + r[3] / 2); time.sleep(0.5)
        vis1 = js("[...document.querySelectorAll('#pbody .grid, #pbody .atoms5')].filter(g => getComputedStyle(g).display !== 'none').length")
        saved = js("localStorage.getItem('units.gfold')")
        click(r[0] + r[2] / 2, r[1] + r[3] / 2); time.sleep(0.5)                 # 다시 펴기
        vis2 = js("[...document.querySelectorAll('#pbody .grid, #pbody .atoms5')].filter(g => getComputedStyle(g).display !== 'none').length")
        return (vis1 == vis0 - 1 and vis2 == vis0 and saved not in (None, "[]"),
                f"줄 {n}개 · 접으니 보이는 묶음 {vis0}→{vis1}, 펴니 {vis2} · 기억 {saved}")
    step("O5 카테고리 접고 펴기 (기억한다)", o5)

    # ───────── P. 인디자인 개체 속성 (오른쪽 패널에 다 있나) ─────────
    WANT_SHAPE = ["w", "h", "fill", "stroke.color", "stroke.w", "stroke.align", "stroke.join", "stroke.tint", "dashpat",
                  "grad", "rotate", "opacity", "tint", "flip", "skewx", "skewy", "scalex", "scaley",
                  "fx.blend", "fx.shadow.x", "fx.shadow.y", "fx.shadow.blur", "fx.shadow.inner", "fx.glow.blur", "fx.glow.inner", "fx.feather"]
    WANT_TEXT = ["text", "bindsel", "style", "font", "size", "color", "align", "leading", "tracking", "indent", "indent_first",
                 "indent_right", "space_before", "space_after", "inset", "valign", "columns", "gutter",
                 "bullet", "tab", "shade", "rule_above.w", "rule_above.color", "rule_above.offset", "rule_below.w",
                 "first_baseline", "baseline", "kerning", "h_scale", "v_scale", "auto_size"]

    def setf(k, v):
        return js(f"""(() => {{ const el = document.querySelector('#side [data-a="{k}"]'); if (!el) return '{k}';
            if (el.type === 'checkbox') el.checked = {str(bool(v)).lower() if isinstance(v, bool) else 'true'};
            else el.value = {json.dumps(v)};
            el.dispatchEvent(new Event('change')); return ''; }})()""")

    def p1():
        js("addAtom('rect', {x: 30, y: 200})"); time.sleep(1.2)
        js("(() => { const i = page.items.length - 1; select([i], i); })()"); time.sleep(0.8)
        have = js("[...document.querySelectorAll('#side [data-a]')].map(x => x.dataset.a)")
        miss = [k for k in WANT_SHAPE if k not in have]
        for k, v in [("stroke.align", "inside"), ("dashpat", "2, 1"), ("stroke.join", "round"), ("stroke.tint", "60"),
                     ("tint", "50"), ("flip", "h"), ("skewx", "10"), ("scalex", "120"), ("fx.blend", "multiply"),
                     ("fx.shadow.x", "1"), ("fx.shadow.y", "1"), ("fx.shadow.blur", "1"), ("fx.glow.blur", "2"), ("fx.feather", "0.5")]:
            setf(k, v)
        time.sleep(2.0)
        svg = js("document.querySelector('#svgwrap svg').innerHTML")
        drawn = {"획 안쪽": "clipPath" in svg, "점선": "stroke-dasharray" in svg, "그림자": "feDropShadow" in svg,
                 "혼합": "mix-blend-mode" in svg, "기울이기": "skewX" in svg, "뒤집기": "scale(-1" in svg}
        at = js("JSON.stringify(page.items[page.items.length - 1].atom)")
        js("(() => { page.items.pop(); select([]); save(); render(); })()"); time.sleep(1.0)
        return (not miss and all(drawn.values()), f"없는 칸 {miss or '없음'} · 그려짐 {drawn} · 원자 {at[:120]}")
    step("P1 도형 속성 — 획 정렬·점선·색조·뒤집기·기울이기·효과", p1)

    def p2():
        js("addAtom('text', {x: 30, y: 210})"); time.sleep(1.2)
        js("(() => { const i = page.items.length - 1; select([i], i); })()"); time.sleep(0.8)
        have = js("[...document.querySelectorAll('#side [data-a]')].map(x => x.dataset.a)")
        miss = [k for k in WANT_TEXT if k not in have]
        for k, v in [("bullet", "decimal"), ("tab", "8"), ("rule_above.w", "0.8"), ("rule_below.w", "0.4"),
                     ("first_baseline", "2"), ("baseline", "1"), ("kerning", "none"), ("h_scale", "90"), ("v_scale", "105")]:
            setf(k, v)
        js("(() => { const el = document.querySelector('#side [data-a=\"auto_size\"]'); el.checked = false; el.dispatchEvent(new Event('change')); })()")
        time.sleep(2.0)
        svg = js("document.querySelector('#svgwrap svg').innerHTML")
        drawn = {"글머리": "list-item" in svg, "단락선": "border-top" in svg, "탭": "tab-size" in svg,
                 "커닝": "font-kerning" in svg, "장평": "transform:scale" in svg}
        at = js("JSON.stringify(page.items[page.items.length - 1].atom)")
        js("(() => { page.items.pop(); select([]); save(); render(); })()"); time.sleep(1.0)
        return (not miss and all(drawn.values()), f"없는 칸 {miss or '없음'} · 그려짐 {drawn} · 원자 {at[:120]}")
    step("P2 글 속성 — 단락 경계선·음영·글머리·탭·장평·기준선·커닝", p2)

    def p3():
        js("addAtom('rect', {x: 20, y: 120})"); time.sleep(1.2)
        js("(() => { const i = page.items.length - 1; select([i], i); })()"); time.sleep(0.8)
        have = js("[...document.querySelectorAll('#side [data-a]')].map(x => x.dataset.a)")
        want = ["corner", "stroke.gap_color", "origin", "nonprint", "overprint", "wrap.mode", "wrap.offset", "wrap.side"]
        miss = [k for k in want if k not in have]
        for k, v in [("corner", "bevel"), ("origin", "tl"), ("wrap.mode", "bbox"), ("wrap.offset", "2"), ("dashpat", "3, 2")]:
            setf(k, v)
        time.sleep(1.6)
        at = js("JSON.stringify(page.items[page.items.length - 1].atom)")
        svg = js("document.querySelector('#svgwrap svg').innerHTML")
        js("(() => { page.items.pop(); select([]); save(); render(); })()"); time.sleep(1.0)
        return (not miss and "bevel" in at and "wrap" in at and "stroke-dasharray" in svg,
                f"없는 칸 {miss or '없음'} · 원자 {at[:110]}")
    step("P3 도형 — 모서리 모양·기준점·감싸기·비인쇄·간격 색", p3)

    def p4():
        js("addAtom('text', {x: 20, y: 150})"); time.sleep(1.2)
        js("(() => { const i = page.items.length - 1; select([i], i); })()"); time.sleep(0.8)
        have = js("[...document.querySelectorAll('#side [data-a]')].map(x => x.dataset.a)")
        want = ["drop_cap.lines", "drop_cap.chars", "case", "column_rule.w", "underline.w", "underline.style", "strike.w"]
        miss = [k for k in want if k not in have]
        for k, v in [("drop_cap.lines", "3"), ("case", "small"), ("columns", "2"), ("column_rule.w", "0.5"),
                     ("underline.w", "0.6"), ("underline.style", "wavy")]:
            setf(k, v)
        time.sleep(1.8)
        svg = js("document.querySelector('#svgwrap svg').innerHTML")
        drawn = {"드롭캡": "float:left" in svg, "작은대문자": "small-caps" in svg,
                 "단 사이 선": "column-rule" in svg, "물결 밑줄": "wavy" in svg}
        at = js("JSON.stringify(page.items[page.items.length - 1].atom)")
        js("(() => { page.items.pop(); select([]); save(); render(); })()"); time.sleep(1.0)
        return (not miss and all(drawn.values()), f"없는 칸 {miss or '없음'} · 그려짐 {drawn} · 원자 {at[:110]}")
    step("P4 글 — 드롭캡·단 사이 선·작은대문자·밑줄 옵션", p4)

    def p5():
        js("addAtom('rect', {x: 20, y: 120})"); time.sleep(1.2)
        js("(() => { const i = page.items.length - 1; select([i], i); })()"); time.sleep(0.8)
        have = js("[...document.querySelectorAll('#side [data-a]')].map(x => x.dataset.a)")
        want = ["ostyle", "layer", "fx.bevel.size", "fx.bevel.depth", "fx.bevel.angle", "fx.satin.blur"]
        miss = [k for k in want if k not in have]
        for k, v in [("fx.bevel.size", "1"), ("fx.bevel.depth", "1.5"), ("fx.satin.blur", "1.5")]:
            setf(k, v)
        time.sleep(1.8)
        svg = js("document.querySelector('#svgwrap svg').innerHTML")
        drawn = {"엠보스": "feSpecularLighting" in svg, "새틴": 'operator="xor"' in svg}
        js("window.__promptv = '감사 박스'")
        b = center("#s-ostyle-new")
        if b:
            click(*b); wait("!!(skin().obj_styles && skin().obj_styles['감사 박스'])", 8)
        js("window.__promptv = null")
        st = js("Object.keys(skin().obj_styles || {})")
        ost = js("page.items[page.items.length - 1].atom.ostyle")
        js("(() => { page.items.pop(); select([]); save(); render(); })()"); time.sleep(1.0)
        return (not miss and all(drawn.values()) and "감사 박스" in st and ost == "감사 박스",
                f"없는 칸 {miss or '없음'} · {drawn} · 개체 스타일 {st} · 요소에 붙음 {ost}")
    step("P5 도형 — 개체 스타일 저장·엠보스·새틴", p5)

    def p6():
        js("select([])"); time.sleep(0.6)
        need = [k for k in ("s-lay-new", "s-grid-start", "s-grid-step") if not js(f"!!document.querySelector('#{k}')")]
        if need:
            return (False, f"지면 칸 없음 {need}")
        js("window.__promptv = '앞면'")
        click(*center("#s-lay-new")); ok1 = wait("(page.layers || []).length >= 1", 8)
        js("window.__promptv = null")
        setf("nothing", "")                                              # (no-op)
        js("(() => { const gs = document.querySelector('#s-grid-start'), gp = document.querySelector('#s-grid-step'); gs.value = 20; gs.dispatchEvent(new Event('change')); gp.value = 6; gp.dispatchEvent(new Event('change')); })()")
        ok2 = wait("!!(page.baseline_grid && page.baseline_grid.step === 6)", 8)
        js("addAtom('rect', {x: 20, y: 120})"); time.sleep(1.2)
        js("(() => { const i = page.items.length - 1; select([i], i); page.items[i].atom.fill = '$sel'; const el = document.querySelector('#side [data-a=\"layer\"]'); el.value = page.layers[0].id; el.dispatchEvent(new Event('change')); })()")
        time.sleep(1.8)
        col = js("skin().tokens.color.sel")
        seen = js(f"document.querySelector('#svgwrap svg').innerHTML.includes({json.dumps(col)})")
        js("select([])"); time.sleep(0.6)
        js("(() => { const c = document.querySelector('#side [data-lay$=\":hide\"]'); c.checked = true; c.dispatchEvent(new Event('change')); })()")
        time.sleep(2.0)
        gone = not js(f"document.querySelector('#svgwrap svg').innerHTML.includes({json.dumps(col)})")
        js("(() => { page.items.pop(); page.layers = []; delete page.baseline_grid; select([]); save(); render(); })()"); time.sleep(1.2)
        return (ok1 and ok2 and seen and gone,
                f"레이어 만들기={ok1} · 격자 20/6={ok2} · 넣으면 보임={seen} · 숨기면 사라짐={gone}")
    step("P6 지면 — 레이어 만들기·숨기기 · 기준선 격자", p6)

    def p7():
        js("addAtom('text', {x: 20, y: 150})"); time.sleep(1.2)
        js("(() => { const i = page.items.length - 1; select([i], i); })()"); time.sleep(0.8)
        have = js("[...document.querySelectorAll('#side [data-a]')].map(x => x.dataset.a)")
        want = ["tabspec", "hyphenate", "justify_mode", "word_spacing", "snap_baseline", "clip"]
        miss = [k for k in want if k not in have and k != "clip"]          # clip 은 그림 원자에만
        setf("text", "가\t나\t다")                                        # 탭 자리를 보려면 글에 탭이 있어야 한다
        for k, v in [("tabspec", "30 right ., 60 center"), ("justify_mode", "letter"), ("word_spacing", "120")]:
            setf(k, v)
        js("(() => { const h = document.querySelector('#side [data-a=\"hyphenate\"]'); h.checked = true; h.dispatchEvent(new Event('change')); })()")
        time.sleep(1.8)
        at = js("JSON.stringify(page.items[page.items.length - 1].atom)")
        svg = js("document.querySelector('#svgwrap svg').innerHTML")
        drawn = {"탭 자리": "min-width:30.000px" in svg, "리더": "......" in svg, "하이픈": "hyphens:auto" in svg}
        anc = js("(() => { const s = document.querySelector('#s-anc-part'); if (!s || !LIB.parts.length) return false; s.value = LIB.parts[0].id; document.querySelector('#s-anc-add').click(); return true; })()")
        time.sleep(2.0)
        has_anc = js("(() => { const a = page.items[page.items.length - 1].atom; return Array.isArray(a.text) && a.text.some(r => r && r.anc); })()")
        js("(() => { page.items.pop(); select([]); save(); render(); })()"); time.sleep(1.0)
        return (not miss and all(drawn.values()) and anc and has_anc,
                f"없는 칸 {miss or '없음'} · {drawn} · 글 안 개체={has_anc} · 원자 {at[:90]}")
    step("P7 글 — 탭 자리·리더·하이픈·양끝맞춤·글 안 개체", p7)

    print("JS 오류:", errs())
    # 정리 — 감사 문서 지우기
    js("(async () => { for (const p of docPages()) { await api('/api/units/pages', {id: p.id}, 'DELETE'); } await api('/api/units/plans', {id: plan.id}, 'DELETE'); await api('/api/units/sets', {id: '77'}, 'DELETE'); })()"); time.sleep(2)
finally:
    proc.terminate()
    ok = sum(1 for r in R if r[1]); print(f"\n== {ok}/{len(R)} PASS ==")
    for name, okk, note in R:
        if not okk: print("FAIL", name, "|", note)
    json.dump(R, open(SP + "/audit_result.json", "w"), ensure_ascii=False, indent=1)
