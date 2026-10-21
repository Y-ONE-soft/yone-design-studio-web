"""상일보카 01 — 잇기 · 책 만들기(기능 테스트) · 편집기 제작 등록 · 맞대기 (docs/편집기_재현/절차.md 「★ 템플릿 등록 — 네 단계」 3 · 4).

    python3 tests/e2e/replay/상일보카/join.py            (JOIN_REGISTER=0 이면 등록 없이 잇기 · 책 만들기만)
    → ~/Downloads/편집기재현/상일보카@합본/ (rec.log · 책.pdf · 책.json · 맞대기 결과)

잇기 — 면마다 검사를 통과한 문서(replay.py 상일보카@<면> check 데이터, 16면)를 「문서 파일 내보내기」 묶음으로 꺼내, 빈 편집기에서
  「문서 파일 가져오기」(첫 묶음은 새 문서로, 나머지는 이 문서 끝에)로 면 차례(구성.json 1 → 16)대로 잇는다. 이은 뒤 편집기에서(사람이 템플릿을 손보듯):
  · 펼침면 면(두 쪽)의 오른쪽 쪽 이름 — 「빈 면 2」 → 「<면> 오른쪽」(넘치면 더할 페이지 목록에서 고르려고)
  · 「펼침면 상위 페이지」 — 펼침면 면의 왼쪽 쪽에서 켠다(레코드 하나가 두 쪽에 찍힌다)
  · 본문 펼침면(5 · 7 · 10 · 12 · 15)의 글상자를 첫 펼침면(4 · 6 · 9 · 11 · 14) 이야기 끝에 연결(텍스트 스레드) — 면마다 따로 검사해
    이야기가 따로였다. 본문 펼침면은 넘친 글을 받는 면(인디자인: 스마트 텍스트 리플로우가 더하는 페이지의 상위 페이지)
  · 스마트 텍스트 리플로우 — 더할 페이지: 첫 펼침면 오른쪽(정답은 첫 면) → 본문 왼쪽 → 본문 오른쪽 → 본문 왼쪽 …
  · 러닝 헤드 — 본문 펼침면의 원고 자리(작은 DAY 번호 · 책 이름 · 꼬리 DAY · 옆 탭) — 더한 페이지에도 그 DAY 값
  · MEMO 면 분류 「MEMO」(자리 없는 면 — 원고 덩어리 {"구분": "MEMO"} 가 고른다)
책 만들기(기능 테스트) — 원본 원고 전체(원본 차례 덩어리 — 파트 간지 · 차례 · DAY · MEMO · 구간 · 정답)를 {원고: [레코드 …]} 로 넣어 그리고
  원고 넣기(빈 자리 · 틀에 없는 자리 0) · 덩어리마다 고른 면 · 넘쳐 더한 쪽을 본다. 원본과 같은 쪽 수를 맞추는 검사가 아니다 — 쪽 수 차이는 적어 둔다.
8 편집기 제작 등록 — 면마다 견본 원고(SAMPLE — 5단계 검사 견본 쪽의 원고)를 넣고 「관리에 등록」(단어장 폴더) → 원본 PDF 를 템플릿에 붙인다.
9 맞대기 — 등록 PDF 쪽마다 그 면의 요소 목록(5단계 elems.json)으로 원본 견본 쪽과 다시 판정(원고 요소 · 쪽 번호는 들어갔나만).
"""
import json, os, re, shutil, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
E2E = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, E2E)
sys.path.insert(0, HERE)
from mkpage import S, F, open_doc, put_content                          # noqa: E402
from cdp import free_port                                                 # noqa: E402
import common as C                                                        # noqa: E402
import entries as EN                                                      # noqa: E402
import face_pyo, face_pa, face_more, face_vv, face_wb, face_dap           # noqa: E402  (원고 읽기 — 면 대본과 같은 함수)

PY = sys.executable
PORT = int(os.environ.get("REPLAY_PORT") or 0) or free_port()
BASE = f"http://127.0.0.1:{PORT}"
CACHE = os.path.expanduser("~/.cache/yone-replay")
OUT = os.path.expanduser("~/Downloads/편집기재현/상일보카@합본")
DATA = os.path.join(CACHE, "상일보카@합본", "catalog")
NAME = C.NAME
UNITS = [str(n) for n in range(1, 17)]                                   # 가져올 문서(면 검사 판) 차례 — 구성.json 1 → 16
if os.environ.get("JOIN_UNITS"):                                         # 시험용 — 면 일부만(검사 중인 면을 빼고 잇기 단계를 미리 돌려 볼 때)
    UNITS = os.environ["JOIN_UNITS"].split(",")
STATE = json.load(open(os.path.join(HERE, "상태.json"), encoding="utf-8"))
REF = os.path.join(REPO, STATE["ref"])
FACES = json.load(open(os.path.join(REPO, "catalog", "vocab", "designs", "xb3c27799", "faces.json"), encoding="utf-8"))["faces"]
LABEL = {p: f["label"] for f in FACES for p in f["pages"]}
# 첫 면 → (본문 면, 흐름 자리). 본문 면은 첫 면 이야기를 이어 받는다
FLOWS = {"4": ("5", face_pyo.ENTRY), "6": ("7", face_pa.ENTRY), "9": ("10", face_vv.VV), "11": ("12", face_wb.FLOW), "14": ("15", face_dap.ENTRY)}
FLOWS = {a: b for a, b in FLOWS.items() if a in UNITS and b[0] in UNITS}
RUN = ("작은 DAY 번호", "책 이름", "꼬리 DAY", "옆 탭")                    # 본문 펼침면 러닝 헤드 자리
DOCNAME = {"more with · 첫 펼침면": "more with · 펼침면"}                   # 면 목록 이름 → 면 문서의 쪽 이름(대본이 붙인 이름이 다른 것)
BODY = {"표제어 · 첫 펼침면": "표제어 · 본문 펼침면", "파생어 & 연관어휘 · 첫 펼침면": "파생어 & 연관어휘 · 본문 펼침면",
        "VOCA vs. VOCA · 첫 펼침면": "VOCA vs. VOCA · 본문 펼침면", "워크북 · 첫 펼침면": "워크북 · 본문 펼침면",
        "정답 첫 면": "정답 · 본문 펼침면", "more with · 첫 펼침면": None}


def unit_dir(g):
    """그 면의 마지막 통과 판 — 사람 조작 판 · 바로 넣기 판 중 나중 것"""
    best = None
    for u in (f"상일보카@{g}", f"상일보카@{g}~바로"):
        try:
            v = json.load(open(os.path.expanduser(f"~/Downloads/편집기재현/{u}/판정.json"), encoding="utf-8"))
        except Exception:
            continue
        if v.get("통과") and (best is None or v["때"] > best[1]):
            best = (u, v["때"])
    if not best:
        sys.exit(f"면 {g} 통과 판 없음 — 먼저 replay.py 상일보카@{g} check")
    return os.path.join(CACHE, best[0], "catalog")


def export_all():
    files = []
    for g in UNITS:
        cat = unit_dir(g)
        f = os.path.join(OUT, f"면_{g}.json")
        code = ("import json, sys; from core.units import store, package; lib = store.library(); "
                "p = [x for x in lib['plans'] if x.get('name') == sys.argv[2]][-1]; "
                "json.dump(package.export(lib, p['id']), open(sys.argv[1], 'w', encoding='utf-8'), ensure_ascii=False)")
        subprocess.run([PY, "-c", code, f, NAME], cwd=REPO, env=dict(os.environ, YONE_CATALOG_DIR=cat, YONE_AUTH="off"), check=True)
        pk = json.load(open(f, encoding="utf-8"))
        print(f"  내보냄 면 {g} — 쪽 {len(pk['pages'])} ({os.path.basename(os.path.dirname(cat))})", flush=True)
        files.append((g, f, pk))
    return files


# ── 원본 원고 — 원본 차례 덩어리 ──────────────────────────────────────
import pymupdf                                                            # noqa: E402
DOC = pymupdf.open(REF)


def big_num(p):
    """번호표 큰 번호(DAY 번호 · 구간 번호) — 없으면 None"""
    try:
        return C.sp_line(C.spans(p), lambda s: s["size"] > 15 and s["base"] < 25)["text"].strip()
    except RuntimeError:
        return None


def small_num(p):
    try:
        return C.sp_line(C.spans(p), lambda s: s["size"] == 10.0 and s["base"] < 12)["text"].strip()
    except RuntimeError:
        return None


def foot(p):
    """꼬리 — 왼쪽 쪽: 책 이름 · 오른쪽 쪽: 꼬리 DAY({자리: 글})"""
    sp = C.spans(p)
    bars = [s for s in sp if s["base"] > 200 and s["text"] == "|"]
    out = {}
    for b in bars:
        if b["x"] < 60:
            r = [s for s in sp if s["base"] > 200 and b["x1"] < s["x"] < 60 and s["size"] == 6.0]
            if r:
                out["책 이름"] = C.line_of(r, r[0]["base"])["text"]
        elif b["x"] > 90:
            r = [s for s in sp if s["base"] > 200 and 90 < s["x"] < b["x"] and s["size"] == 6.0]
            if r:
                out["꼬리 DAY"] = C.line_of(r, r[0]["base"])["text"]
    return out


def side_tab(p):
    pg = DOC[p - 1]
    for b in pg.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            if l["dir"] == (0.0, 1.0):
                t = "".join(c["c"] for sp in l["spans"] for c in sp["chars"]).strip()
                if t:
                    return t
    return None


def frame_vals(pages, num_key):
    """DAY(구간) 덩어리의 쪽 틀 원고 — 번호 · 작은 번호 · 책 이름 · 꼬리 DAY · 옆 탭(그 덩어리 쪽들에서 처음 나온 값)"""
    r = {}
    n = big_num(pages[0])
    if n and num_key:
        r[num_key] = n
    for p in pages:
        for k, v in foot(p).items():
            r.setdefault(k, v)
        t = side_tab(p)
        if t:
            r.setdefault("옆 탭", t)
        s = small_num(p) if p != pages[0] else None
        if s:
            r.setdefault("작은 DAY 번호", s)
    if "작은 DAY 번호" not in r and n:
        r["작은 DAY 번호"] = n                                            # 본문 쪽이 없는 덩어리 — 넘쳐 더한 쪽에 쓸 값(같은 번호)
    return r


def part_cover(p):
    tx = [e for e in C.els(p) if e["k"] == "text"]
    part = next(e for e in tx if e["text"].startswith("PART"))
    name = max(tx, key=lambda e: e["size"])
    sub = next(e for e in tx if e is not part and e is not name)
    return {"파트 번호": part["text"], "파트 이름": name["text"], "파트 부제": sub["text"], "_원본쪽": [p]}


def part_toc(p):
    el = C.els(p)
    names = sorted((e for e in el if e["k"] == "text" and e["size"] == 8.0), key=lambda e: e["y"])
    counts = sorted((e for e in el if e["k"] == "text" and e["size"] == 6.0), key=lambda e: e["y"])
    return {"차례 이름+차례 단어 수": [{"차례 이름": n["text"], "차례 단어 수": c["text"]} for n, c in zip(names, counts)], "_원본쪽": [p]}


def wb_flow(pages):
    """워크북 DAY — A(첫 쪽) · B~D 한 줄기(나머지 쪽, 머리 없이 시작하는 쪽은 앞 쪽 문제를 이어 받는다)"""
    a = pages[0]
    hs = {h[0]: h for h in face_wb.heads(a)}
    r = {"A 발문": hs["A"][2]["text"], face_wb.ALIST: [it["rec"] for it in face_wb.a_items(a)]}
    flow, sec = [], "B"
    for p in pages[1:]:
        flow += face_wb.page_records(p, sec)
        hs = face_wb.heads(p)
        if hs:
            sec = hs[-1][0]
    r[face_wb.FLOW] = flow
    return r


def body_of(kind, pages):
    if kind == "표제어 · 첫 펼침면":
        return {face_pyo.ENTRY: [x for p in pages for x in EN.entries(REF, p)]}
    if kind == "파생어 & 연관어휘 · 첫 펼침면":
        return {face_pa.ENTRY: face_pa.ended([x for p in pages for x in EN.derived(REF, p)])}
    if kind == "more with · 첫 펼침면":
        return {face_more.MORE: [x for p in pages for x in face_more.more_records(p)]}
    if kind == "VOCA vs. VOCA · 첫 펼침면":
        return {face_vv.VV: [x for p in pages for x in face_vv.vv_records(p)]}
    if kind == "워크북 · 첫 펼침면":
        return wb_flow(pages)
    if kind == "정답 첫 면":
        return {face_dap.ENTRY: face_dap.dap_records(pages)}
    raise KeyError(kind)


def chunk(kind, pages):
    num_key = {"more with · 첫 펼침면": "구간 번호", "VOCA vs. VOCA · 첫 펼침면": "구간 번호", "정답 첫 면": None}.get(kind, "DAY 번호")
    if kind == "정답 첫 면":
        r = {k: v for k, v in frame_vals(pages, None).items() if k == "책 이름"}
    else:
        r = frame_vals(pages, num_key)
    r.update(body_of(kind, pages))
    r["_면"] = kind
    r["_원본쪽"] = list(pages)
    return r


def records():
    recs, p, last = [], 2, DOC.page_count
    while p < last:
        lab = LABEL.get(p)
        if lab == "PART 간지":
            recs.append(dict(part_cover(p), _면=lab))
            p += 1
        elif lab == "PART 차례":
            recs.append(dict(part_toc(p), _면=lab))
            p += 1
        elif lab == "MEMO 면":
            recs.append({"구분": "MEMO", "_면": lab, "_원본쪽": [p]})
            p += 1
        elif lab in BODY:
            pages, q = [p], p + 1
            ok = {lab, BODY[lab]}
            while q < last and LABEL.get(q) in ok and not (LABEL.get(q) == lab and lab != "정답 첫 면" and big_num(q)):
                pages.append(q)                                          # 같은 구간의 다음 쪽 — 새 번호표(다음 DAY 첫 쪽) 전까지
                q += 1
            recs.append(chunk(lab, pages))
            p = q
        else:
            sys.exit(f"{p}쪽 면을 모른다 — {lab}")
    c = [e for e in C.els(1) if e["k"] == "text"]
    sp = C.spans(1)
    school = next(e for e in c if e["size"] == 12.5 and e["x"] < 60)
    exam = next(e for e in c if e["size"] == 12.5 and e["x"] > 60)
    rng = next(e for e in c if e["text"].startswith("Day"))
    return {"학교": school["text"], "시험": C.el_line(sp, exam)["text"], "범위": C.el_line(sp, rng)["text"], "원고": recs}


# 견본 원고 — 5단계 검사 견본 쪽(덩어리 첫 쪽 → 그 덩어리에서 쓸 쪽). 본문 펼침면은 첫 펼침면에서 넘쳐 받는다
SAMPLE = {2: [2], 3: [3], 4: [4, 5, 6, 7], 9: [9], 94: [94, 95, 96, 97], 150: [150, 151], 152: [152, 153, 154, 155],
          162: [162, 163, 164, 165], 244: [244, 245]}
# 등록 PDF 쪽 → 그 쪽을 그린 면의 견본 쪽(맞대기 기준). 넘쳐 더한 쪽은 본문 펼침면 견본 쪽
# (정답 244 · 245쪽 원고 = Day 31 끝 + Day 32 — Day 마다 새 쪽이라 첫 면 + 본문 왼쪽 · 오른쪽 세 쪽 → 견본 244 · 246 · 247)
WANT = [1, 2, 3, 4, 5, 6, 7, 9, 94, 95, 96, 97, 150, 151, 152, 153, 154, 155, 162, 163, 164, 165, 244, 246, 247, 259]


def sample(content):
    out = []
    for r in content["원고"]:
        p0 = r["_원본쪽"][0]
        if p0 not in SAMPLE:
            continue
        if r["_면"] in BODY:
            r = dict(chunk(r["_면"], SAMPLE[p0]), **{k: v for k, v in r.items() if k in ("옆 탭", "꼬리 DAY", "책 이름", "DAY 번호", "구간 번호", "작은 DAY 번호")})
        out.append(r)
    return dict({k: v for k, v in content.items() if k != "원고"}, 원고=out)


def fresh_data():
    shutil.rmtree(os.path.dirname(DATA), ignore_errors=True)
    os.makedirs(os.path.join(DATA, "_units"))
    src = os.path.join(REPO, "catalog")
    for n in os.listdir(src):
        if n != "_units":
            os.symlink(os.path.join(src, n), os.path.join(DATA, n))
    shutil.copy(os.path.join(src, "_units", "specs.json"), os.path.join(DATA, "_units", "specs.json"))
    base = {"id": "base", "name": "기본 (브랜드 없음)", "tokens": {"color": {"ink": "#231f20", "white": "#ffffff"}, "font": {"body": "Noto Sans CJK KR"}}, "styles": {}}
    for k, v in (("skins", [base]), ("blocks", []), ("parts", []), ("pages", []), ("plans", []), ("sets", [])):
        json.dump(v, open(os.path.join(DATA, "_units", k + ".json"), "w", encoding="utf-8"), ensure_ascii=False)


def server():
    root = os.path.join(os.path.dirname(DATA), "studio")                 # 스튜디오 루트는 빈 폴더 — 기동 때 잡 기록(_jobs, iCloud 내려받기 대기)을 안 읽게
    os.makedirs(root, exist_ok=True)
    env = dict(os.environ, YONE_CATALOG_DIR=DATA, YONE_AUTH="off", YONE_STUDIO_ROOT=root)
    p = subprocess.Popen([PY, "-u", "studio_server.py", "--port", str(PORT)], cwd=REPO, env=env,
                         stdout=open(os.path.join(OUT, "server.log"), "w"), stderr=subprocess.STDOUT)
    for _ in range(960):                                                 # 8분 — 기동 때 모든 디자인 구성을 미리 계산(다른 세션이 바쁘면 늦다 · YONE_WARM=0 이면 몇 초)
        try:
            urllib.request.urlopen(BASE + "/api/units/library", timeout=1)
            return p
        except Exception:
            time.sleep(0.5)
    p.kill()
    sys.exit(f"서버가 안 뜸 — {OUT}/server.log")


def page_step(i, label, body):
    return ([S(label, 900), {"js": f"(() => {{ openPage(docPages()[{i}]); return '쪽 열기 {i + 1}'; }})()"}, {"wait": 1500},
             {"js": f"(() => {{ if (idx() !== {i}) throw new Error('쪽 안 열림 ' + (idx() + 1)); return '{i + 1}쪽 열림'; }})()"},
             {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}] + body)


def layout(files):
    """이은 문서의 쪽 차례 — [(면 번호, 면 안 몇째 쪽, 쪽 이름, 쪽 데이터)] · 면마다 이야기 이름(가져오기가 겹치는 이름에 붙이는 번호까지 — package.import_)"""
    rows, stories, used = [], {}, set()
    for g, _, pk in files:
        ren = {}
        for s in sorted({(it.get("atom") or {}).get("story") for p in pk["pages"] for it in p.get("items") or []} - {None}):
            if s in used:
                n = 2
                while f"{s} ({n})" in used:
                    n += 1
                ren[s] = f"{s} ({n})"
            used.add(ren.get(s, s))
        for k, p in enumerate(pk["pages"]):
            rows.append((g, k, p["name"], p))
            for it in p.get("items") or []:
                s = (it.get("atom") or {}).get("story")
                if s:
                    stories.setdefault(g, ren.get(s, s))
    return rows, stories


def center(it):
    a = it.get("atom") or {}
    x, y = float(it.get("x") or 0), float(it.get("y") or 0)
    w, h = float(it.get("w") or a.get("w") or 0), float(it.get("h") or a.get("h") or 0)
    return [round(x + w / 2, 2), round(y + h / 2, 2)]


def click_item(it, want_js, label):
    """지면에서 그 개체를 눌러 고른다(사람처럼) — 골라진 것이 want_js(a = 고른 개체 원자) 가 아니면 멈춘다"""
    return [{"click": {"mm": center(it)}, "wait": 900},
            {"js": f"(() => {{ const it = sel != null && page.items[sel]; const a = it && it.atom; if (!a || !({want_js})) "
                   f"throw new Error('안 골라짐 — {label} · 고른 것 ' + JSON.stringify(a && {{bind: a.bind, story: a.story, t: a.t}})); return '고름 {label}'; }})()"}]


def steps(files, content):
    st = open_doc(NAME)
    got = 0
    for k, (g, f, pk) in enumerate(files):
        got += len(pk["pages"])
        st += [S(f"문서 파일 가져오기 — 면 {g} ({'새 문서로' if k == 0 else '이 문서 끝에'})", 1200), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
               {"pick": {"at": "#side #s-pkg-mode", "value": "new" if k == 0 else "append"}, "wait": 700},
               {"upload": {"at": "#side #s-pkg-file", "click": "#side #s-pkg-in", "path": f}, "wait": 4000},
               {"until": f"docPages().length === {got}", "wait": 500},
               {"js": "(() => '쪽 ' + docPages().length + ' · ' + document.querySelector('#st').textContent)()"}]
    rows, stories = layout(files)
    st += [{"js": f"(() => {{ const n = docPages().length; if (n !== {len(rows)}) throw new Error('이은 쪽 ' + n); return '이은 쪽 ' + n; }})()"}]
    at = {(g, k): i for i, (g, k, _, _) in enumerate(rows)}
    first = {g: n for i, (g, k, n, _) in enumerate(rows) if k == 0}
    two = {g for g, k, _, _ in rows if k == 1}
    pname = {}
    for g in sorted(two, key=int):                                       # 오른쪽 쪽 이름 — 넘치면 더할 페이지 목록에서 고른다
        i = at[(g, 1)]
        pname[(g, 1)] = first[g] + " 오른쪽"
        st += page_step(i, f"페이지 이름 — {i + 1}쪽 「{rows[i][2]}」 → 「{pname[(g, 1)]}」", [
            F("#side #s-pname", pname[(g, 1)], 900),
            {"js": f"(() => {{ if (page.name !== {json.dumps(pname[(g, 1)])}) throw new Error('이름 안 바뀜 ' + page.name); return page.name; }})()"}])
    for g in sorted(two, key=int):                                       # 펼침면 상위 페이지
        i = at[(g, 0)]
        st += page_step(i, f"펼침면 상위 페이지 — {i + 1}쪽 「{first[g]}」 + 다음 쪽", [
            {"click": "#side #s-spread2", "wait": 1000},
            {"js": f"(() => {{ const q = planPg(docPages()[{i}].id); if (!q || !q.펼침면) throw new Error('펼침면 안 켜짐'); return '펼침면 켬'; }})()"}])
    for g0, (g, bind) in FLOWS.items():                                  # 본문 면 글상자 → 첫 면 이야기 끝에
        s0 = stories[g0]
        for k in (0, 1):
            if (g, k) not in at:
                continue
            i = at[(g, k)]
            box = next(it for it in rows[i][3]["items"] if (it.get("atom") or {}).get("story"))
            st += page_step(i, f"텍스트 스레드 — {i + 1}쪽 「{rows[i][2]}」 글상자 → 면 {g0} 이야기 「{s0}」 끝에 연결", click_item(box, "a.story", "글상자") + [
                {"pick": {"at": '#side select[data-a="story"]', "value": s0}, "wait": 1000},
                {"js": f"(() => {{ const a = page.items[sel].atom; if (a.story !== {json.dumps(s0)} || (+a.story_seq || 1) < 2) throw new Error('연결 안 됨 ' + a.story + ' ' + a.story_seq); "
                       "return '스레드 ' + a.story + ' · ' + a.story_seq + '번째'; })()"}])
    for g0, (g, _) in FLOWS.items():                                     # 러닝 헤드 — 본문 면 원고 자리
        for k in (0, 1):
            if (g, k) not in at:
                continue
            i = at[(g, k)]
            for it in rows[i][3]["items"]:
                b = (it.get("atom") or {}).get("bind")
                if b in RUN and not (it.get("atom") or {}).get("running"):
                    st += page_step(i, f"러닝 헤드 — {i + 1}쪽 「{rows[i][2]}」 「{b}」 (넘쳐 더한 페이지에도 그 DAY 값)",
                                    click_item(it, f"a.bind === {json.dumps(b)}", b) + [
                                        {"click": '#side input[data-a="running"]', "wait": 900},
                                        {"js": "(() => { const a = page.items[sel].atom; if (!a.running) throw new Error('러닝 헤드 안 켜짐'); return '러닝 헤드 ' + a.bind; })()"}])
    for g0, (g, _) in FLOWS.items():                                     # 스마트 텍스트 리플로우 — 더할 페이지
        src = (g0, 1) if (g0, 1) in at else (g0, 0)
        lname = first[g]
        rname = pname.get((g, 1))
        chain = [(src, lname)] + ([((g, 0), rname), ((g, 1), lname)] if rname else [((g, 0), lname)])
        for (key, target) in chain:
            i = at[key]
            st += page_step(i, f"스마트 텍스트 리플로우 — {i + 1}쪽 넘치면 더할 페이지 → 「{target}」", [
                {"pick": {"at": "#side #s-cont", "text": target}, "wait": 900},
                {"js": f"(() => {{ const p = docPages()[{i}]; const t = docPages().find(x => x.id === p.cont); if (!t || t.name !== {json.dumps(target)}) throw new Error('더할 페이지 지정 실패'); return '더할 페이지 ' + t.name; }})()"}])
    i = next(i for i, r in enumerate(rows) if r[2] == "MEMO 면")
    st += page_step(i, f"분류 — {i + 1}쪽 「MEMO 면」 → MEMO(원고 덩어리 「구분: MEMO」가 고른다)", [
        {"fill": {"at": "#side #s-gubun", "value": "MEMO"}, "wait": 1200},
        {"js": f"(() => {{ const q = planPg(docPages()[{i}].id); if (!q || q.구분 !== 'MEMO') throw new Error('분류 안 들어감'); return '분류 ' + q.구분; }})()"}])
    if os.environ.get("JOIN_REGISTER", "1") == "0":
        return st
    st += put_content(sample(content), "원고 넣기 — 면마다 견본 원고 하나(원고 덩어리 차례 — 바깥 시스템이 보내는 꼴)")
    st += [S("관리에 등록 — 단어장 폴더", 1500), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
           {"pick": {"at": "#side #s-reg-series", "value": "vocab"}, "wait": 900}, {"click": "#side #s-reg", "wait": 3000}]
    st += [{"until": "plan.catalog && plan.catalog.design && /등록됨/.test(document.querySelector('#s-reg-st').textContent)", "wait": 300}] * 60
    st += [{"js": "(() => { const t = document.querySelector('#s-reg-st').textContent; if (!/등록됨/.test(t)) throw new Error('관리 등록 안 됨 — ' + t); "
                  "return '등록 ' + JSON.stringify(plan.catalog) + ' · ' + t; })()"}]
    return st


def build(content, tag="책"):
    """원고를 넣은 책 — 관리 등록과 같은 함수(fill_svgs). 면마다 이름 · 덧쪽 여부 · 받은 덩어리의 원본 쪽"""
    code = r'''
import json, sys
from core.units import store
from core.units import pdf as _pdf
from routes.units import _filled, fill_svgs, _ctx
lib = store.library()
plan = [p for p in lib["plans"] if p.get("name") == sys.argv[1]][-1]
content = json.load(open(sys.argv[2], encoding="utf-8"))
ctx = _ctx(lib, plan.get("skin"))
seq = _filled(lib, plan, content, ctx, False)[0]
recs = []
svgs, rep, spec = fill_svgs(lib, plan, content, ctx, recs=recs)
_pdf.to_pdf(svgs, float(spec["w"]), float(spec["h"]), sys.argv[3], title="상일보카", timeout=3600)
json.dump({"names": [pg.get("name") for pg, _, _ in seq], "spare": [bool(sp) for _, _, sp in seq],
           "orig": [(r or {}).get("_원본쪽") for r in recs], "face": [(r or {}).get("_면") for r in recs], "report": rep},
          open(sys.argv[4], "w", encoding="utf-8"), ensure_ascii=False)
'''
    cf, pdf, res = os.path.join(OUT, f"{tag}_원고.json"), os.path.join(OUT, f"{tag}.pdf"), os.path.join(OUT, f"{tag}.json")
    json.dump(content, open(cf, "w", encoding="utf-8"), ensure_ascii=False)
    subprocess.run([PY, "-W", "ignore", "-c", code, NAME, cf, pdf, res], cwd=REPO, env=dict(os.environ, YONE_CATALOG_DIR=DATA, YONE_AUTH="off"), check=True)
    return pdf, json.load(open(res, encoding="utf-8"))


def judge(pdf, res, content):
    """기능 테스트 — ① 원고 넣기: 빈 자리 · 틀에 없는 자리 0 ② 덩어리마다 그 면(원본 면 이름의 면)이 골라졌나 ③ 넘친 글이 본문 면 모양 덧쪽으로 이어졌나.
    쪽 수는 원본과 대 적어 두기만(원본과 똑같은 책 맞추기가 아니다)"""
    ref, book = pymupdf.open(REF), pymupdf.open(pdf)
    rep = res["report"]
    bad = []
    if rep.get("unfilled") or rep.get("unknown"):
        bad.append(f"원고 넣기 — 빈 자리 {rep.get('unfilled')} · 틀에 없는 자리 {rep.get('unknown')}")
    chunks = [r for r in content["원고"]]
    heads = [(n, f, o) for n, f, o, sp in zip(res["names"], res["face"], res["orig"], res["spare"]) if f and not sp]
    seen = {}                                                            # 덩어리(원본 쪽 목록) → 그 덩어리를 받은 첫 쪽의 면 이름
    for n, f, o in heads:
        seen.setdefault(json.dumps(o), n)
    want = [DOCNAME.get(r["_면"], r["_면"]) for r in chunks]
    got = [seen.get(json.dumps(r["_원본쪽"])) for r in chunks]
    miss = [(w, g, r["_원본쪽"][0]) for w, g, r in zip(want, got, chunks) if g != w]
    for w, g, p in miss[:20]:
        bad.append(f"덩어리 원본 {p}쪽 — 면 「{w}」 대신 「{g}」")
    sp_n = sum(res["spare"])
    used = book.page_count - (len(res["names"]) - sp_n)                  # 실제로 찍힌 덧쪽(크롬이 빈 덧쪽을 지운 뒤)
    print(f"책 {book.page_count}쪽 · 원본 {ref.page_count}쪽 · 덩어리 {len(chunks)}개 · 면 {len(res['names']) - sp_n}쪽 + 넘쳐 더한 쪽 {used}"
          f"(덧쪽 후보 {sp_n}) · 넣은 보고 {rep}")
    # 구간마다 쪽 수 — MEMO 쪽(글로 찾음)을 경계로 원본과 책을 나란히(적어 두기만 — 「PART」 글은 more with · VV 번호표에도 있어 경계로 안 쓴다)
    def marks(d):
        out = []
        for i in range(d.page_count):
            t = re.sub(r"\s+", "", d[i].get_text())
            if t.startswith("MEMO"):
                out.append(i + 1)
        return out + [d.page_count]
    a, b = marks(ref), marks(book)
    diff = []
    prev_a, prev_b = 0, 0
    for x, y in zip(a, b):
        if (y - prev_b) != (x - prev_a):
            diff.append(f"원본 {prev_a + 1}~{x}쪽 {x - prev_a}쪽 → 책 {prev_b + 1}~{y}쪽 {y - prev_b}쪽")
        prev_a, prev_b = x, y
    print("구간 쪽 수 차이(MEMO 쪽 사이):", "없음" if not diff else "")
    for x in diff:
        print("   ·", x)
    if not miss:
        print("  ○ 덩어리마다 그 면 — 원본 차례 그대로", len(chunks), "덩어리")
    for b in bad[:30]:
        print("  ✗", b)
    return not bad


def judge_reg(reg_pdf):
    import pagecmp
    reg = pymupdf.open(reg_pdf)
    units = {}
    for g in UNITS:
        wd = os.path.join(os.path.dirname(unit_dir(g)), "work")
        st = json.load(open(os.path.join(wd, "상태.json"), encoding="utf-8"))
        el = json.load(open(os.path.join(wd, "elems.json"), encoding="utf-8"))
        for k, rp in enumerate(st["pages"]):
            units[rp] = (g, el[str(k + 1)])
    if reg.page_count != len(WANT):
        print(f"  ✗ 등록 쪽 {reg.page_count} ≠ {len(WANT)} — 견본 차례 {WANT}")
        return False
    tot, bad = 0, []
    allow = {k for k in (STATE.get("허용") or {}) if not k.startswith("책:")}
    for i, rp in enumerate(WANT):
        g, elems = units[rp]
        one = pymupdf.open()
        one.insert_pdf(reg, from_page=i, to_page=i)
        pdf = os.path.join(OUT, f"p{rp}_reg.pdf")
        one.save(pdf)
        es = []
        for e in elems:
            if e.get("원고") or (str(e.get("text", "")).strip().isdigit() and int(e["text"]) == rp):
                e = dict({kk: vv for kk, vv in e.items() if kk != "text"}, pad=8.0, search=8.0, 원고=True)
            es.append(e)
        res = pagecmp.measure(REF, rp, pdf, es)
        for r, e in zip(res, es):
            ok = r.get("my") is not None if e.get("원고") else r["ok"]
            tot += 1
            if not ok and f"p{rp}:{r['id']}" not in allow:
                bad.append(f"면 {g} · 원본 {rp}쪽(등록 {i + 1}쪽) {r['id']}")
        print(f"  면 {g} · 원본 {rp}쪽 → 등록 {i + 1}쪽", flush=True)
    print(f"맞대기 — 요소 {tot - len(bad)}/{tot} 맞음")
    for b in bad[:30]:
        print("  ✗", b)
    return not bad


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    content = records()
    json.dump(content, open(os.path.join(OUT, "원고_전체.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print("원고 덩어리", len(content["원고"]), "·", [(r["_원본쪽"][0], len(r["_원본쪽"])) for r in content["원고"]])
    if os.environ.get("JOIN_ONLY_RECORDS"):
        for r in content["원고"]:
            print(r["_원본쪽"][0], r["_면"], {k: (v if isinstance(v, str) else f"[{len(v)}]") for k, v in r.items() if not k.startswith("_")})
        sys.exit(0)
    files = export_all()
    fresh_data()
    srv = server()
    try:
        sf = os.path.join(OUT, "steps.json")
        json.dump(steps(files, content), open(sf, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        r = subprocess.run([PY, "tests/e2e/rec.py", BASE + "/units", sf, os.path.join(OUT, "join.mp4"), "1600", "1000", "8"], cwd=REPO,
                           env=dict(os.environ, REC_FAST="1", REC_DIRECT="1"), capture_output=True, text=True)
        log = r.stdout + r.stderr
        open(os.path.join(OUT, "rec.log"), "w").write(log)
        print("\n".join(ln for ln in log.splitlines() if "js →" in ln or "ERR" in ln)[-4000:])
        if any("ERR" in ln or "Traceback" in ln for ln in log.splitlines()):
            sys.exit("잇기 실패 — " + os.path.join(OUT, "rec.log"))
        if os.environ.get("JOIN_REGISTER", "1") != "0":
            cat = next(p["catalog"] for p in json.load(open(os.path.join(DATA, "_units", "plans.json"), encoding="utf-8")) if p.get("catalog"))
            if subprocess.run([PY, os.path.join(E2E, "attach_origin.py"), f"{cat['series']}/{cat['design']}", REF, "--base", BASE], cwd=REPO).returncode:
                sys.exit("템플릿 보기 확인 실패 — 원본 페이지 차례가 안 나온다")
    finally:
        srv.kill()
    pdf, res = build(content)
    ok = judge(pdf, res, content)
    print("4 책 만들기(기능 테스트) 판정:", "통과" if ok else "실패", "→", pdf)
    if os.environ.get("JOIN_REGISTER", "1") == "0":
        sys.exit(0 if ok else 1)
    plans = json.load(open(os.path.join(DATA, "_units", "plans.json"), encoding="utf-8"))
    cat = next(p["catalog"] for p in plans if p.get("catalog"))
    ddir = os.path.join(REPO, "catalog", cat["series"], "designs", cat["design"])
    print("8 등록 카드", ddir)
    ok9 = judge_reg(os.path.join(ddir, "참고", "reference.pdf"))
    print("9 맞대기 판정:", "통과" if ok9 else "실패")
