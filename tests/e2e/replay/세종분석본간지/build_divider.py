"""세종고 분석본 간지 템플릿 — 문서 묶음(yone-units-doc)을 만들어 임시 카탈로그에서 편집기 제작으로 등록한다.
값은 원본 세종1_분석본01 1쪽(재단 기준 pt → mm). 고정 그림(테두리 점선 · 중간 고사 · 1학년 2학기 · 2026 · 월계수 · 권 번호 원 · 학습 가이드 카드)은
원본에서 원고 자리 글만 지운 SVG(divider_art.py), 원고 자리 둘(권번호 · 교재명+강제목)은 글상자.
학교 「세종고」는 그림에 남긴다 — 원본 TT 옴니고딕 L 이 시스템 서체에 없다(2026-10-28, Pretendard 로 바꿔 넣었더니 모양이 달랐다)."""
import base64, json, os, shutil, sys
# build_divider.py <스튜디오 리포> <그림 폴더(divider_art.py 가 낸 SVG)> <앞말> <이름> <글 색> <교재명> <강제목>
#   중간(남색): … out sejong_divider "세종고 분석본 간지 (편집기 제작)" "#183d61" "공통영어2 비상(홍) Unit 1" "A Road Ahead"
#   기말(버건디): … out sejong_final_divider "세종고 분석본 간지 기말 (편집기 제작)" "#582a31" "공통영어2 비상(홍) Unit 3" "The Gift of Art"
WT, S, STEM, NAME, NAVY, BOOK, LESSON = sys.argv[1:8]
TMP = os.path.join(S, "cat_tmp")
if os.path.exists(TMP):
    shutil.rmtree(TMP)
shutil.copytree(os.path.join(WT, "catalog"), TMP)
os.environ["YONE_CATALOG_DIR"] = TMP
os.environ["PATH"] = "/opt/homebrew/bin:" + os.environ["PATH"]
sys.path.insert(0, WT)
sys.path.insert(0, os.path.join(WT, "tests", "e2e"))
from mkpage import face, top_of, MM                                      # noqa: E402

PT = 0.352778
GRAY = "#373d41"
b64 = lambda p: base64.b64encode(open(p, "rb").read()).decode()


def text(x, y, w, size, color, txt, font, weight, leading=None, align="center", bind=None, extra=None):
    a = {"t": "text", "x": 0, "y": 0, "w": w, "h": round((leading or size * 1.45) * PT * 1.03, 3), "font": font, "size": size, "color": color,
         "text": txt, "leading": leading or round(size * 1.45, 3), "align": align, "weight": weight, "auto_size": "height"}
    if bind:
        a["bind"] = bind
    a.update(extra or {})
    return {"x": round(x, 3), "y": round(y, 3), "w": w, "atom": a}


# 기준선 → 글상자 위: top_of 에 첫 판에서 잰 차이(+pt)를 더한다(글꼴마다 7~10pt — 편집기 글상자 위 여백)
# 권 번호 — Myriad Pro Bold 27.6pt, 원 가운데(축 105mm)
vol = text(93, top_of(448.0 * PT, 27.6, "Myriad Pro", 700) + 7.3 * PT, 24, 27.6, "#f0efea", "«권번호»", "Myriad Pro", 700, bind="권번호")
# 교재명 + 강제목 — 한 글상자에 번갈아(쌍 수는 원고만큼). 행간 · 단락 뒤 간격은 원본 기준선 간격(02권 두 쌍)에서
# 글상자 가운데는 재단 가운데보다 1mm 오른쪽(원본 두 권 다 글 가운데 308.98pt · 재단 가운데 306.14pt)
# 자간은 원본 글자 간격에서: 글자마다 원본 x 와 맞대어 밀림이 0 이 되는 값 — 교재명 -40, 강제목 +50
TR1, TR2 = -40, 50
# 편집기는 줄 끝 글자 뒤 자간까지 넣어 가운데를 잡는다 — 원본(두 줄 다 글 가운데 308.98pt)에 맞추려 그 반만큼 단락 들여쓰기로 민다:
# 교재명 오른쪽 들여쓰기 0.64pt(=40×16/1000) · 강제목 왼쪽 들여쓰기 0.7pt(=50×14/1000). 편집기 정렬을 바꾸면 다른 템플릿이 원본에서 멀어졌다(2026-10-28 regcheck)
b1, k1, b2 = 509.1 * PT, 539.9 * PT, 592.5 * PT
asc, desc, _ = face("Gmarket Sans", 700)
r = asc - desc
s1, s2 = 16 * PT, 14 * PT
lead = (k1 - b1) - r * (s2 - s1) / 2
after = round((b2 - k1) - lead - r * (s1 - s2) / 2, 2)
LP = round(lead / PT, 2)
top = top_of(b1, 16, "Gmarket Sans", 700, LP) + 8.5 * PT   # 첫 판에서 잰 기준선 차(편집기 글상자 위 여백) — 다시 재서 맞춤
lines = text(11, top, 190, 16, NAVY, "«교재명+강제목»", "Gmarket Sans", 700, leading=LP, bind="교재명+강제목",
             extra={"tracking": TR1, "slot_fmt": {"교재명": {"style": "교재명"}, "강제목": {"style": "강제목"}}})

art = lambda src: {"x": -3, "y": -3, "atom": {"t": "image", "x": 0, "y": 0, "w": 216, "h": 303, "src": src}}
P1, P2 = "page_sjdiv1", "page_sjdiv2"
pages = [{"id": P1, "name": "간지", "spec": "a4", "mirror": True, "zones": [], "idv": 2, "items": [art(STEM), vol, lines]},
         {"id": P2, "name": "간지 학습 가이드", "spec": "a4", "mirror": True, "zones": [], "idv": 2, "items": [art(STEM + "_guide"), vol, lines]}]
skin = {"id": "doc_plan_" + STEM, "name": NAME + " 스타일",
        "tokens": {"color": {"ink": "#231f20", "white": "#ffffff", "rule": "#b8b8b8", "gray": "#e6e6e6"}, "font": {"body": "Noto Sans CJK KR"}},
        "styles": {"교재명": {"font": "Gmarket Sans", "size": 16, "color": NAVY, "weight": 700, "leading": LP, "align": "center", "tracking": TR1, "indent_right": 0.226},
                   "강제목": {"font": "Gmarket Sans", "size": 14, "color": GRAY, "weight": 500, "leading": LP, "align": "center", "space_after": after, "tracking": TR2, "indent": 0.247}},
        "idv": 2, "cstyles": {}, "images": {STEM: f"_img/{STEM}.svg", STEM + "_guide": f"_img/{STEM}_guide.svg"}}
plan = {"id": "plan_" + STEM, "name": NAME, "spec": "a4", "front": [], "back": [], "skin": skin["id"],
        "sections": [{"id": "s1", "name": "본문", "pages": [{"page": P1, "repeat": "each_set"}, {"page": P2, "repeat": "each_set", "구분": "학습 가이드"}]}],
        "content": {"권번호": ["1"], "교재명+강제목": [{"교재명": BOOK, "강제목": LESSON}]}}
src = json.load(open(os.path.join(WT, "catalog/analysis/designs/x009d5556/units.json"), encoding="utf-8"))
pkg = {"kind": src["kind"], "v": src["v"], "plan": plan, "pages": pages, "parts": [], "blocks": [], "skin": skin, "specs": src["specs"],
       "images": {k: {"name": f"{k}.svg", "b64": b64(os.path.join(S, f"{k}.svg"))} for k in (STEM, STEM + "_guide")},
       "fonts": {"MyriadPro-Bold.otf": b64(os.path.expanduser("~/Library/Fonts/MyriadPro-Bold.otf"))}}
json.dump(pkg, open(os.path.join(S, f"{STEM}_pkg.json"), "w", encoding="utf-8"), ensure_ascii=False)
print("LP", LP, "after", after, "lines top", round(top, 2))

from core.units import package                                           # noqa: E402
from routes.units import register_design                                 # noqa: E402
pid, rep = package.load(pkg)
print("들여옴", pid, rep)
res = register_design(pid, "analysis", NAME)
print(res)
