"""상일보카 01 — 「상일1_상일보카01_내지_인쇄.pdf」(259쪽 · 관리 vocab/xb3c27799, 원본은 같은 폴더 원본.pdf)를 보고 편집기로 손수 만든다.
등록 이름 「상일보카 (편집기 제작)」.

절차: docs/편집기_재현/절차.md 「작업 순서 — 확정」. 만드는 단위 = 면 하나(구성.json — 사용자 확인 16면).
구간마다 색만 다른 면은 따로 만들지 않는다 — 첫 견본 쪽의 색으로 한 장. 값은 모두 원본 PDF(상태.json ref)에서 잰다.
서체는 원본 글자와 겹쳐 고른 시스템 서체(fontmatch.py — 이름 없는 Type3 판):
  Elice DX Neolli OTF 700 — PART · 파트 이름 · MEMO · DAY · 머리 제목 · SANGIL VOCA (0.95~0.96)
  Noto Sans CJK KR 500 — 차례 항목(0.91) · 400 — 부제 · 예문(0.87~0.93)

면(구성.json 번호) — 지금 만드는 면: 2 PART 간지 · 3 PART 차례 · 13 MEMO 면 (고정 면부터, 나머지는 차례로 더한다)
"""
import glob, importlib, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from common import *                                                    # noqa
import common
# ── 13 MEMO 면 — 얇은 띠(연파랑 + 파랑 줄) · MEMO · 가로줄 16개 ─────────────────────────────────────────────
def memo(pno):
    st = pg_new(pno, f"⑬ MEMO 면 — 원본 {pno}쪽", name="MEMO 면")
    el, sp = els(pno), spans(pno)
    band, bline = find(el, "rect", -3, -3), find(el, "rect", -3, 4.8)
    st += rbox(band["x"], band["y"], band["w"], band["h"], band["fill"], label="위 띠")
    st += rbox(bline["x"], bline["y"], bline["w"], bline["h"], bline["fill"], label="띠 아래 파랑 줄")
    lines = sorted((e for e in el if e["k"] == "line"), key=lambda e: e["y"])
    sw = lines[0]["sw"] * MM                                             # 선 굵기 pt → mm (가로줄 = 굵기만큼 높은 상자)
    for k, ln in enumerate(lines):
        st += rbox(ln["x"], ln["y"] - sw / 2, ln["w"], sw, ln["stroke"], label=f"가로줄 {len(lines)}개" if k == 0 else None)
    memo_t = next(e for e in el if e["k"] == "text" and e["text"] == "MEMO")
    st += T(el_line(sp, memo_t), ELICE, 700, label="MEMO — Elice DX Neolli Bold (겹침 0.96)")
    st += done("MEMO 면", f"p{pno}.png")
    return st


# ── 2 PART 간지 — 전면 바탕 · PART 번호 · 파트 이름 · 부제 · 짧은 선 ────────────────────────────────────────
def part_cover(pno):
    st = pg_new(pno, f"② PART 간지 — 원본 {pno}쪽", name="PART 간지")
    el, sp = els(pno), spans(pno)
    s0, _ = full_bg(el, "전면 바탕")
    st += s0
    bar = next(e for e in el if e["k"] == "rect" and e["h"] < 2 and e["w"] < 40)
    st += rbox(bar["x"], bar["y"], bar["w"], bar["h"], bar["fill"], label="짧은 선")
    tx = {e["text"]: e for e in el if e["k"] == "text"}
    part = next(e for t, e in tx.items() if t.startswith("PART"))
    name = max((e for e in tx.values()), key=lambda e: e["size"])
    sub = next(e for e in tx.values() if e is not part and e is not name)
    st += T(el_line(sp, part), ELICE, 700, label="PART 번호 — 원고 자리 「파트 번호」", slot_name="파트 번호", temp="PART 0")
    st += T(el_line(sp, name), ELICE, 700, label="파트 이름 — 원고 자리 「파트 이름」", slot_name="파트 이름", temp="파트 이름", w=100)
    st += T(el_line(sp, sub), NOTO, 400, label="부제 — 원고 자리 「파트 부제」", slot_name="파트 부제", temp="파트 부제 글", w=100)
    CONTENT.setdefault("파트 번호", []).append(part["text"])
    CONTENT.setdefault("파트 이름", []).append(name["text"])
    CONTENT.setdefault("파트 부제", []).append(sub["text"])
    st += done("PART 간지", f"p{pno}.png")
    return st


# ── 3 PART 차례 — 전면 바탕 · 차례 항목(이름 + 엠 공백 + 단어 수) · 항목 위 구분선(흰 35%) ────────────────────
def part_toc(pno):
    st = pg_new(pno, f"③ PART 차례 — 원본 {pno}쪽", name="PART 차례")
    el, sp = els(pno), spans(pno)
    s0, bgc = full_bg(el, "전면 바탕")
    st += s0
    rules = sorted((e for e in el if e["k"] == "rect" and e["h"] < 0.5), key=lambda e: e["y"])
    names = sorted((e for e in el if e["k"] == "text" and e["size"] == 8.0), key=lambda e: e["y"])
    counts = sorted((e for e in el if e["k"] == "text" and e["size"] == 6.0), key=lambda e: e["y"])
    rows = [el_line(sp, e) for e in names]
    crow = [el_line(sp, e) for e in counts]
    lead = round((rows[1]["base"] - rows[0]["base"]) / MM, 2)          # 항목 간격 = 행간(pt)
    rc = mix(rules[0]["fill"], bgc, rules[0].get("opacity", 100) / 100)
    # 구분선 = 단락 경계선(위) — 첫 줄 기준선에서 경계선 아래 끝까지(render rule_above), 굵기 pt
    off = round(rows[0]["base"] - (rules[0]["y"] + rules[0]["h"]), 2)          # mm
    for r, n in zip(rules, rows):
        Ebox(r["x"], r["y"], r["w"], r["h"], rc, pad=0.3, ctol=40)
    for n in rows:
        E({"id": f"t{len(ELEMS[len(PAGES)])}", "x": round(n["x"], 2), "y": round(n["base"] - 8 * MM * 0.8, 2), "w": round(n["x1"] - n["x"], 2),
           "h": round(8 * MM * 1.05, 2), "color": n["color"], "see": n["color"], "ctol": 40, "pad": 1.0, "search": 1.0, "text": n["text"], "size": 8.0, "원고": True})
    st += need_pstyle("차례 항목", {"font": NOTO, "weight": 500, "size": 8.0, "leading": lead, "color": rows[0]["color"],
                                 "rule_above": {"w": round(rules[0]["h"] / MM, 3), "color": rc, "offset": off}})
    st += need_cstyle("차례 단어 수", {"font": NOTO, "weight": 400, "size": 6.0, "color": crow[0]["color"]})
    top = round(top_of(rows[0]["base"], 8.0, NOTO, 500, lead), 2)
    st += text(round(rows[0]["x"], 2), top, round(rules[0]["w"], 2), round(lead * MM * len(rows) + 2, 1), "(1) 차례 이름 000 words", 8.0, rows[0]["color"],
               label="차례 — 한 글상자, 항목마다 한 단락(원고 자리 「차례 이름」 + 엠 공백 + 「차례 단어 수」)", font=NOTO, weight=500, leading=lead)
    st += [{"pick": {"at": '#side select[data-a="style"]', "value": "차례 항목"}, "wait": 700}]
    # 첫 항목 위 경계선은 상자 위 끝보다 3.6mm 위 — 상자를 4mm 올리고 위 인세트 4mm(첫 기준선은 그대로, 경계선이 상자 안에 든다)
    st += [F('#side input[data-it="y"]', round(top + fb_shift(NOTO, 500, 8.0, lead) - 4, 3)), F('#side input[data-a="inset4"]', "4 0 0 0")]
    st += slot("차례 이름+차례 단어 수", label="자리 — 차례 항목(이름 · 단어 수)")
    st += [slot_style("차례 단어 수", "차례 항목")]                         # 한 단락으로 이은 필드는 뒤 필드(단어 수)의 단락 — 그 단락 스타일 「차례 항목」(위 경계선 — 구분선)
    st += slot_inline("차례 이름", sep="\u2003")                         # 이름 뒤 엠 공백(^m) — 원본 이름 끝 ~ 단어 수 사이 2.97mm
    st += grep(0, r"\d+ words", "차례 단어 수", label="GREP 스타일 — 「N words」 → 문자 스타일 「차례 단어 수」")
    CONTENT["차례 이름+차례 단어 수"] = [{"차례 이름": n["text"], "차례 단어 수": c["text"]} for n, c in zip(rows, crow)]   # 흐름 자리 = [항목 {자리: 글} …]
    st += done("PART 차례", f"p{pno}.png")
    return st


# ── 1 표지 · 16 뒤표지 — 전면 바탕 · 로고(그림) · 학교 | 시험 · Day 범위 ─────────────────────────────────────────
# 학교 · 시험 · 범위 글은 원고(책마다 바뀜) — 서체는 원본과 겹쳐 0.9 넘는 시스템 서체가 없다(Pretendard 700 0.75 · Noto 900 0.75 ·
# 받아 본 Pretendard 800 · SUIT 800 0.72~0.73). 원고 글은 모양을 맞대지 않으니 가장 닮은 Pretendard 700 으로 두고 보고에 적는다
PRE = "Pretendard"


def cover(pno, name):
    st = pg_new(pno, f"{'①' if pno == 1 else '⑯'} {name} — 원본 {pno}쪽", name=name, rep=False)
    el, sp = els(pno), spans(pno)
    s0, _ = full_bg(el, "전면 바탕")
    st += s0
    for k, e in enumerate(sorted((e for e in el if e["k"] == "path"), key=lambda e: e["y"])):
        st += crop_image(pno, e, f"로고_{pno}_{k + 1}", f"로고 {k + 1} — 원본 그림 그대로")
    if pno == 1:
        bar = next(e for e in el if e["k"] == "rect" and e["w"] < 2)
        st += rbox(bar["x"], bar["y"], bar["w"], bar["h"], bar["fill"], label="학교 | 시험 사이 세로선")
        tx = {e["text"]: e for e in el if e["k"] == "text"}
        school = next(e for e in tx.values() if e["size"] == 12.5 and e["x"] < 60)
        exam = next(e for e in tx.values() if e["size"] == 12.5 and e["x"] > 60)
        rng = next(e for e in tx.values() if e["text"].startswith("Day"))
        st += T(el_line(sp, school), PRE, 700, label="학교 — 원고 자리 「학교」", slot_name="학교", temp="학교")
        st += T(el_line(sp, exam), PRE, 700, label="시험 — 원고 자리 「시험」", slot_name="시험", temp="시험 이름", w=40)
        st += T(el_line(sp, rng), PRE, 500, label="Day 범위 — 원고 자리 「범위」 (가운데 맞춤)", slot_name="범위", temp="Day 00~00", align="center",
                w=round(rng["w"] + 20, 1))
        CONTENT.setdefault("학교", []).append(school["text"])
        CONTENT.setdefault("시험", []).append(el_line(sp, exam)["text"])
        CONTENT.setdefault("범위", []).append(el_line(sp, rng)["text"])
    st += done(name, f"p{pno}.png")
    return st



# 면 대본 모듈 — face_*.py 마다 FACES = {구성 번호: (함수, 원본 쪽 …)} (여러 작업자가 면마다 따로 짠다)
MODS = {}
for f in sorted(glob.glob(os.path.join(HERE, "face_*.py"))):
    try:                                                                 # 다른 작업자가 짜는 중인 면 파일이 깨져 있어도 나머지 면은 돈다
        m = importlib.import_module(os.path.basename(f)[:-3])
        MODS.update(m.FACES)
    except Exception as e:
        print(f"면 파일 건너뜀 {os.path.basename(f)} — {type(e).__name__}: {e}", file=sys.stderr)

st = open_doc(NAME)
st += expect_pages(1)
for n, (fn, *args) in sorted(MODS.items()):
    if want(n):
        st += fn(*args)
if want(1):
    st += cover(1, "표지")
if want(16):
    st += cover(259, "뒤표지")
if want(2):
    st += part_cover(2)
if want(3):
    st += part_toc(3)
if want(13):
    st += memo(9)
if CONTENT:
    st += put_content(CONTENT)

CONTENT = common.CONTENT
json.dump(st, open(os.path.join(WORK, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
json.dump(ELEMS, open(os.path.join(WORK, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
json.dump(dict(STATE, pages=PAGES, fill=True), open(os.path.join(WORK, "상태.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("단계", len(st), "· 잴 지면", len(PAGES))
