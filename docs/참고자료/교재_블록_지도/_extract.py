"""교재_블록_지도.html → 교재_블록_지도.json + README.md (마크다운 전문) 추출기.
python3 _extract.py <html>  — 갱신본이 오면 다시 돌린다."""
import json, re, sys
from collections import OrderedDict
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString, Tag

src = Path(sys.argv[1])
out = src.parent
soup = BeautifulSoup(src.read_text(encoding="utf-8"), "html.parser")

def txt(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).replace(" ,", ",").replace("( ", "(").replace(" )", ")").strip() if el else ""

def md_inline(el):
    """<b>·<span class=mono>·<small> 정도만 마크다운으로."""
    if el is None:
        return ""
    parts = []
    for c in el.children:
        if isinstance(c, NavigableString):
            parts.append(str(c))
        elif isinstance(c, Tag):
            cls = c.get("class") or []
            inner = md_inline(c)
            if c.name == "b":
                parts.append(f"**{inner}**")
            elif "mono" in cls:
                parts.append(f"`{inner}`")
            elif "del" in cls:
                parts.append(f"~~{inner}~~")
            elif "ins" in cls:
                parts.append(f"**{inner}**")
            elif c.name == "br":
                parts.append(" ")
            else:
                parts.append(inner)
    return re.sub(r"\s+", " ", "".join(parts)).strip()

# ---------- header ----------
hdr = soup.select_one("header")
head = OrderedDict(
    eyebrow=txt(hdr.select_one(".eyebrow")),
    title=txt(hdr.select_one("h1")),
    lede=md_inline(hdr.select_one(".lede")),
    meta=[txt(s) for s in hdr.select(".meta span")],
)

sections = soup.select(".wrap > section")
def sec(title_start):
    for s in sections:
        h = s.select_one("h2")
        if h and txt(h).startswith(title_start):
            return s
    raise KeyError(title_start)

# ---------- layers ----------
s_layers = sec("전체 구조")
layers = []
for L in s_layers.select(".layer"):
    body = L.select_one(".layer-body")
    h3 = body.select_one("h3")
    small = h3.select_one("small")
    chips = [txt(c) for c in body.select(".chip")]
    layers.append(OrderedDict(
        no=txt(L.select_one(".layer-no .n")),
        kind=txt(L.select_one(".layer-no .k")),
        title=txt(h3).replace(txt(small), "").strip() if small else txt(h3),
        subtitle=txt(small) if small else "",
        text=" ".join(md_inline(p) for p in body.select("p")),
        chips=chips,
        core="core" in (L.get("class") or []),
    ))
layers_lede = md_inline(s_layers.select_one(".lede"))
layers_note = md_inline(s_layers.select_one(".note"))

# ---------- compositions ----------
def chip(c):
    cls = c.get("class") or []
    i = c.select_one("i")
    return OrderedDict(
        block=txt(i) if i else None,
        text=txt(c).replace(txt(i), "", 1).strip() if i else txt(c),
        absent="none" in cls,
    )

s_comp = sec("2층")
comp_lede = md_inline(s_comp.select_one(".lede"))
comps = []
group = None
for el in s_comp.select_one(".comp").children:
    if not isinstance(el, Tag):
        continue
    if "comp-sub" in el.get("class", []):
        group = txt(el)
        continue
    if "comp-row" not in el.get("class", []):
        continue
    name = el.select_one(".comp-name")
    ojt = name.select_one(".ojt")
    spans = [s for s in name.find_all("span", recursive=False) if "ojt" not in (s.get("class") or [])]
    # flow: 여러 줄(프리미엄북)일 수 있다
    flows = []
    flow_root = el.select_one(".flow")
    inner_flows = flow_root.select(".flow")
    for fl in (inner_flows or [flow_root]):
        seq = []
        label = None
        for c in fl.children:
            if not isinstance(c, Tag):
                continue
            cls = c.get("class") or []
            if "chip" in cls and "plain" in cls and fl is not flow_root and label is None and not c.select_one("i"):
                label = txt(c)  # 블랙북/배N제/화이트북 줄 이름
                continue
            if "rep" in cls:
                seq.append(OrderedDict(repeat=c.get("data-l"), items=[chip(x) for x in c.select(".chip")]))
            elif "chip" in cls:
                seq.append(chip(c))
        flows.append(OrderedDict(label=label, seq=seq))
    note = el.select_one(".comp-note")
    comps.append(OrderedDict(
        group=group,
        ojt=txt(ojt) if ojt else None,
        name=txt(name.select_one("b")),
        sub=txt(spans[-1]) if spans else "",
        flows=flows,
        note=md_inline(note) if note else "",
    ))

# ---------- goods ----------
s_good = sec("이렇게 나누면")
goods = [OrderedDict(title=txt(g.select_one("h3")), text=md_inline(g.select_one("p"))) for g in s_good.select(".good")]

# ---------- changes ----------
s_chg = sec("8블록 초안")
changes = [md_inline(li.select_one("div")) for li in s_chg.select(".verdict li")]

# ---------- blocks ----------
s_blk = sec("수정안")
blocks_lede = md_inline(s_blk.select_one(".lede"))
blocks = []
for b in s_blk.select(".blk"):
    tag = b.select_one(".tag")
    dl = {}
    for dt, dd in zip(b.select("dt"), b.select("dd")):
        dl[txt(dt)] = md_inline(dd)
    blocks.append(OrderedDict(
        id=txt(b.select_one(".blk-no")),
        name=txt(b.select_one("h3")),
        status=txt(tag) if tag else "유지",
        desc=md_inline(b.select_one("p")),
        fields=dl.get("필드", ""),
        variants=dl.get("variant", ""),
        examples=dl.get("실물", ""),
    ))

# ---------- matrix ----------
s_mx = sec("책 × 블록")
mx_lede = md_inline(s_mx.select_one(".lede"))
mx_note = md_inline(s_mx.select_one(".note"))
cols = [txt(th) for th in s_mx.select("thead th")][1:-1]  # 11 blocks
col_ids = [b["id"] for b in blocks]
matrix = []
grp = None
for tr in s_mx.select("tbody tr"):
    if "grp" in (tr.get("class") or []):
        grp = txt(tr)
        continue
    book = txt(tr.select_one("th.book"))
    tds = tr.select("td")
    cells = OrderedDict()
    for cid, cname, td in zip(col_ids, cols, tds[:11]):
        d = td.select_one(".d")
        if d and "f" in d.get("class"):
            v = "핵심"
        elif d and "p" in d.get("class"):
            v = "일부"
        elif "n" in (td.get("class") or []):
            v = txt(td)  # 없음! / 미확인
        else:
            v = ""
        cells[f"{cid} {cname}"] = v
    matrix.append(OrderedDict(group=grp, book=book, blocks=cells, frame=txt(tds[11])))

# ---------- non-blocks ----------
s_nb = sec("블록이 아닌 것")
nb_lede = md_inline(s_nb.select_one(".lede"))
nonblocks = [OrderedDict(title=txt(c.select_one("h3")), items=[md_inline(li) for li in c.select("li")]) for c in s_nb.select(".card")]

# ---------- traps ----------
s_tr = sec("이름만 같은 함정")
tr_lede = md_inline(s_tr.select_one(".lede"))
traps = [OrderedDict(word=txt(t.select_one(".word")), items=[md_inline(li) for li in t.select("li")]) for t in s_tr.select(".trap")]

# ---------- decisions ----------
s_dc = sec("정하셔야 할 것")
decisions = [OrderedDict(q=txt(q.select_one("h3")), text=md_inline(q.select_one("p"))) for q in s_dc.select(".q")]

# ---------- coverage ----------
s_cv = sec("확인 범위")
coverage = [md_inline(li) for li in s_cv.select("details li")]

data = OrderedDict(
    source=src.name, head=head,
    layers=OrderedDict(lede=layers_lede, items=layers, note=layers_note),
    compositions=OrderedDict(lede=comp_lede, items=comps),
    benefits=goods,
    changes_from_8block_draft=changes,
    blocks=OrderedDict(lede=blocks_lede, items=blocks),
    matrix=OrderedDict(lede=mx_lede, legend={"핵심": "핵심 구성", "일부": "일부·부속", "없음!": "있어야 할 것 같은데 인쇄본에 없음"}, rows=matrix, note=mx_note),
    non_blocks=OrderedDict(lede=nb_lede, items=nonblocks),
    traps=OrderedDict(lede=tr_lede, items=traps),
    decisions=decisions,
    coverage=coverage,
)
(out / "교재_블록_지도.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

# ---------- README.md ----------
L = []
L.append(f"# {head['title']} — 참고자료\n")
L.append(f"> {head['eyebrow']} · {' · '.join(head['meta'])}")
L.append(f"> 원본: `교재_블록_지도.html`(브라우저용) · 기계용: `교재_블록_지도.json`(blocks·matrix·compositions) · 이 문서는 원본을 마크다운으로 옮긴 전문이다.\n")
L.append(head["lede"] + "\n")

L.append("## 전체 구조 — 4개 층\n")
L.append(layers_lede + "\n")
for ly in layers:
    core = " **(연동 단위 — 에셋·콘텐츠가 붙는 곳)**" if ly["core"] else ""
    L.append(f"### {ly['no']} {ly['kind']} — {ly['title']}{core}")
    if ly["subtitle"]:
        L.append(f"_{ly['subtitle']}_\n")
    if ly["text"]:
        L.append(ly["text"] + "\n")
    if ly["chips"]:
        L.append("- " + " · ".join(f"`{c}`" for c in ly["chips"]) + "\n")
L.append(f"> {layers_note}\n")

L.append("## 2층 — 라인업별 블록 조합\n")
L.append(comp_lede.replace("점선 상자가 반복 단위이고, 점선 칩은 인쇄본에 없는 블록입니다", "`[반복: …]` 가 반복 단위이고, `(없음)` 표시는 인쇄본에 없는 블록입니다") + "\n")
def flow_md(seq):
    parts = []
    for it in seq:
        if "repeat" in it:
            inner = " + ".join(chip_md(x) for x in it["items"])
            parts.append(f"[반복 {it['repeat']}: {inner}]")
        else:
            parts.append(chip_md(it))
    return " → ".join(parts)
def chip_md(c):
    b = f"{c['block']} " if c["block"] else ""
    s = f"{b}{c['text']}"
    return f"~~{s}~~(없음)" if c["absent"] else s
cur = None
for c in comps:
    if c["group"] != cur:
        cur = c["group"]
        L.append(f"### {cur}\n")
    no = f"{c['ojt']} " if c["ojt"] else ""
    L.append(f"**{no}{c['name']}** — {c['sub']}")
    for fl in c["flows"]:
        pre = f"{fl['label']}: " if fl["label"] else ""
        L.append(f"- {pre}{flow_md(fl['seq'])}")
    if c["note"]:
        L.append(f"  - 비고: {c['note']}")
    L.append("")

L.append("## 이렇게 나누면\n")
for g in goods:
    L.append(f"- **{g['title']}** — {g['text']}")
L.append("")

L.append("## 8블록 초안에서 무엇이 바뀌었나\n")
for i, c in enumerate(changes, 1):
    L.append(f"{i}. {c}")
L.append("")

L.append("## 수정안 — 블록 11종\n")
L.append(blocks_lede + "\n")
L.append("| ID | 블록 | 상태 | 무엇 | 필드(콘텐츠가 줌) | variant(디자인이 고름) | 실물 |\n|---|---|---|---|---|---|---|")
for b in blocks:
    L.append(f"| {b['id']} | {b['name']} | {b['status']} | {b['desc']} | {b['fields']} | {b['variants']} | {b['examples']} |")
L.append("")

L.append("## 책 × 블록\n")
L.append(mx_lede.replace("빨간 열이 이번에 새로 생긴 블록입니다", "이번에 새로 생긴 블록 열은 B1·B3·B7·B8·B11 입니다") + "\n")
L.append("`●` 핵심 구성 · `○` 일부·부속 · `없음!` 있어야 할 것 같은데 인쇄본에 없음 · 열 순서 = B1…B11\n")
L.append("| 계열 | 교재 | " + " | ".join(f"{cid}<br>{cn}" for cid, cn in zip(col_ids, cols)) + " | 틀 |")
L.append("|---|---|" + "---|" * 11 + "---|")
sym = {"핵심": "●", "일부": "○", "": ""}
for r in matrix:
    cells = " | ".join(sym.get(v, v) for v in r["blocks"].values())
    L.append(f"| {r['group']} | {r['book']} | {cells} | {r['frame']} |")
L.append(f"\n> {mx_note}\n")

L.append("## 블록이 아닌 것 — 따로 관리할 층\n")
L.append(nb_lede + "\n")
for nb in nonblocks:
    L.append(f"**{nb['title']}**")
    for it in nb["items"]:
        L.append(f"- {it}")
    L.append("")

L.append("## 이름만 같은 함정\n")
L.append(tr_lede + "\n")
for t in traps:
    L.append(f"**{t['word']}**")
    for it in t["items"]:
        L.append(f"- {it}")
    L.append("")

L.append("## 정하셔야 할 것 (미결 4건)\n")
for d in decisions:
    L.append(f"**{d['q']}**  \n{d['text']}\n")

L.append("## 확인 범위\n")
for c in coverage:
    L.append(f"- {c}")
L.append("")

(out / "README.md").write_text("\n".join(L), encoding="utf-8")
print("layers", len(layers), "comps", len(comps), "blocks", len(blocks), "matrix", len(matrix), "traps", len(traps), "decisions", len(decisions))
