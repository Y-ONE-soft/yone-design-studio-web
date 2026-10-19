"""교재 폴더 → 템플릿 등록 작업표(HTML). 책마다 한 줄: 대표 PDF · 다른 판 · 만든 프로그램 · 첫 쪽 그림 · 진행 상태.

    python3 tests/e2e/worklist.py                         ~/Downloads/교재 2 → ~/Downloads/교재_작업표.html
    python3 tests/e2e/worklist.py <교재 폴더> <출력 html>
    python3 tests/e2e/worklist.py set <책 키 일부> <단계> [메모]   진행 상태 고치고 표 다시 만들기(병렬 세션이 같이 써도 잠금)
      단계: 대기 · 1 원본 올림 · 2 면 나누기 · … · 10 반영(끝) · 건너뜀 (앞 번호만 써도 된다: set 광문보카01 3 "대본 짜는 중")

책 = 한 폴더 안에서 쪽 수가 비슷한(±4) PDF 묶음(같은 책의 여러 판). 참고 · 간지 · _보관… 하위 폴더의 PDF 는 바로 위 책의 다른 판으로 본다.
대표 PDF = 인디자인으로 만든 판이 있으면 그것(진짜 원본), 없으면 '_인쇄' 판, 없으면 가장 최근 판.
진행 상태 = 출력 옆 <이름>.json 의 {책 키: {"step": "...", "note": "..."}} (작업하며 손으로 고친다) + 관리에 이미 등록된 PDF(같은 파일)면 자동으로 「등록됨」.
경로를 누르면 그 파일·폴더가 열린다(file:// 링크 — 브라우저에서 이 html 을 파일로 열었을 때).
"""
import base64, fcntl, glob, hashlib, html, json, os, re, sys, unicodedata, urllib.parse

import fitz

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
nfc = lambda t: unicodedata.normalize("NFC", t)          # macOS 파일 이름은 NFD — 비교·표시는 NFC 로
SET = sys.argv[2:5] if len(sys.argv) > 1 and sys.argv[1] == "set" else None
ARGS = [] if SET else sys.argv[1:]
ROOT = os.path.expanduser(ARGS[0] if ARGS else "~/Downloads/교재 2")
OUT = os.path.expanduser(ARGS[1] if len(ARGS) > 1 else "~/Downloads/교재_작업표.html")
STATE = os.path.splitext(OUT)[0] + ".json"
CACHE = os.path.splitext(OUT)[0] + ".cache.json"           # PDF 정보 · 첫 쪽 그림(파일 크기·시각이 같으면 다시 안 읽는다)
LINEUP = {"단어장": "단어장", "워크북_비블리오": "워크북", "중등부": "중등부", "특강교재": "특강교재",
          "파이널 직전보충": "직전보충", "포켓북": "포켓북", "프리미엄북": "프리미엄북"}
SIDE = re.compile(r"^(참고|간지|원고|_보관.*)$")             # 책 폴더 아래 덧폴더 — 그 책의 다른 판
STEPS = ["대기", "1 원본 올림", "2 면 나누기", "3 대본", "4 가르기", "5 만들기+검사", "6 원고 넣기", "7 잇기·책 검사",
         "8 편집기 제작 등록", "9 맞대기", "10 반영(끝)", "건너뜀"]


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


_cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}


def info(p):
    st = os.stat(p)
    k = f"{p}|{st.st_size}|{int(st.st_mtime)}"
    if k not in _cache:
        _cache[k] = _info(p)
    return _cache[k]


def _info(p):
    d = fitz.open(p)
    r = d[0].rect
    cr = (d.metadata or {}).get("creator") or ""
    made = "인디자인" if "InDesign" in cr else "예전 코드(Vivliostyle)" if "Vivliostyle" in cr else \
        "일러스트레이터" if "Illustrator" in cr else cr[:20] or "알 수 없음"
    z = 96 / r.width
    thumb = "data:image/png;base64," + base64.b64encode(d[0].get_pixmap(matrix=fitz.Matrix(z, z)).tobytes("png")).decode()
    out = {"pages": d.page_count, "mm": f"{r.width / 72 * 25.4:.0f}×{r.height / 72 * 25.4:.0f}", "made": made, "thumb": thumb,
           "mtime": os.path.getmtime(p)}
    d.close()
    return out


def rank(p, i):
    n = os.path.basename(p)
    return (i["made"] == "인디자인", "_인쇄" in n and not re.search(r" \d\.pdf$|CMYK", n), "(최종" in n, i["mtime"])


def url(p):
    return "file://" + urllib.parse.quote(p)


# 관리에 등록된 PDF — 같은 파일(md5)이면 그 카드
cards = {}
for p in glob.glob(os.path.join(REPO, "catalog", "*", "designs", "*", "참고", "*.pdf")):
    s, _, d = p.split(os.sep)[-5:-2]
    cards.setdefault(md5(p), f"{s}/{d}")

# 책 폴더 → PDF 목록
folders = {}
for dp, dns, fns in os.walk(ROOT):
    dns[:] = sorted(d for d in dns if d not in ("build", "assets"))
    dp = nfc(dp)
    pdfs = [os.path.join(dp, nfc(f)) for f in sorted(fns) if f.lower().endswith(".pdf")]
    if not pdfs:
        continue
    book = dp
    while SIDE.match(os.path.basename(book)) and book != ROOT:
        book = os.path.dirname(book)
    folders.setdefault(book, []).extend(pdfs)

items = []
for book, pdfs in sorted(folders.items()):
    meta = {p: info(p) for p in pdfs}
    # 보관 폴더의 옛 판 · 시안 · 견본은 따로 된 책이 아니라 가장 가까운 책의 다른 판
    extra = lambda p: re.search(r"_보관", p) or re.search(r"시안|견본|샘플|메모없음", os.path.basename(p))
    main = [p for p in pdfs if not extra(p)] or pdfs
    groups = []                                          # 쪽 수가 비슷한 판끼리
    for p in sorted(main, key=lambda p: meta[p]["pages"]):
        if groups and abs(meta[p]["pages"] - meta[groups[-1][-1]]["pages"]) <= 4:
            groups[-1].append(p)
        else:
            groups.append([p])
    for p in pdfs:
        if p not in main:
            min(groups, key=lambda g: (os.path.basename(p) not in map(os.path.basename, g),
                                       abs(meta[p]["pages"] - meta[g[0]]["pages"]))).append(p)
    for g in groups:
        rep = max(g, key=lambda p: rank(p, meta[p]))
        rel = os.path.relpath(book, ROOT)
        key = os.path.relpath(rep, ROOT)
        lineup = "표지" if "_표지" in os.path.basename(rep) else LINEUP.get(rel.split(os.sep)[0], rel.split(os.sep)[0])
        items.append({"key": key, "lineup": lineup, "book": rel, "dir": book,
                      "rep": rep, "info": meta[rep], "others": [(p, meta[p]) for p in sorted(g) if p != rep],
                      "card": cards.get(md5(rep)) or next((cards[h] for h in (md5(p) for p in g) if h in cards), None)})

json.dump(_cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False)
lock = open(STATE + ".lock", "w")
fcntl.flock(lock, fcntl.LOCK_EX)                          # 병렬 세션이 같은 표를 고쳐도 덮어쓰지 않게
state = json.load(open(STATE, encoding="utf-8")) if os.path.exists(STATE) else {}
for it in items:                                          # 새 책은 상태 칸을 만들어 둔다(손으로 고치기 쉽게)
    st = state.setdefault(it["key"], {"step": "대기", "note": ""})
    if it["card"] and st["step"] == "대기":
        st["step"] = "1 원본 올림"
if SET:
    want = nfc(SET[0])
    hit = [k for k in state if want in k]
    if len(hit) != 1:
        sys.exit(f"책 키가 {len(hit)}개 맞음 — 더 길게: " + " / ".join(hit[:8]))
    step = next((s for s in STEPS if s == SET[1] or s.split(" ")[0] == SET[1]), None)
    if not step:
        sys.exit("단계는: " + " · ".join(STEPS))
    state[hit[0]] = {"step": step, "note": SET[2] if len(SET) > 2 else state[hit[0]].get("note", "")}
    print("상태:", hit[0], "→", step)
json.dump(state, open(STATE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
fcntl.flock(lock, fcntl.LOCK_UN)

E = html.escape
rows = []
for n, it in enumerate(items, 1):
    i, st = it["info"], state[it["key"]]
    made_cls = "ind" if i["made"] == "인디자인" else "viv" if i["made"].startswith("예전") else "etc"
    others = "".join(f'<li><a href="{url(p)}">{E(os.path.relpath(p, it["dir"]))}</a> <span>{m["pages"]}쪽 · {E(m["made"])}</span></li>'
                     for p, m in it["others"])
    card = f'<a href="http://127.0.0.1:5099/design/{it["card"]}">관리 카드</a>' if it["card"] else ""
    step_i = STEPS.index(st["step"]) if st["step"] in STEPS else 0
    stat = "done" if st["step"] == "10 반영(끝)" else "skip" if st["step"] == "건너뜀" else "doing" if step_i else "todo"
    box = {"done": "☑", "doing": "◐", "skip": "—", "todo": "☐"}[stat]
    word = {"done": "완료", "doing": "진행중", "skip": "건너뜀", "todo": ""}[stat]
    rows.append(f"""<tr data-lineup="{E(it['lineup'])}" data-made="{made_cls}" data-stat="{stat}">
<td class="ck {stat}"><span class="box">{box}</span><small>{word}</small></td><td class="n">{n}</td><td><img src="{i['thumb']}" alt=""></td>
<td><b>{E(it['lineup'])}</b><div class="path"><a href="{url(it['dir'])}">{E(it['book'])}</a></div></td>
<td><a href="{url(it['rep'])}">{E(os.path.basename(it['rep']))}</a><div class="sub">{i['pages']}쪽 · {i['mm']}mm</div>
{f'<details><summary>다른 판 {len(it["others"])}개</summary><ul>{others}</ul></details>' if others else ''}</td>
<td><span class="made {made_cls}">{E(i['made'])}</span></td>
<td><span class="step s{min(step_i, 10)}">{E(st['step'])}</span> {card}<div class="sub">{E(st.get('note', ''))}</div></td></tr>""")

lineups = sorted({it["lineup"] for it in items})
counts = {s: sum(1 for it in items if state[it["key"]]["step"] == s) for s in STEPS}
n_done = counts["10 반영(끝)"]
n_doing = sum(v for k, v in counts.items() if k not in ("대기", "10 반영(끝)", "건너뜀"))
page = f"""<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>교재 등록 작업표</title><style>
:root{{--bg:#f6f5fa;--fg:#1d1b26;--mute:#6b6880;--card:#fff;--line:#e3e0ee;--pp:#7d2ae8;--ind:#1f8a4c;--viv:#b26a00}}
@media (prefers-color-scheme:dark){{:root{{--bg:#16151c;--fg:#ecebf3;--mute:#a19eb4;--card:#211f2a;--line:#34313f}}}}
body{{background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,sans-serif;margin:0;padding:20px 16px}}
h1{{font-size:20px;margin:0 0 4px}} .lead{{color:var(--mute);margin:0 0 14px}}
.bar{{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0}} .bar button{{border:1px solid var(--line);background:var(--card);color:var(--fg);border-radius:16px;padding:4px 12px;cursor:pointer}}
.bar button.on{{background:var(--pp);color:#fff;border-color:var(--pp)}}
.wrap{{overflow-x:auto}} table{{border-collapse:collapse;width:100%;background:var(--card);border-radius:10px;overflow:hidden}}
th,td{{border-bottom:1px solid var(--line);padding:8px;vertical-align:top;text-align:left}} th{{font-weight:600;color:var(--mute);font-size:12.5px}}
td img{{width:64px;border:1px solid var(--line)}} td.n{{color:var(--mute)}} a{{color:var(--pp);word-break:break-all}}
.path,.sub{{color:var(--mute);font-size:12.5px}} details{{font-size:12.5px;margin-top:4px}} details ul{{margin:4px 0;padding-left:18px}} details span{{color:var(--mute)}}
.made{{font-size:12px;padding:2px 8px;border-radius:10px;white-space:nowrap}} .made.ind{{background:#1f8a4c22;color:var(--ind)}} .made.viv{{background:#b26a0022;color:var(--viv)}} .made.etc{{background:#8882}}
.step{{font-size:12px;padding:2px 8px;border-radius:10px;background:#8882;white-space:nowrap}} .step.s10{{background:#1f8a4c33}}
td.ck{{text-align:center;white-space:nowrap;width:52px}} td.ck .box{{font-size:22px;line-height:1;display:block}} td.ck small{{font-size:11.5px;font-weight:600}}
td.ck.doing{{color:#d97706}} td.ck.done{{color:#1f8a4c}} td.ck.skip,td.ck.todo{{color:var(--mute)}}
.note{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;margin:10px 0}}
</style>
<h1>교재 등록 작업표</h1>
<p class="lead">{E(ROOT)} · 책 {len(items)}권 · ☑ 완료 {n_done} · ◐ 진행중 {n_doing} · ☐ 대기 {counts["대기"]}</p>
<div class="note">한 줄 = 템플릿으로 올릴 책 하나. <b>대표 PDF</b>를 누르면 파일이, <b>폴더 경로</b>를 누르면 폴더가 열린다.
<b>만든 프로그램</b>: <span class="made ind">인디자인</span> 이 진짜 원본, <span class="made viv">예전 코드(Vivliostyle)</span> 는 예전 코드 조판으로 다시 뽑은 책.
진행 상태는 편집기 재현 절차 10단계. 이 표는 작업할 때마다 다시 만든다.</div>
<div class="bar" id="f-line"><button class="on" data-v="">전체</button>{''.join(f'<button data-v="{E(l)}">{E(l)}</button>' for l in lineups)}</div>
<div class="bar" id="f-stat"><button class="on" data-v="">모든 상태</button><button data-v="todo">☐ 대기</button><button data-v="doing">◐ 진행중</button><button data-v="done">☑ 완료</button></div>
<div class="bar" id="f-made"><button class="on" data-v="">모든 판</button><button data-v="ind">인디자인 원본만</button><button data-v="viv">예전 코드만</button></div>
<div class="wrap"><table><thead><tr><th>상태</th><th>#</th><th>첫 쪽</th><th>라인업 · 폴더</th><th>대표 PDF</th><th>만든 프로그램</th><th>진행</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<script>
const f = {{line: "", made: "", stat: ""}};
function apply() {{ document.querySelectorAll("tbody tr").forEach(tr => {{
  tr.style.display = (!f.line || tr.dataset.lineup === f.line) && (!f.made || tr.dataset.made === f.made) && (!f.stat || tr.dataset.stat === f.stat) ? "" : "none"; }}); }}
for (const [id, k] of [["f-line", "line"], ["f-made", "made"], ["f-stat", "stat"]]) document.getElementById(id).addEventListener("click", e => {{
  const b = e.target.closest("button"); if (!b) return; f[k] = b.dataset.v;
  b.parentNode.querySelectorAll("button").forEach(x => x.classList.toggle("on", x === b)); apply(); }});
</script>"""
open(OUT, "w", encoding="utf-8").write(page)
print(OUT, f"· 책 {len(items)}권 · 상태 {STATE}")
