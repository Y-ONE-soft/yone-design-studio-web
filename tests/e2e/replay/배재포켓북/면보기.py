"""배재1 포켓북 면 보기 — 만든 면마다 원본(왼쪽) · 결과(오른쪽) 그림과 판정을 한 화면에.

    python3 tests/e2e/replay/배재포켓북/면보기.py      → ~/Downloads/편집기재현/배재포켓북_면보기.html 을 만들고 연다
"""
import html, json, os, subprocess

OUT = os.path.expanduser("~/Downloads/편집기재현")
FACES = [  # (번호, 면 이름, 단위, 원본 쪽들)
    (1, "앞면", "배재포켓북@1", [1]),
    (2, "뒷면", "배재포켓북@6", [118]),
    (3, "분석 면 · 교과서", "배재포켓북@2", [2]),
    (4, "분석 면 · 모의고사", "배재포켓북@2", [42]),
    (5, "분석 면 · 삽화 · 모의고사", "배재포켓북@5", [44]),
    (6, "암기 TEST + 정답 · 교과서", "배재포켓북@4", [12, 13]),
    (7, "암기 TEST + 정답 · 모의고사", "배재포켓북@4", [46, 47]),
    (8, "FLOWNOTE · 교과서 · 3칸", "배재포켓북@3", [3]),
    (9, "FLOWNOTE · 교과서 · 4칸", "배재포켓북@3", [5]),
    (10, "FLOWNOTE · 모의고사 · 4칸", "배재포켓북@3", [45]),
]

def verdict(unit):
    try:
        return json.load(open(os.path.join(OUT, unit, "판정.json"), encoding="utf-8"))
    except Exception:
        return {}


rows = []
for no, name, unit, pages in FACES:
    unit = max((unit, unit + "~바로"), key=lambda u: verdict(u).get("때", ""))   # 사람 조작 판 · 바로 넣기 판 중 나중 것
    v = verdict(unit)
    imgs = [p for p in pages if os.path.exists(os.path.join(OUT, unit, f"p{p}_side.png"))]
    if not imgs:
        state = "아직 결과 없음"
    elif v.get("통과"):
        state = "통과"
    else:
        mine = [w for w in v.get("이유", []) if any(f"p{p}" in w for p in pages)] if v else []
        state = "실패 — " + " · ".join(mine[:4]) if mine else ("통과(이 면 요소)" if v else "판정 없음")
    pics = "".join(f'<figure><img src="{html.escape(unit)}/p{p}_side.png" loading="lazy"><figcaption>원본 {p}쪽 (왼쪽 원본 · 오른쪽 결과)</figcaption></figure>' for p in imgs)
    rows.append(f'<section><h2>{no}. {html.escape(name)} <span class="{"ok" if state.startswith("통과") else "no"}">{html.escape(state)}</span></h2>'
                f'<p class="when">{html.escape(v.get("때", ""))}</p>{pics}</section>')

page = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>배재1 포켓북 면 보기</title><style>
body{{font-family:-apple-system,"Apple SD Gothic Neo",sans-serif;margin:0 auto;max-width:1400px;padding:16px;background:#f4f4f6;color:#222}}
h1{{font-size:20px}} h2{{font-size:16px;margin:0 0 6px}} section{{background:#fff;border-radius:8px;padding:14px;margin:14px 0}}
.ok{{color:#147a3d;font-weight:600}} .no{{color:#b3261e;font-weight:600}} .when{{color:#888;font-size:12px;margin:0 0 8px}}
figure{{margin:0 0 10px}} img{{max-width:100%;border:1px solid #ddd}} figcaption{{font-size:12px;color:#666}}
</style></head><body><h1>배재1 포켓북 — 면 10개 (원본 · 결과)</h1>
<section><h2>진행 — 10단계 중 5단계(만들기 + 검사)</h2><p>1 원본 올리기 ✓ · 2 면 나누기 ✓ · 3 대본 짜기 ✓ · 4 가르기 ✓ · <b>5 만들기 + 검사 ← 지금</b> · 6 원고 넣기 · 7 잇기 · 책 만들기 검사 · 8 편집기 제작 등록 · 9 맞대기 · 10 반영</p></section>{"".join(rows)}</body></html>"""
dst = os.path.join(OUT, "배재포켓북_면보기.html")
open(dst, "w", encoding="utf-8").write(page)
print(dst)
subprocess.run(["open", dst])
