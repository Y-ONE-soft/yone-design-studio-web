"""편집기 재현 — 단위 하나를 늘 같은 순서로 돌린다. 절차: docs/편집기_재현/절차.md

    python3 tests/e2e/replay.py <단위> check     만들기(녹화 없음) + 원본과 비교 → 일치율
    python3 tests/e2e/replay.py <단위> rec       같은 대본으로 녹화(기본 4배속) + 비교
    python3 tests/e2e/replay.py <단위> reset     그 단위의 데이터·그림·영상 지우기 (make.py 는 남김)
    python3 tests/e2e/replay.py _audit audit     기능을 고친 뒤 편집기 전체 감사 (빈 데이터로)

검사와 녹화 (2026-10-10 확정 — docs/편집기_재현/절차.md 「작업 순서」):
  검사  check — make.py 대본(손으로 짠 마우스·키보드)을 녹화 없이 재생해 편집기로 직접 만들고 원본과 요소마다 맞댄다.
        만들다 막히면 기능·버그를 고치고 그 단위를 지우고 처음부터. 판정은 도구가 낸다(끝 줄 「판정: 통과/실패」).
  녹화  rec — 같은 대본을 보기용으로 찍는다(선택). 결과는 검사와 같다.

단위 폴더 tests/e2e/replay/<단위>/ 에
  make.py   대본 생성기 — 실행하면 같은 폴더에 steps.json 을 쓴다
  상태.json  {"ref": "catalog/workbook/designs/d1/reference.pdf", "pages": [1, 2]}
             pages = 원본 쪽. 대본이 새로 만든 지면과 차례대로 맞댄다.
단위마다 데이터 폴더를 따로 써서(YONE_CATALOG_DIR) 지우기·병렬이 그 단위에만 미친다.
병렬: REPLAY_PORT(서버, 기본 5101) · REC_PORT(크롬, 기본 9466) 를 세션마다 다르게.
구성 하나만: <단위>@<구성 번호>(예: 정본-최종@4) — 그 대본(make.py)이 그 구성만 빈 문서에서 처음부터 만든다(GUSEONG).
  데이터·결과·만든 대본은 그 이름의 폴더에 따로 — 여러 구성을 동시에 돌려도 안 섞인다. 판정은 책 전체와 같다.
"""
import json, os, shutil, subprocess, sys, time, urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PY = sys.executable
PORT = int(os.environ.get("REPLAY_PORT") or 5101)
BASE = f"http://127.0.0.1:{PORT}"
DPI = 110

unit, cmd = sys.argv[1], sys.argv[2]
base_unit, _, only = unit.partition("@")
udir = os.path.join(REPO, "tests", "e2e", "replay", base_unit)
DIRECT = os.environ.get("REC_DIRECT") == "1"                               # 바로 넣기(rec.py) — 결과는 「<단위>~바로」 폴더에 따로.
store = unit + ("~바로" if DIRECT else "")                                  # 사람 조작 판의 결과(해 본 동작 목록의 출처)를 덮지 않는다
data = os.path.expanduser(f"~/.cache/yone-replay/{store}/catalog")
out = os.path.expanduser(f"~/Downloads/편집기재현/{store}")
wdir = os.path.join(os.path.dirname(data), "work") if only else udir     # make.py 가 쓰는 대본·요소 목록·상태


def fresh_data():
    """카탈로그는 리포를 가리키는 링크로, 편집기 저장 데이터(_units)는 **빈 상태**로 — 판형 정의와 빈 브랜드 하나만.
    시드의 블록·지면·문서가 화면(블록 패널·문서 목록)에 섞이지 않게, 대본이 만든 것만 남는다.
    빈 브랜드는 그림(로고)을 올릴 자리 — 올린 그림은 브랜드 그림 목록에 들어간다."""
    shutil.rmtree(os.path.dirname(data), ignore_errors=True)
    os.makedirs(os.path.join(data, "_units"))
    src = os.path.join(REPO, "catalog")
    for n in os.listdir(src):
        if n != "_units":
            os.symlink(os.path.join(src, n), os.path.join(data, n))
    shutil.copy(os.path.join(src, "_units", "specs.json"), os.path.join(data, "_units", "specs.json"))
    if cmd == "audit":                                                       # 감사는 시드 데이터로 — 문서 목록·브랜드 색·세트·미리보기를 시드에 기대어 본다(빈 데이터면 5개가 떨어진다)
        for n in os.listdir(os.path.join(src, "_units")):
            p = os.path.join(src, "_units", n)
            (shutil.copytree if os.path.isdir(p) else shutil.copy)(p, os.path.join(data, "_units", n))
        return
    base = {"id": "base", "name": "기본 (브랜드 없음)",
            "tokens": {"color": {"ink": "#231f20", "white": "#ffffff", "rule": "#b8b8b8", "gray": "#e6e6e6"},
                       "font": {"body": "Noto Sans CJK KR"}}, "styles": {}}
    for k, v in (("skins", [base]), ("blocks", []), ("parts", []), ("pages", []), ("plans", []), ("sets", [])):
        json.dump(v, open(os.path.join(data, "_units", k + ".json"), "w", encoding="utf-8"), ensure_ascii=False)


def server():
    env = dict(os.environ, YONE_CATALOG_DIR=data, YONE_AUTH="off")
    envf = os.path.expanduser("~/.config/yone/env")                          # bin/studio 와 같이 — 클로드 키
    if os.path.exists(envf):
        for ln in open(envf):
            k, _, v = ln.strip().removeprefix("export ").partition("=")
            if k and v and not k.startswith("#"):
                env.setdefault(k, v.strip("'\""))
    log = open(os.path.join(out, "server.log"), "w")
    p = subprocess.Popen([PY, "-u", "studio_server.py", "--port", str(PORT)], cwd=REPO, env=env, stdout=log, stderr=log)
    for _ in range(240):                                                      # 2분 — 기동 때 모든 디자인 구성을 미리 계산한다(warm_layouts, 디자인 30개 41초)
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
    os.makedirs(wdir, exist_ok=True)
    subprocess.run([PY, os.path.join(udir, "make.py")], check=True,          # → steps.json · elems.json · 상태.json (wdir)
                   env=dict(os.environ, REPLAY_WORK=wdir, GUSEONG=only))
    env = dict(os.environ, REC_FAST="1" if fast else "0")
    env.setdefault("REC_SPEED", "8")                                         # 녹화는 확인용 — 빠르게 (2026-10-08 사용자: 8배)
    r = subprocess.run([PY, "tests/e2e/rec.py", BASE + "/units", os.path.join(wdir, "steps.json"),
                        video, "1600", "1000", "8"], cwd=REPO, env=env, capture_output=True, text=True)
    open(os.path.join(out, "rec.log"), "w").write(r.stdout + r.stderr)
    bad = [ln for ln in (r.stdout + r.stderr).splitlines() if "ERR" in ln or "Traceback" in ln or ln.strip().startswith("!")]
    if fast and "프레임이 없다" in r.stdout + r.stderr:                         # 빠른 모드는 프레임을 안 찍는다 — 실패 아님
        r.returncode = 0
    if r.returncode or bad:
        print("대본 실패 —", f"{out}/rec.log")
        print("\n".join(bad[-8:]))
        return False
    return True


def compare(new_ids, state):
    compare.over = []
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
        fill = "&fill=auto" if state.get("fill") else ""                                  # 원고 자리 단위 — 넣은 원고로(임시 글 대신)
        urllib.request.urlretrieve(f"{BASE}/api/units/pdf?page={new_ids[k]}{fill}", pdf)
        try:                                                                              # 재단 여백 포함 — 원본과 같은 216×303
            urllib.request.urlretrieve(f"{BASE}/api/units/pdf?page={new_ids[k]}&print=1&marks=0{fill}",
                                       os.path.join(out, f"p{rp}_print.pdf"))
            warns = json.load(urllib.request.urlopen(f"{BASE}/api/units/pdf?page={new_ids[k]}&print=1&marks=0&json=1{fill}"))["warnings"]
            for w in warns:
                print(f"  ! 편집기 경고 p{rp}: {w}")
                if "넘" in w or "길다" in w:
                    compare.over.append(f"p{rp} {w[:60]}")
        except urllib.error.HTTPError as e:
            print(f"  ! 인쇄용 PDF 실패 p{rp}: {e.read().decode()[:300]}")
        ref[rp - 1].get_pixmap(dpi=DPI, clip=ref[rp - 1].trimbox).save(os.path.join(out, f"p{rp}_ref.png"))   # 재단선 안만 — 만든 지면(210×297)과 같은 판
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


def measure_units(new_ids, state, fix=False):
    """요소마다 원본과 결과를 같은 색 상자로 재서 차이(mm) — elems.json(make.py 가 씀)이 있을 때.
    fix: 글의 자리(dx,dy)·자간(dw→dtr) 차이를 보정.json 에 더한다 (편집기 글상자 위 끝 ↔ 원본 글자 상자)."""
    ep = os.path.join(wdir, "elems.json")
    if not os.path.exists(ep):
        return
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import pagecmp
    elems = json.load(open(ep, encoding="utf-8"))
    fp = os.path.join(udir, "보정.json")
    corr = json.load(open(fp, encoding="utf-8")) if os.path.exists(fp) else {}
    allres, bad = {}, 0
    for k, rp in enumerate(state["pages"]):
        pdf = os.path.join(out, f"p{rp}_my.pdf")
        if k >= len(new_ids) or not os.path.exists(pdf):
            continue
        # 원고 요소(원고 자리·원고를 따라 움직이는 것) — 원본과 위치·크기·모양을 맞대지 않는다. 그 자리 둘레(8mm)에 들어갔는지만(2026-10-10 사용자 확정:
        # 원고 부분은 「만들 수 있는가」 — 들어감·안 넘침·안 겹침·글 모양을 칸으로 정할 수 있음. 원본의 쪽별 차이는 따라 하지 않는다)
        es = [dict({kk: vv for kk, vv in e.items() if kk != "text"}, pad=8.0, search=8.0) if e.get("원고") else e for e in elems[str(k + 1)]]
        res = pagecmp.measure(os.path.join(REPO, state["ref"]), rp, pdf, es)
        for r, e in zip(res, es):
            if e.get("원고"):
                r["원고"] = True
                r["ok"] = r.get("my") is not None
                # 견본 원고(원본 글 그대로)를 넣은 판이면 원본 글 자리의 가로 · 세로 절반은 채워야 한다 — 「들어갔나」만 보면
                # 조각 원고가 첫 조각만 들어가 한 줄로 끝나도 통과했다(2026-10-12 배재1 포켓북 지문)
                # 견줄 크기 = 원본에서 잡힌 자리와 요소에 적은 크기 중 작은 쪽 — 둘레 8mm 찾기가 이웃 글(그림 설명)까지 잡아 원본 자리가 부푼다(배재1 포켓북 44쪽 꼬리)
                rw, rh = (min(r["ref"][2], e.get("w") or r["ref"][2]), min(r["ref"][3], e.get("h") or r["ref"][3])) if r.get("ref") else (0, 0)
                if r["ok"] and state.get("fill") and rw > 20 and rh > 8:
                    full = r["my"][2] >= rw * 0.5 and r["my"][3] >= rh * 0.5
                    if not full:
                        r["ok"] = False
                        r["덜 참"] = True
        allres[f"p{rp}"] = res
        for r, e in zip(res, es):
            if r["ok"]:
                continue
            bad += 1
            shape = (f"  · 모양 잉크 {r['ink']:.2f} 겹침 {r['iou']:.2f}" + ("" if r.get("shape_ok") else " ✗") if r.get("ink") is not None else "")
            if r.get("덜 참"):
                shape = f"  · 원고 덜 참 — 결과 {r['my'][2]:.1f}×{r['my'][3]:.1f}mm · 원본 글 자리 {min(r['ref'][2], e.get('w') or 1e9):.1f}×{min(r['ref'][3], e.get('h') or 1e9):.1f}mm"
            print(f"  ✗ p{rp} {r['id']:9s} " + (f"dx {r['dx']:+.2f} dy {r['dy']:+.2f} dw {r['dw']:+.2f} dh {r['dh']:+.2f}" + shape if r.get("my") and r.get("ref")
                                                else f"못 찾음 (원본 {r['ref']} · 결과 {r['my']})"))
            if fix and "text" in e and r.get("my") and r.get("ref"):
                key = r["id"] if k == 0 else f"p{rp}:{r['id']}"
                c = corr.setdefault(key, {})
                c["dx"] = round(c.get("dx", 0) + r["dx"], 2)
                c["dy"] = round(c.get("dy", 0) + r["dy"], 2)
                n = len(e["text"])
                if n > 1:
                    c["dtr"] = round(c.get("dtr", 0) + r["dw"] / (n - 1) / (e["size"] * 25.4 / 72) * 1000)
    n_all = sum(len(v) for v in allres.values())
    n_w = sum(1 for v in allres.values() for r in v if r.get("원고"))
    n_wbad = sum(1 for v in allres.values() for r in v if r.get("원고") and not r["ok"])
    measure_units.last = allres
    print(f"  고정 요소 {n_all - n_w - (bad - n_wbad)}/{n_all - n_w} 맞음 (위치·크기 0.3mm 안 · 글은 모양까지: 잉크 ±{pagecmp.SHAPE_INK:.0%} · 겹침 {pagecmp.SHAPE_IOU})"
          f" · 원고 요소 {n_w - n_wbad}/{n_w} 들어감")
    json.dump(allres, open(os.path.join(out, "측정.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if fix:
        json.dump(corr, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("  보정.json 갱신 — 다시 돌리면 반영")
    deco_check(new_ids, state)
    flow_check(new_ids, state)


def deco_check(new_ids, state):
    """원고 자리 안 작은 글(윗주 · 위첨자 번호 · 구문 표기 등 본문보다 작은 글)의 높이 — 원본과 0.3mm 안.
    원고 글 모양·줄 끝은 맞대지 않지만, 작은 글이 주인 글자에서 떨어진 높이는 원고가 바뀌어도 그대로라 맞댄다
    (2026-10-12 배재1 포켓북: 윗주가 줄에 붙고 번호 높이가 틀려도 「들어감」만 봐서 통과했다).
    주인 글자 = 상자 사이가 가장 가까운 본문 글. 견본 원고(원본 글 그대로)를 넣은 판에서만 — 글로 짝을 짓는다."""
    deco_check.bad = []
    ep = os.path.join(wdir, "elems.json")
    if not state.get("fill") or not os.path.exists(ep):
        return
    import collections
    import pymupdf
    mm = 25.4 / 72
    elems = json.load(open(ep, encoding="utf-8"))

    def spans(page, ox, oy):
        """낱말 목록 — 한 줄의 같은 크기 조각들을 이어 붙인 뒤 띄어쓰기로 나눈다. 결과 PDF 는 글 언어로 감싼 문장부호 · 한글이
        글자마다 따로 조각이 되어(「인」「류」「학」「자」 · 「: 」) 원본 낱말(「인류학자」 · 「*anthropologist:」)과 짝이 안 지어졌다(2026-10-14 실전 문제 주석)"""
        res = []
        for b in page.get_text("rawdict")["blocks"]:
            for ln in b.get("lines", []):
                runs = []                                                 # [(크기, 기준선, 글자들)] — 크기가 같고 잇닿은 조각은 하나로
                for s in ln["spans"]:
                    if (runs and s["chars"] and runs[-1][2] and abs(runs[-1][0] - s["size"]) < 0.05 and abs(runs[-1][1] - s["origin"][1]) < 0.5
                            and abs(s["chars"][0]["bbox"][0] - runs[-1][2][-1]["bbox"][2]) < 0.6):   # 잇닿은 조각만(떨어져 놓인 윗주 낱말끼리는 안 붙인다)
                        runs[-1][2].extend(s["chars"])
                    else:
                        runs.append((s["size"], s["origin"][1], list(s["chars"])))
                for size, base, chars in runs:
                    word = []
                    for c in chars + [{"c": " ", "bbox": (0, 0, 0, 0)}]:
                        if c["c"].strip():
                            word.append(c)
                            continue
                        if word:                                          # 붙은 표시(「S V」)는 결과 PDF 가 한 덩어리로 낸다 — 낱말로
                            x0, y0 = min(k["bbox"][0] for k in word), min(k["bbox"][1] for k in word)
                            x1, y1 = max(k["bbox"][2] for k in word), max(k["bbox"][3] for k in word)
                            res.append(dict(t="".join(k["c"] for k in word), size=size, by=(base - oy) * mm, x0=(x0 - ox) * mm, x1=(x1 - ox) * mm,
                                            y0=(y0 - oy) * mm, y1=(y1 - oy) * mm))
                            word = []
        return res

    def decos(S, e, pad):
        x, y, w, h = e["x"] - pad, e["y"] - 4, e["w"] + 2 * pad, e["h"] + 4 + pad      # 위 4mm — 첫 줄 윗주
        ss = [s for s in S if x <= s["x0"] <= x + w and y <= s["y0"] <= y + h]
        if not ss:
            return {}
        cnt = collections.Counter()
        for s in ss:
            cnt[round(s["size"], 1)] += len(s["t"])
        body = cnt.most_common(1)[0][0]
        bodys = [s for s in ss if s["size"] >= body * 0.85]
        d = collections.defaultdict(list)
        for s in sorted(ss, key=lambda s: (round(s["by"]), s["x0"])):
            if s["size"] >= body * 0.85:
                continue
            gap = lambda b: (max(0, b["x0"] - s["x1"], s["x0"] - b["x1"]) ** 2 + max(0, b["y0"] - s["y1"], s["y0"] - b["y1"]) ** 2) ** 0.5
            o = min(bodys, key=lambda b: (round(gap(b), 1), abs(b["by"] - s["by"])), default=None)
            over = [b for b in bodys if b["x0"] < s["x1"] + 0.05 and b["x1"] > s["x0"] - 0.05 and abs(b["by"] - s["by"]) <= 3.5]   # 맞닿음(틈 0)도 붙은 것 — 원본은 커닝으로 0.06mm 겹치고 결과는 딱 닿아 번호를 놓쳤다(2026-10-15 포켓북 암기)
            if o and over:                                                # 주인 글자에 붙은 작은 글만 — 바로 위아래(3.5mm 안)에 가로로 겹치는 본문 글이 있다(윗주 · 위첨자 번호 · 구문 표기).
                d[s["t"]].append(s["by"] - o["by"])                       # 제 줄로 따로 선 작은 글(지문 끝 오른쪽 맞춤 주석)은 주인 글자가 없다 — 원고 판정(들어갔나)으로
        return d

    ref = pymupdf.open(os.path.join(REPO, state["ref"]))
    allow = allowed(state)
    for k, rp in enumerate(state["pages"]):
        pdf = os.path.join(out, f"p{rp}_my.pdf")
        if k >= len(new_ids) or not os.path.exists(pdf):
            continue
        rpg = ref[rp - 1]
        R, M = spans(rpg, rpg.trimbox.x0, rpg.trimbox.y0), spans(pymupdf.open(pdf)[0], 0, 0)
        n = 0
        for e in elems[str(k + 1)]:
            if not e.get("원고") or f"p{rp}:{e['id']}:작은 글" in allow:
                continue
            a, b = decos(R, e, 1), decos(M, e, 8)                             # 결과는 둘레 8mm — 원고 판정과 같은 찾기 범위
            for t, offs in a.items():
                mine = b.get(t, []) + [o2 for k2, v2 in b.items() if k2 != t and t.replace(" ", "") in k2.replace(" ", "") for o2 in v2]   # 붙어 그려진 작은 글은 PDF 에서 한 덩어리로 읽힌다(「V 조」+「S」 → 「V 조S」) — 그 안에서도 찾는다
                for i, o in enumerate(offs):
                    n += 1
                    if f"p{rp}:{e['id']}:작은 글:{t}" in allow:                   # 그 작은 글만 — 원본 손 고침(사용자 확정)
                        continue
                    if i >= len(mine):
                        deco_check.bad.append(f"p{rp}:{e['id']} 작은 글 「{t[:10]}」 빠짐 (원본 높이 {o:+.2f}mm)")
                    elif abs(mine[i] - o) > 0.3:
                        deco_check.bad.append(f"p{rp}:{e['id']} 작은 글 「{t[:10]}」 높이 원본 {o:+.2f} · 결과 {mine[i]:+.2f}mm")
        print(f"  원본 p{rp}: 원고 자리 작은 글 {n}개 높이 맞대기")
    for w in deco_check.bad[:20]:
        print("  ✗", w)
    if len(deco_check.bad) > 20:
        print(f"  … 외 {len(deco_check.bad) - 20}개")


def flow_check(new_ids, state):
    """원고 흐름 간격 — 위아래로 이웃한 두 줄(글줄 · 원고 상자 · 장식)의 사이가 원본과 0.3mm 안.
    원고 글의 줄 끝 · 쪽마다 달라지는 자리는 맞대지 않지만, 레코드마다 되풀이되는 간격(행간 · 단락 앞뒤 공백 · 상자 → 답 줄)은
    템플릿 값이라 원고가 바뀌어도 그대로다(2026-10-15 정본 영작 배열: 보기 상자 → ▶▶ 원본 5.97 · 결과 3.43mm 가 「들어감」만 봐서 통과했다).
    견본 원고(원본 글 그대로)를 넣은 판에서만. 판정은 견본 쪽(state pages 첫 쪽 — 템플릿 값을 잰 쪽)만, 나머지 쪽은 원본이 쪽마다 손으로
    줄인 곳(정본 25쪽 선지 행간 등)이 있어 적기만 한다(원본 쪽별 차이는 따라 하지 않는다 — 2026-10-10 사용자 확정). 짝 =원본에서 바로 아래 이웃(가로로 겹침 · 20mm 안)이고 결과에서도 그 둘이 바로 이웃일 때 —
    줄 바뀜이 달라 사이에 다른 줄이 끼면 맞대지 않는다. 예외 키 "p쪽:간격:<아래 것>" (상태.json 「원본_손고침」).
    상태.json 「흐름_참고만」 {구성 번호: 사용자 확정 이유} — 템플릿을 견본 한 쪽이 아니라 여러 쪽 가운데 값으로 만든 구성은 견본 쪽도 적기만."""
    flow_check.bad, flow_check.note = [], []
    if not state.get("fill") or getattr(measure_units, "last", None) is None:
        return
    import pymupdf
    mm = 25.4 / 72
    ref = pymupdf.open(os.path.join(REPO, state["ref"]))
    allow = allowed(state)

    def lines(page, ox, oy):
        """눈에 보이는 글줄 — 기준선이 같고 잇닿은 조각을 한 줄로. 작은 글(윗주 · 번호, 6.5pt 아래)은 뺀다(deco_check 가 본다)"""
        sp = []
        for b in page.get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                for s in ln["spans"]:
                    if s["text"].strip() and s["size"] >= 6.5:
                        sp.append(((s["bbox"][0] - ox) * mm, (s["bbox"][2] - ox) * mm, (s["origin"][1] - oy) * mm, s["text"]))
        sp.sort(key=lambda s: (round(s[2], 1), s[0]))
        out = []
        for x0, x1, by, t in sp:
            o = out[-1] if out else None
            if o and abs(o["by"] - by) < 0.4 and x0 - o["x1"] < 6:
                o["x1"], o["t"] = max(o["x1"], x1), o["t"] + t
            else:
                out.append({"x0": x0, "x1": x1, "by": by, "t": t})
        return [{"k": "줄:" + "".join(o["t"].split())[:24], "x0": o["x0"], "x1": o["x1"], "top": o["by"], "bot": o["by"]} for o in out]

    def below(items, a):
        """a 바로 아래 이웃 — 가로로 겹치고 a 아래 끝보다 아래에 위 끝이 있는 것 중 가장 가까운 것(20mm 안). 짝 못 지은 줄(짧은 줄 · 같은 글 여럿)도
        이웃으로 친다 — 그 줄이 끼면 짝이 안 된다(빼면 사이 줄을 건너뛰어 줄 수가 다른 곳까지 맞댔다)"""
        c = [b for b in items if b is not a and b["x0"] < a["x1"] and b["x1"] > a["x0"] and b["top"] > a["bot"] + 0.05]
        b = min(c, key=lambda b: b["top"], default=None)
        return b if b and b["top"] - a["bot"] < 20 else None

    for k, rp in enumerate(state["pages"]):
        pdf = os.path.join(out, f"p{rp}_my.pdf")
        res = measure_units.last.get(f"p{rp}")
        if k >= len(new_ids) or not os.path.exists(pdf) or res is None:
            continue
        rpg = ref[rp - 1]
        R, M = lines(rpg, rpg.trimbox.x0, rpg.trimbox.y0), lines(pymupdf.open(pdf)[0], 0, 0)
        import collections as _c
        cr, cm = _c.Counter(o["k"] for o in R), _c.Counter(o["k"] for o in M)
        ok = {kk for kk in cr if cr[kk] == 1 and cm.get(kk) == 1 and len(kk) >= 3}        # 원본 · 결과에 한 번씩만 나오는 줄만 짝짓는다(지문 번호 「2」처럼 한 글자도 — 쪽에 하나뿐이면)
        for o in R + M:
            o["m"] = o["k"] in ok
        decl = {e["id"]: e for e in json.load(open(os.path.join(wdir, "elems.json"), encoding="utf-8")).get(str(k + 1), [])}
        for r in res:                                                     # 원고 상자 · 장식(글 단 전체는 뺀다)
            e = decl.get(r["id"]) or {}
            if e and r.get("ref") and max(abs(r["ref"][0] - e["x"]), abs(r["ref"][1] - e["y"]), abs(r["ref"][2] - e["w"]), abs(r["ref"][3] - e["h"])) > 0.3:
                continue                                                  # 원본에서 잰 상자가 요소 목록과 다르다 — 둘레 8mm 찾기가 이웃(같은 색 · 번호)까지 잡았다, 그 짝은 못 믿는다
            if r.get("원고") and r.get("ref") and r.get("my") and not r["id"].startswith(("col", "t")):
                for D, b in ((R, r["ref"]), (M, r["my"])):
                    D.append({"k": r["id"], "m": True, "x0": b[0], "x1": b[0] + b[2], "top": b[1], "bot": b[1] + b[3]})
        Mk = {o["k"]: o for o in M if o["m"]}
        n = 0
        for a in R:
            b = below(R, a) if a["m"] else None
            if not b or not b["m"]:
                continue
            ka, kb = a["k"], b["k"]
            bm = below(M, Mk[ka])
            if not bm or bm["k"] != kb or not bm["m"]:                   # 결과에서 사이에 다른 것이 끼었다 — 줄 바뀜 차이, 맞대지 않는다
                continue
            n += 1
            g_ref, g_my = b["top"] - a["bot"], Mk[kb]["top"] - Mk[ka]["bot"]
            if abs(g_my - g_ref) > 0.3 and f"p{rp}:간격:{kb}" not in allow:
                w = f"p{rp} 간격 「{ka[:14]}」→「{kb[:14]}」 원본 {g_ref:.2f} · 결과 {g_my:.2f}mm"
                (flow_check.bad if k == 0 and only not in (state.get("흐름_참고만") or {}) else flow_check.note).append(w)
        print(f"  원본 p{rp}: 원고 흐름 간격 {n}곳 맞대기" + ("" if k == 0 else " (견본 쪽이 아니다 — 원본 쪽별 차이일 수 있어 판정에 안 넣고 적기만)"))
    for w in flow_check.note[:12]:
        print("  · 참고", w)
    for w in flow_check.bad[:20]:
        print("  ✗", w)
    if len(flow_check.bad) > 20:
        print(f"  … 외 {len(flow_check.bad) - 20}개")


def font_problems():
    """문서가 쓴 서체가 시스템 서체(core.units.fonts — 등록된 서체)인가. 컴퓨터에 깔린 서체로 그려지면 서버에선 다르게 나온다."""
    sys.path.insert(0, REPO)
    os.environ["YONE_CATALOG_DIR"] = data
    from core.units import fonts as F
    import routes.catalog as rc
    rc.CATALOG = data                                                       # 이 단위 데이터(올려 등록한 서체 포함)
    fams = F.families()
    load = lambda k: json.load(open(os.path.join(data, "_units", k + ".json"), encoding="utf-8")) if os.path.exists(os.path.join(data, "_units", k + ".json")) else []
    bad = set()

    def chk(font, weight, where):
        if not font or str(font).startswith("$"):
            return
        w = int(weight or 400)
        if font not in fams:
            bad.add(f"등록 안 된 서체 {font} ({where})")
        elif w not in fams[font]:
            bad.add(f"서체 {font} 에 굵기 {w} 없음 ({where})")
    for pg in load("pages"):
        for it in pg.get("items") or []:
            a = it.get("atom") or {}
            if a.get("t") == "text":
                chk(a.get("font"), a.get("weight"), pg.get("name") or pg["id"])
                for r in a.get("grep") or []:
                    if r.get("font"):
                        chk(r["font"], r.get("weight") or a.get("weight"), (pg.get("name") or pg["id"]) + " GREP")
    for sk in load("skins"):
        for k, v in ((sk.get("tokens") or {}).get("font") or {}).items():
            if v and v not in fams:
                bad.add(f"등록 안 된 서체 {v} (브랜드 {sk.get('name')} 견본 {k})")
        for n, st in (sk.get("styles") or {}).items():
            chk(st.get("font"), st.get("weight"), f"단락 스타일 {n}")
    return sorted(bad)


def allowed(state):
    """사용자 확정 예외 — 「허용」 + 「원본_손고침」(원본이 템플릿으로 찍은 뒤 사람이 손으로 고친 곳. 템플릿은 표준 값으로 두고
    필요하면 사용자가 편집기에서 그 자리만 고친다 — 절차.md 「원본 손 고침」). 키 = "p쪽:요소" · "p쪽:요소:작은 글" → 이유"""
    return {**(state.get("허용") or {}), **(state.get("원본_손고침") or {})}


def verdict(state, new_ids, ok_steps):
    """판정 — 도구가 정한다(사람·클로드가 줄이지 못한다). 하나라도 걸리면 실패:
      ① 대본 오류  ② 원본 쪽마다 만든 지면이 있어야  ③ 맞댈 요소 목록(elems.json)이 있어야
      ④ 요소 전부 기준 안 — 예외는 상태.json 「허용」 · 「원본_손고침」 {"p쪽:요소": "사용자 확정 이유"} 만
      ⑥ 원고 자리 작은 글(윗주 · 번호)의 높이가 원본과 0.3mm 안 — deco_check
      ⑦ 원고 흐름 간격(이웃한 글줄 · 상자 · 장식 사이)이 원본과 0.3mm 안 — flow_check
      ⑤ 목록 밖 차이 없음 — 원본과 결과가 다른 화소가 어느 요소 상자에도 안 들면 「목록에 없는 요소」(빠진 장식 등)
    → (통과 여부, 이유 목록)"""
    from PIL import Image, ImageChops, ImageDraw
    why = []
    if not ok_steps:
        why.append("대본 오류")
    why += font_problems()
    why += getattr(deco_check, "bad", [])
    why += getattr(flow_check, "bad", [])
    hand = {k: v for k, v in (state.get("원본_손고침") or {}).items() if any(k.startswith(f"p{rp}:") for rp in state.get("pages") or [])}
    if hand:                                                             # 판정에는 안 들지만 늘 보인다 — 템플릿은 표준 값, 사용자가 편집기에서 고칠 곳
        print(f"  원본 손 고침(사용자 확정) {len(hand)}곳 — 템플릿은 표준 값으로 두었다: " + " · ".join(sorted(hand))[:300])
    if not state.get("pages"):
        return (not why), why
    if len(new_ids) < len(state["pages"]):
        why.append(f"만든 지면 {len(new_ids)} < 원본 쪽 {len(state['pages'])}")
    allow = allowed(state)
    res = getattr(measure_units, "last", None)
    if not os.path.exists(os.path.join(wdir, "elems.json")) or res is None:
        why.append("맞댈 요소 목록 없음 — make.py 가 elems.json 을 써야 한다")
        res = {}
    for pk, rs in res.items():
        for r in rs:
            if not r["ok"] and f"{pk}:{r['id']}" not in allow:
                why.append(f"요소 기준 밖 {pk}:{r['id']}")
    px = DPI / 25.4
    for rp in state["pages"]:
        a_p, b_p = os.path.join(out, f"p{rp}_ref.png"), os.path.join(out, f"p{rp}_my.png")
        if not (os.path.exists(a_p) and os.path.exists(b_p)):
            continue
        a = Image.open(a_p).convert("RGB")
        b = Image.open(b_p).convert("RGB").resize(a.size)
        diff = ImageChops.difference(a, b).convert("L").point(lambda v: 255 if v > 48 else 0)
        cover = Image.new("L", a.size, 0)
        dr = ImageDraw.Draw(cover)
        decl = {e["id"]: e for e in json.load(open(os.path.join(wdir, "elems.json"), encoding="utf-8")).get(str(state["pages"].index(rp) + 1), [])}
        for r in res.get(f"p{rp}", []):
            boxes = [r.get("ref"), r.get("my")]
            if r.get("원고") and r["id"] in decl:                            # 원고 자리 — 그 둘레 전부(원고 글 모양·줄 끝은 원본과 비교하지 않는다)
                e = decl[r["id"]]
                boxes.append([e["x"] - 6, e["y"] - 6, e["w"] + 12, e["h"] + 12])
            for box in boxes:
                if box:
                    x, y, w, h = box
                    dr.rectangle([(x - 1.0) * px, (y - 1.0) * px, (x + w + 1.0) * px, (y + h + 1.0) * px], fill=255)
        out_of = ImageChops.subtract(diff, cover)
        cell = int(2 * px)                                                   # 2mm 칸 — 칸의 25% 넘게 다르면 그 칸은 「목록 밖 차이」
        bad = []
        for cy in range(0, a.size[1] - cell, cell):
            for cx in range(0, a.size[0] - cell, cell):
                n = sum(out_of.crop((cx, cy, cx + cell, cy + cell)).histogram()[255:])
                if n > cell * cell * 0.25:
                    bad.append((round(cx / px), round(cy / px)))
        if bad:
            keep = [c for c in bad if f"p{rp}:@{c[0]},{c[1]}" not in allow]
            if keep:
                why.append(f"p{rp} 목록 밖 차이 {len(keep)}칸 — 처음 {keep[:4]} mm (빠진 요소·목록에 안 넣은 요소)")
    return (not why), why


if cmd == "reset":
    shutil.rmtree(os.path.dirname(data), ignore_errors=True)
    shutil.rmtree(out, ignore_errors=True)
    for n in ("steps.json",):
        if os.path.exists(os.path.join(udir, n)):
            os.remove(os.path.join(udir, n))
    print("지움:", unit, "(make.py · 상태.json 은 남김)")
    sys.exit()

# 구성표 확인(2026-10-11) — 새 책은 구성을 구성 판정(layouts.py → 구성.json)으로만 정한다. 눈으로 나눈 목록 · 손으로 고친 구성.json ·
# 사용자 확인 전이면 돌지 않는다. 구성 번호(<단위>@N)는 구성.json 의 번호여야 한다. 이 규칙 전에 만든 단위는 예전 방식 그대로(LEGACY)
LEGACY = {"광문분석본", "정본-최종", "_audit"}
if base_unit not in LEGACY and not base_unit[:2].isdigit():
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import layouts
    ok_l, why_l = layouts.check(base_unit)
    if not ok_l:
        sys.exit("구성표 막힘 — " + why_l)
    nums = {str(r["번호"]) for r in json.load(open(layouts.path_of(base_unit), encoding="utf-8"))["구성"]}
    if only and any(g not in nums for g in only.split(",")):
        sys.exit(f"구성 번호 {only} 가 구성표에 없다 — 있는 번호 {sorted(nums, key=int)}")

state = json.load(open(os.path.join(udir, "상태.json"), encoding="utf-8"))


def mine(s):
    """대본이 쓴 상태(원본 쪽 목록 등)에 사용자 확정 예외는 단위 폴더 상태.json 것을 — 판 뒤에 적은 「허용」 · 「원본_손고침」도 판정에 든다"""
    for k in ("허용", "원본_손고침", "흐름_참고만"):
        if state.get(k):
            s[k] = dict(s.get(k) or {}, **state[k])
    return s


if cmd == "judge":                                                          # 판정만 다시 — 지난 판이 만든 결과(PDF·그림)로. 다시 만들지 않는다
    state = mine(json.load(open(os.path.join(wdir, "상태.json"), encoding="utf-8")))
    log = open(os.path.join(out, "rec.log"), encoding="utf-8").read()
    ok = not [ln for ln in log.splitlines() if "ERR" in ln or "Traceback" in ln or ln.strip().startswith("!")]
    ids = [rp for rp in state["pages"] if os.path.exists(os.path.join(out, f"p{rp}_my.pdf"))]
    compare.over = []                                                       # 넘침(편집기 경고)은 만들 때 판정 — 여기선 결과 그림만 다시 잰다
    measure_units(ids, state)
    passed, why = verdict(state, ids, ok)
    print("판정: 통과" if passed else "판정: 실패 — " + " · ".join(why[:12]) + (f" 외 {len(why) - 12}" if len(why) > 12 else ""))
    json.dump({"통과": passed, "이유": why, "때": time.strftime("%Y-%m-%d %H:%M")}, open(os.path.join(out, "판정.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    sys.exit(0 if passed else 1)
os.makedirs(out, exist_ok=True)
fresh_data()
srv = server()
try:
    if cmd == "audit":                                                       # 기능을 고친 뒤 — 편집기 전체 감사(다른 곳이 안 깨졌나)
        r = subprocess.run([PY, "tests/e2e/canvas_audit.py", BASE], cwd=REPO, capture_output=True, text=True)
        open(os.path.join(out, "audit.log"), "w").write(r.stdout + r.stderr)
        print("\n".join((r.stdout + r.stderr).strip().splitlines()[-6:]))
        sys.exit(r.returncode)
    before = set(page_ids())
    t0 = time.time()
    ok = run_steps(cmd != "rec", os.path.join(out, unit + ".mp4") if cmd == "rec" else os.path.join(out, "_fast.mp4"))
    state = mine(json.load(open(os.path.join(wdir, "상태.json"), encoding="utf-8")))  # 대본이 방금 쓴 상태(원본 쪽 목록) — 미리 읽은 것은 지난 판 것
    new_ids = [i for i in page_ids() if i not in before]
    print(f"{unit} {cmd} — {time.time() - t0:.0f}초 · 새 지면 {len(new_ids)}개")
    compare(new_ids, state)
    measure_units(new_ids, state, fix=ok and os.environ.get("REPLAY_FIX") == "1")      # 대본이 실패한 판은 보정에 안 쓴다
    passed, why = verdict(state, new_ids, ok)
    why += [f"넘침 {w}" for w in compare.over]
    passed = passed and not compare.over
    print("판정: 통과" if passed else "판정: 실패 — " + " · ".join(why[:12]) + (f" 외 {len(why) - 12}" if len(why) > 12 else ""))
    json.dump({"통과": passed, "이유": why, "때": time.strftime("%Y-%m-%d %H:%M"), "바로넣기": DIRECT},
              open(os.path.join(out, "판정.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if cmd == "rec" and ok:
        print("  영상:", os.path.join(out, unit + ".mp4"))
    print("→", out)
finally:
    srv.kill()
if "passed" in globals() and not passed:
    sys.exit(1)
