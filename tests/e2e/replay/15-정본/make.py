"""단위 15 정본 — 「스텝바이스텝 워크북 정본 (블루·베이지·브릭, A4)」을 편집기로 만들어 관리(워크북 폴더)에 등록한다. 전부 마우스·키보드.

정본(catalog/workbook/designs/d3, 274면)은 d1(74면)과 같은 디자인이고 구성 14개가 지문 수만큼 되풀이된다.
구성 하나하나는 단위 01~14 에서 편집기로 이미 만들었다(원본과 요소 단위로 맞댄 것). 이 단위는 그 문서들을
「문서 파일 → 가져오기(이 문서 끝에)」로 한 문서에 모으고, 쓰지 않는 쪽을 지우고, 구성마다
「원고마다 — 지문마다 한 장」을 켜고 이름을 붙인 뒤(원고 목록이 그 이름으로 들어온다), 견본 원고를 넣고 「관리에 등록」한다.

쪽 차례(30쪽): 속표지 · STEP 01 간지·차례(01C) · STEP 01 구성 6쌍(A1 어휘 선택 · A2 본문 O/X · B1 본문 정리 · B2 내용 종합 ·
C1 문장 배열 · C2 빈칸 어휘) · STEP 02 간지·차례(08) · STEP 02 구성 4쌍(A1 어법 선택 · B1 어법 O/X · C1 빈칸 어법 · C2 영작 배열) ·
STEP 03 간지·차례(13) · S 실전 문제(14F 흐름 틀 — 문항이 단·쪽을 넘어 흐르고 모자라면 덧쪽) · 뒤표지(14c 끝 쪽).
견본 원고 = 각 단위가 원본 d1 에서 읽어 넣은 원고 — 구성마다 한 벌. 정본 원고(274면)는 「원고 넣기」로 구성 이름마다 지문 목록을 주면 그만큼 되풀이된다.
문서 파일은 각 단위 데이터(~/.cache/yone-replay/<단위>)에서 편집기의 「내보내기」와 같은 함수(core/units/package.export)로 만든다.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, REPO)
from mkpage import *                                                    # noqa
from core.units import package, store

PKG_DIR = os.path.expanduser("~/Downloads/편집기재현/15-정본/문서파일")
os.makedirs(PKG_DIR, exist_ok=True)
# (단위, 이 문서에서 남길 쪽 차례(단위 문서 안 0부터), 구성 이름 — 있으면 「지문마다」 쌍)
UNITS = [("01-간지표지", [0], None), ("01C-차례", [0, 1], None),
         ("02B-원고자리", [0, 1], "STEP 01 A1 어휘 선택"), ("03-A본문OX", [0, 1], "STEP 01 A2 본문 O/X"),
         ("04-B본문정리", [0, 1], "STEP 01 B1 본문 정리"), ("05-B내용종합", [0, 1], "STEP 01 B2 내용 종합"),
         ("06-C문장배열", [0, 1], "STEP 01 C1 문장 배열"), ("07-C빈칸어휘", [0, 1], "STEP 01 C2 빈칸 어휘"),
         ("08-간지", [0, 1], None),
         ("09-A어법선택", [0, 1], "STEP 02 A1 어법 선택"), ("10-B어법OX", [0, 1], "STEP 02 B1 어법 O/X"),
         ("11-C빈칸어법", [0, 1], "STEP 02 C1 빈칸 어법"), ("12-C영작배열", [0, 1], "STEP 02 C2 영작 배열"),
         ("13-간지", [0, 1], None), ("14F-흐름실전", [0, 1], None), ("14c-S실전문제", [8], None)]

pk, content, k = {}, {}, 1                                              # k = 이 문서 쪽 차례(0 = 새 문서의 빈 쪽)
keep, layout = [0], []                                                  # 가져온 뒤 쪽 차례 · 남길 쪽
for unit, take, name in UNITS:
    store.CATALOG = os.path.expanduser(f"~/.cache/yone-replay/{unit}/catalog")
    if not os.path.isdir(store.CATALOG):
        sys.exit(f"단위 데이터 없음 — 먼저 python3 tests/e2e/replay.py {unit} check")
    lib = store.library()
    pkg = package.export(lib, lib["plans"][0]["id"])
    path = os.path.join(PKG_DIR, f"{unit}.json")
    json.dump(pkg, open(path, "w", encoding="utf-8"), ensure_ascii=False)
    n = len(pkg["pages"])
    pk[unit] = (path, n)
    for t in take:
        layout.append((k + t, unit, t, name))
    k += n
    c = pkg["plan"].get("content") or {}
    if len(take) < n:                                                   # 일부 쪽만 남기는 단위(14c 뒤표지) — 남는 쪽에 있는 자리의 원고만
        ids = [pid for pid in __import__("core.units.content", fromlist=["x"]).plan_page_ids(pkg["plan"])]
        kept = {(it.get("atom") or {}).get("bind") for p in pkg["pages"] if p["id"] in {ids[t] for t in take} for it in p.get("items") or []}
        c = {key: v for key, v in c.items() if key in kept}
    if name:                                                            # 구성 = 원고 한 벌(레코드) — 이름으로 받는다
        content[name] = [c]
    else:                                                               # 한 번만 찍는 쪽(간지·차례·S 흐름) — 자리마다 문서 차례대로
        for key, v in c.items():
            content.setdefault(key, [])
            content[key] += v if isinstance(v, list) and not ("+" in key) else [v]
for key in [x for x in content if "+" in x]:                           # 흐름 자리 = 문항 목록 그대로(한 줄기)
    content[key] = content[key][0]
TOTAL = k
drop = sorted(set(range(TOTAL)) - {p for p, *_ in layout}, reverse=True)     # 뒤에서부터 지운다(앞 차례가 안 바뀌게)

st = open_doc("스텝바이스텝 워크북 정본 (편집기 제작)")
st += expect_pages(1)
st += [{"clickif": {"at": "#tg-strip", "when": "!view.strip"}, "wait": 1000}]
st += [S("① 단위 문서들을 이 문서 끝에 가져온다 — 문서 패널 「문서 파일 → 가져오기」", 1800)]
for unit, take, name in UNITS:
    path, n = pk[unit]
    st += [S(f"가져오기 — {unit} ({n}쪽)", 900), {"key": "Escape", "wait": 400}, {"key": "Escape", "wait": 600},
           {"pick": {"at": "#side #s-pkg-mode", "value": "append"}, "wait": 500},
           {"upload": {"at": "#side #s-pkg-file", "path": path}, "wait": 3500},
           {"js": f"(() => {{ const k = docPages().length; return '쪽 ' + k; }})()"}]
st += [{"js": f"(() => {{ const k = docPages().length; if (k !== {TOTAL}) throw new Error('가져온 뒤 쪽 수 {TOTAL} 이 아니라 ' + k); return '가져온 쪽 {TOTAL} 확인'; }})()"}]
st += [S(f"② 쓰지 않는 쪽 {len(drop)}개 지우기 — 새 문서의 빈 쪽 · 겹치는 간지 · 14c 의 고정 실전 문제(뒤표지만 남긴다)", 1800)]
for i in drop:
    st += [{"move": f'#rail .pg[data-i="{i}"]', "wait": 400}, {"click": f'#rail .pg[data-i="{i}"] [data-pg-del]', "wait": 1200}]
FINAL = TOTAL - len(drop)
st += [{"js": f"(() => {{ const k = docPages().length; if (k !== {FINAL}) throw new Error('쪽 수 {FINAL} 이 아니라 ' + k); return '남은 쪽 {FINAL} 확인'; }})()"}]
st += [S("③ 구성마다 이름 · 「원고마다 — 지문마다 한 장」 (원고 목록이 구성 이름으로 들어온다)", 1800)]
pos = {}
for j, (_, unit, t, name) in enumerate(layout):
    pos.setdefault(unit, []).append(j)
for unit, take, name in UNITS:
    if not name:
        continue
    left, right = pos[unit]
    for i, nm in ((left, name), (right, name + " — 이어지는 면")):
        st += [{"click": f'#rail .pg[data-i="{i}"]', "wait": 1300}, {"key": "Escape", "wait": 400}, {"key": "Escape", "wait": 700},
               F("#side #s-pname", nm, 700), {"pick": {"at": "#side #s-rep", "value": "each_set"}, "wait": 900}]
st += put_content(content, "④ 견본 원고 넣기 — 구성마다 한 벌(이름 → [레코드]) · 간지 교재명·단원명 · S 문항 목록")
st += [{"shot": "doc_content.png", "wait": 1500}]
st += [S("⑤ 관리에 등록 — 워크북 폴더", 1800), {"key": "Escape", "wait": 400}, {"key": "Escape", "wait": 700},
       {"pick": {"at": "#side #s-reg-series", "value": "workbook"}, "wait": 600},
       {"click": "#side #s-reg", "wait": 3000},
       {"until": "/등록됨|등록 실패/.test((document.querySelector('#s-reg-st') || {}).textContent || '')", "wait": 500},
       {"js": "(() => { const t = document.querySelector('#s-reg-st').textContent; if (!/등록됨/.test(t)) throw new Error(t); return t; })()"},
       {"shot": "registered.png", "wait": 800}]
json.dump(st, open(os.path.join(HERE, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(content, open(os.path.join(HERE, "원고.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("15 단계", len(st), "· 가져온 쪽", TOTAL, "· 남길 쪽", FINAL, "· 구성", sum(1 for *_, n in UNITS if n), "· 원고 키", len(content))
