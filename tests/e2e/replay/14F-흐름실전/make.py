"""단위 14F 흐름 실전 — 14a(S 실전문제 48~56쪽)를 「흐름 틀」로. 문항이 길어지면 다음 단·쪽으로 밀리고, 쪽이 모자라면 더 생긴다.

고정 배치(14a)는 문항마다 글상자를 원본 자리에 놓았다 — 다른 원고(길이가 다른 문항)를 넣으면 넘치고 겹쳤다(swap_check 14a).
흐름 틀은 인디자인 방식: 문항 전체가 한 줄기 글(자리 「번호+발문+보기+지문+요약문+선지+진술+조건머리+조건+답칸」)이고,
왼쪽·오른쪽 면마다 두 단 글상자를 이어(글 잇기) 흘린다. 자리마다 단락 스타일(브랜드) — 서체·간격(인디자인처럼 앞뒤 간격을 더한다)·
바탕 상자(보기·조건)·「다음 문단과 함께」(번호·발문)·「쪼개지 않기」(선지 묶음)·행 유지(지문 처음 3·마지막 2행).
넘치면 쪽 더하기 — 두 면의 「넘치면 이어 갈 면」을 서로 가리켜 덧쪽이 왼쪽·오른쪽으로 번갈아 생긴다(render.story_spares).

값은 원본에서 잰 것(14a 대본 읽기 함수) — 간격: 발문→지문 6.15 · 지문→선지 8.94 · 선지끼리 5.23 · 선지→다음 발문 10.32 · 지문→다음 발문 8.02 (기준선).
비교는 위치가 아니라 구조로(tests/e2e/flow_check.py): 문항 안 요소 사이 간격 · 문항이 시작하는 쪽·단 — 줄바꿈 한 줄 차이(컴포저 93%)가 뒤로 밀리므로.
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
sys.path.insert(0, REPO)
from mkpage import *                                                    # noqa
import mkpage

U14 = os.path.join(os.path.dirname(HERE), "14a-S실전문제", "make.py")
G = {"__file__": U14, "__name__": "u14a"}
exec(compile(open(U14, encoding="utf-8").read().split("# ── 문서 ─")[0], U14, "exec"), G)    # 원본 읽기(묶음 · 잇기 · 값)
mkpage.SPOT["mm"][:] = [50, 287.5]                                      # 끌어 그리는 빈 띠(꼬리 아래)
MM = 25.4 / 72
NOTO, EL, INK = "Noto Sans CJK KR", "Elice DX Neolli OTF", "#231f20"

# ── 원고 — 문항 목록 [[자리, 글], …] (문항 안 차례 그대로) ──────────
KIND = {"prompt": "발문", "passage": "지문", "opts": "선지", "stmt": "진술", "bogi": "보기", "cond": "조건", "answer": "답칸"}
RECS, cur = [], None
for pno in G["PAGES"]:
    for ci in (0, 1):
        for g in G["GROUPS"][pno][ci]:
            k = g["kind"]
            if k == "num":
                cur = [["번호", "".join(c["c"] for c in g["lines"][0]["num"]).strip()]]
                RECS.append(cur)
                continue
            if g.get("cont_of") or cur is None:
                continue
            if k == "condlabel":
                cur.append(["조건머리", "[조건]"])
                continue
            lines = [ln for c in G["chain"](g) for ln in c["lines"]] if g.get("story_next") else g["lines"]
            s = KIND[k]
            if s == "보기" and any(x[0] == "지문" for x in cur):
                s = "요약문"                                             # 지문 뒤 상자 = 요약문(앞 = 보기) — 간격이 다르다
            cur.append([s, G["gtext"]({"kind": k, "left": g["left"], "lines": lines})])
FIRST = sorted(c["x"] - g["left"] for pno in G["PAGES"] for ci in (0, 1) for g in G["GROUPS"][pno][ci] if g["kind"] == "prompt"
               for c in [next(c for c in g["lines"][0]["chars"] if c["c"].strip() and c["c"] != "\t")])
INLINE_W = round(FIRST[len(FIRST) // 2], 2)                             # 번호 칸 폭 = 발문 첫 글자 - 단 왼쪽 (중앙값)

# ── 단락 스타일 (브랜드) — 값은 원본에서 잰 기준선 간격에서 (인디자인: 앞 문단 뒤 + 이 문단 앞) ──────
JC = {"word_min": 100, "word_max": 133, "letter_min": -5, "letter_max": 250}
B = dict(font=NOTO, size=8, align="justify", tracking=-50)
STY = [
    ("번호", dict(font=EL, size=12, color="#00559f", weight=700, drop=0.55)),
    ("발문", dict(B, leading=14.6, tracking=-40, tsume=40, space_before=2.975, keep_next=True, keep_together=True, jc=JC)),   # 발문은 단 끝에서 안 갈라진다(원본 10번)
    ("지문", dict(B, leading=14, space_before=1.105, space_same=0, keep_first=3, keep_last=2, jc=JC)),
    ("선지", dict(B, leading=12, indent=3.5, indent_first=-3.5, space_before=4.354, space_after=2.653, space_same=1.0, keep_together=True,
                 jc=dict(JC, letter_min=-1))),
    ("진술", dict(B, leading=12, indent=3.5, indent_first=-3.5, space_before=4.354, space_after=2.653, space_same=1.0, keep_together=True, jc=JC)),
    ("보기", dict(B, leading=14, tracking=-49, shade="#f9fcf3", pad=3, pad_top=0.78, pad_bottom=1.1, space_before=2.325, space_after=0.796, jc=JC)),
    ("요약문", dict(B, leading=14, tracking=-49, shade="#f9fcf3", pad=3, pad_top=0.78, pad_bottom=1.1, space_before=4.22, space_after=-1.1, jc=JC)),
    ("조건머리", dict(font=NOTO, size=9.5, weight=500, leading=12, shade="#dbecf2", border=0.5, border_color="#6ab3c7", pad=3, pad_top=1.372,
                    space_before=4.21)),
    ("조건", dict(B, leading=12, tracking=-40, shade="#dbecf2", border=0.5, border_color="#6ab3c7", pad=3, pad_bottom=2.454, space_before=0.83,
                 space_same=0, jc=JC)),
    ("답칸", dict(B, leading=14, tracking=-43, align="left", space_before=2.19)),
]
BIND = "+".join(n for n, _ in STY)
TOP, BOT = 26.87, 278.0                                                  # 단 위 끝 · 아래 끝(원본 단 끝 줄로 잰 프레임 끝)
W = round(82.01 - 50 / 1000 * 8 * MM, 2)                                # 단 폭(꽉 찬 줄 끝 - 끝 글자 뒤 자간)
COLS = {"L": (20.0, 106.0), "R": (21.5, 108.0)}
TEMP = "임시 문항 — 번호·발문·지문·선지가 이 글상자 하나에 흘러 들어온다. 길면 오른쪽 단, 다음 쪽으로 넘어간다."


def style_steps(name, st):
    """브랜드 창 「＋ 단락 스타일」 → 이름 → 칸마다 친다"""
    q = lambda k: f'input[data-st="{name}:{k}"]'
    out = [S(f"단락 스타일 「{name}」", 1200), {"js": f"window.__p = {json.dumps(name)}; true", "wait": 200},
           {"click": "#st-new", "wait": 900}]
    for k, v in st.items():
        if k in ("align", "weight"):
            out.append({"pick": {"at": f'select[data-st="{name}:{k}"]', "value": str(v)}, "wait": 450})
        elif k in ("keep_next", "keep_together"):
            out.append({"click": q(k), "wait": 450})
        elif k == "jc":
            out += [F(q(f"jc.{kk}"), vv, 450) for kk, vv in v.items()]
        else:
            out.append(F(q(k), v, 450))
    return out


def story_box(x, head):
    st = text(x, TOP, W, round(BOT - TOP, 2), TEMP if head else "이어 받는 상자", 8, INK, font=NOTO,
              label="문항 글상자 — 한 줄기 글(자리 여럿)" if head else "이어 받는 글상자 — 같은 이야기")
    if head:
        st += slot(BIND, label="자리 — 번호+발문+…+답칸 (원고에 나온 차례대로 한 줄기)")
        for n, _ in STY:
            st.append({"pick": {"at": f'#side select[data-a="slotfmt.{n}.style"]', "value": n}, "wait": 500})
        st += [S("번호는 발문 첫 줄 앞에 붙인다 — 번호 칸 폭", 1200), {"click": '#side input[data-a="slotfmt.번호.inline"]', "wait": 600},
               F('#side input[data-a="slotfmt.번호.inline_w"]', INLINE_W, 600)]
        st += grep(0, r"_\{([^}]*)\}", bold=False, underline=True, line=round(0.5 * MM, 3), line_off=0.71, line_color=INK, hide=True,
                   label="GREP — 원고의 _{…} 는 밑줄만")
        st += grep(1, r"\{([^}]*)\}", bold=False, weight=500, underline=True, line=round(0.5 * MM, 3), line_off=0.71, line_color=INK, hide=True,
                   label="GREP — 원고의 {…} 는 Medium + 밑줄")
        st += [S("글 잇기 — 새 이야기(넘친 줄은 다음 상자로)", 1200), {"pick": {"at": '#side select[data-a="story"]', "value": "__new"}, "wait": 900}]
    else:
        st += [{"pick": {"at": '#side select[data-a="story"]', "value": "이야기1"}, "wait": 900}]
    return st


def page_set(name, cont=None):
    st = [S(f"면 이름 「{name}」" + (f" · 넘치면 이어 갈 면 「{cont}」" if cont else ""), 1300), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
          F("#side #s-pname", name, 800)]
    if cont:
        st.append({"pick": {"at": "#side #s-cont", "text": cont}, "wait": 900})
    return st


st = open_doc("스텝바이스텝 S 실전문제 — 흐름 틀 (A4)")
st += expect_pages(1)
st += [S("속성 패널 넓히기", 900), {"drag": {"from": '[data-rsz="r"]', "to": [1200, 500]}, "wait": 800}]
st += [S("① 단락 스타일 — 브랜드 창에서 자리마다 하나씩", 1600), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
       {"click": "#side #s-skin-edit", "wait": 1200}]
for n, sty in STY:
    st += style_steps(n, sty)
st += [{"click": "#sheet-x", "wait": 900}]
st += [S("② 왼쪽 면 — 두 단 글상자를 잇는다", 1600)]
st += story_box(COLS["L"][0], True) + story_box(COLS["L"][1], False)
st += columns(2, 4)
st += page_set("왼쪽 면")
st += add_page("③ 오른쪽 면 — 같은 이야기를 이어 받는 두 단")
st += story_box(COLS["R"][0], False) + story_box(COLS["R"][1], False)
st += columns(2, 4)
st += page_set("오른쪽 면", cont="왼쪽 면")
st += [S("왼쪽 면도 넘치면 오른쪽 면으로 — 덧쪽이 왼쪽·오른쪽 번갈아", 1300), {"click": '#rail .pg[data-i="0"]', "wait": 1500}]
st += page_set("왼쪽 면", cont="오른쪽 면")
st += done("흐름 틀", "p_tpl.png")
st += put_content({BIND: RECS}, "④ 원고 넣기 — 문항 목록(바깥 시스템이 보내는 꼴): 쪽이 모자라면 덧쪽이 생긴다")
st += [{"shot": "p_content.png", "wait": 1200}]
json.dump(st, open(os.path.join(HERE, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump({"bind": BIND, "records": RECS}, open(os.path.join(HERE, "원고.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("14F 단계", len(st), "· 문항", len(RECS), "· 번호 칸", INLINE_W)
