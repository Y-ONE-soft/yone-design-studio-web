"""정본 — 「스텝바이스텝 워크북 정본 (블루·베이지·브릭, A4)」 원본 PDF(274면, 한영1_워크북01(마더텅11강)_내지(수정).pdf)를 보고
편집기로 손수 만든다. 등록 이름 「스텝바이스텝 워크북 정본 (편집기 제작 최종)」.

절차: docs/편집기_재현/절차.md 「작업 순서 — 확정」. 이 대본 하나가 문서 하나를 처음부터 만든다 — 구성은 아래 차례대로 하나씩 덧붙인다.
값은 모두 원본 PDF(상태.json ref)에서 잰다. 예전 단위·문서의 결과물은 가져오지 않는다(만드는 방법·도구 함수는 쓴다).
구성마다 「검사 통과」 뒤에 다음 구성. 원고 자리 요소는 elems 에 "원고": true (상태.json 원고_허용_mm 안이면 통과).

구성 차례(원본 구성 판정 — 관리 지면 보기와 같다):
  1 STEPBYSTEP(속표지 1쪽) · 2 STEP 간지(2·124·196쪽) · 3 차례(3·125·197쪽)
  4 A어휘선택(4~23) · 5 A본문OX(24~43) · 6 B본문정리(44~63) · 7 B내용종합(64~83) · 8 C문장배열(84~103) · 9 C빈칸어휘(104~123)
  10 A어법선택(126~145) · 11 B어법OX(146~165) · 12 C빈칸어법(166~185) · 13 C영작배열(186~195)
  14 S실전문제(198~272, 흐르는 쪽 — 고정 부분도 요소 목록에) · 15 MEMO(273) · 16 뒤표지(274)
"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from mkpage import *                                                    # noqa
import pymupdf
STATE = json.load(open(os.path.join(HERE, "상태.json"), encoding="utf-8"))
REF = pymupdf.open(os.path.join(REPO, STATE["ref"]))
NAME = "스텝바이스텝 워크북 정본 (편집기 제작 최종)"
ELEMS = {}                                                              # 지면 차례(1부터) → 맞댈 요소

st = open_doc(NAME)
st += expect_pages(1)
# ── 구성 1부터 여기에 덧붙인다 ─────────────────────────────────

json.dump(st, open(os.path.join(HERE, "steps.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(ELEMS, open(os.path.join(HERE, "elems.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("정본 단계", len(st), "· 잴 지면", len(ELEMS))
