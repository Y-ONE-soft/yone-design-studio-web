"""단위 15 정본 — 제작(녹화 없음). make.py(검사 대본)와 같은 일을 화면이 부르는 서버 주소로 바로 한다.

    python3 tests/e2e/replay/15-정본/build.py [서버 주소]      (기본 http://127.0.0.1:5099)

검사(make.py → replay.py)는 마우스·키보드로 화면 기능이 되는지 확인하고, 제작은 확인된 그 기능을 바로 부른다:
  문서 파일 가져오기  POST /api/units/package            (화면 「문서 파일 → 가져오기」)
  쪽 지우기 · 쪽 순서  POST /api/units/plans · DELETE /api/units/pages   (화면 쪽 ✕ — setPlanIds 와 같게 구간 하나로)
  쪽 이름 · 원고마다   POST /api/units/pages · /api/units/plans          (화면 「이름」·「원고마다」)
  원고 넣기          POST /api/units/plans (content)                   (화면 「원고 넣기」)
  관리에 등록        POST /api/units/register → /api/units/job/<id>     (화면 「관리에 등록」)
차례·이름·원고는 make.py 의 것을 그대로 쓴다(두 길이 같은 문서를 만든다).
"""
import json, os, sys, time, urllib.request
HERE = os.path.dirname(os.path.abspath(__file__))
BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5099").rstrip("/")
G = {"__file__": os.path.join(HERE, "make.py"), "__name__": "u15"}
exec(compile(open(os.path.join(HERE, "make.py"), encoding="utf-8").read().split("st = open_doc(")[0], "make.py", "exec"), G)
UNITS, pk, content, layout, drop = G["UNITS"], G["pk"], G["content"], G["layout"], G["drop"]
NAME = "스텝바이스텝 워크북 정본 (편집기 제작)"


def call(path, body=None, method=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method or ("POST" if data else "GET"), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        j = json.load(r)
    if isinstance(j, dict) and j.get("error"):
        raise RuntimeError(f"{path}: {j['error']}")
    return j


def lib():
    return call("/api/units/library")


t0 = time.time()
# ① 가져오기 — 첫 단위는 새 문서로(검사 대본은 빈 새 문서를 만들고 그 빈 쪽을 지운다 — 남는 쪽은 같다), 나머지는 그 문서 끝에
pid = None
for unit, take, name in UNITS:
    pkg = json.load(open(pk[unit][0], encoding="utf-8"))
    j = call("/api/units/package", {"pkg": pkg, "into": pid} if pid else {"pkg": pkg, "name": NAME})
    pid = j["plan"]
L = lib()
plan = next(p for p in L["plans"] if p["id"] == pid)
ids = [e["page"] for s in plan["sections"] for e in s["pages"]]
print("가져온 쪽", len(ids))
# ② 쓰지 않는 쪽 지우기 — 검사 대본 차례에서 새 문서의 빈 쪽(0)이 없으므로 하나씩 당긴다
gone = [ids[i - 1] for i in G["drop"] if i > 0]
keep = [i for i in ids if i not in gone]
old = {e["page"]: e for s in plan["sections"] for e in s["pages"]}
plan["front"], plan["back"] = [], []
plan["sections"] = [{"id": plan["sections"][0]["id"], "name": plan["sections"][0].get("name", "본문"),
                     "pages": [dict(old[i], page=i, repeat=old[i].get("repeat") or "once") for i in keep]}]   # 화면 setPlanIds 와 같게
call("/api/units/plans", plan)
for i in gone:
    call(f"/api/units/pages?id={i}", method="DELETE")
print("남은 쪽", len(keep))
# ③ 구성마다 이름 · 원고마다
pages = {p["id"]: p for p in lib()["pages"]}
pos = {}
for j, (_, unit, t, name) in enumerate(layout):
    pos.setdefault(unit, []).append(j)
for unit, take, name in UNITS:
    if not name:
        continue
    left, right = pos[unit]
    for i, nm in ((left, name), (right, name + " — 이어지는 면")):
        pg = pages[keep[i]]
        pg["name"] = nm
        call("/api/units/pages", pg)
        for e in plan["sections"][0]["pages"]:
            if e["page"] == keep[i]:
                e["repeat"] = "each_set"
# ④ 원고 넣기
plan["content"] = content
call("/api/units/plans", plan)
# ⑤ 관리에 등록
job = call("/api/units/register", {"plan": pid, "series": "workbook"})["job"]
while True:
    s = call(f"/api/units/job/{job}")
    if s["status"] not in ("queued", "running"):
        break
    time.sleep(1.5)
if s["status"] == "failed":
    sys.exit(f"등록 실패 — {s.get('error')}")
print(f"등록 — {s['result']['pages']}면 · {s['result']['url']} · 문서 {pid} · {time.time() - t0:.0f}초")
