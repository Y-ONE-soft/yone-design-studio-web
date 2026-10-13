"""편집기 화면 글자를 용어집(docs/편집기_재현/용어.md)의 인디자인 말로 바꾼다 — 바꿀 말은 용어집에서만 읽는다.

    python3 tests/e2e/terms.py check   바꿀 곳 목록 → ~/Downloads/편집기재현/용어_바꾸기.html
    python3 tests/e2e/terms.py apply   바꾸기 — 바꾼 뒤 「한글 아닌 글자(코드 · id · 값)는 하나도 안 바뀜」을 확인하고, 아니면 안 바꾼다

바꾸는 곳 = 화면에 보이는 글자만: 태그 사이 글 · title · placeholder · 상태 문구(say · textContent). 저장 데이터 키 · 요소 id · 값은 안 바꾼다.
규칙 = 용어집 각 줄 「옛말: …」 → 그 줄의 굵은 말 + 「바꾸지 않는 것(문맥 예외)」(아래 KEEP · CONTEXT 는 그 절을 옮긴 것).
"""
import html, json, os, re, sys

E2E = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(E2E))
GLOSS = os.path.join(REPO, "docs", "편집기_재현", "용어.md")
FILES = [os.path.join(REPO, "templates", "units_canvas.html")]


def glossary():
    """용어집 → [(옛말, 새 말)] 긴 것부터. 한 줄에 새 말이 여럿(「A · B」)이고 옛말 수가 같으면 차례대로 짝짓는다.
    괄호로 뜻을 단 옛말(면(도구 이름) 등)은 문맥 예외(CONTEXT)로"""
    rules = []
    for ln in open(GLOSS, encoding="utf-8").read().splitlines():
        if not ln.startswith("- **"):
            continue
        for new, olds in re.findall(r"\*\*([^*]+)\*\*\(옛말: ([^)]+)\)", ln):
            rules += [(o.strip(), new) for o in olds.split(",")]
        m = re.match(r"- \*\*([^*]+)\*\*.*? 옛말: (.+)$", ln)
        if not m or "(옛말:" in ln:
            continue
        news = [x.strip() for x in m.group(1).split("·")]
        olds = [o.strip().rstrip(".") for o in re.split(r",\s*", m.group(2).split(". ")[0])]
        olds = [o for o in olds if o and "(" not in o]
        if len(news) > 1 and len(news) == len(olds):
            rules += list(zip(olds, news))
        elif len(news) == 1:
            rules += [(o, news[0]) for o in olds]
    return sorted(set(rules), key=lambda r: -len(r[0]))


# 용어집 「바꾸지 않는 것(문맥 예외)」 — 그 절 그대로
KEEP = ["제본쪽", "왼쪽", "오른쪽", "안쪽", "바깥쪽", "위쪽", "아래쪽", "양쪽", "한쪽", '"오른"}쪽', '"왼" : "오른"}쪽',
        "색 면", "색상 견본", "견본 이름", "들어올 자리", "들어갈 자리", "글 자리", "그 자리만큼", "쌓기 자리", "그 자리엔"]
CONTEXT = [("R 면 ·", "R 사각형 ·"), ("쪽마다", "변마다"), ("네 쪽 같게", "네 변 같게"), ("커서 자리", "커서 위치"), ("자리는 오른쪽 패널", "위치는 오른쪽 패널"),
           ("틀 저장 실패", "문서 저장 실패"), ("폴더(틀)", "폴더(템플릿)"), ("틀에는", "템플릿에는"), ("틀 =", "템플릿 ="), ("순서(틀)", "순서(템플릿)"),
           ("XML 태그 자리", "XML 태그에 해당"), ("같은 이야기의", "같은 스토리의"), ("이 이야기를", "이 스토리를"),
           ("견본은 「보기: 원고」", "레코드 미리 보기는 「보기: 원고」"), ("데이터 병합 자리 표시", "데이터 병합 필드 표시"),
           # 단일 레코드 · 여러 레코드(용어집: 인디자인 데이터 병합 레코드 옵션)
           ("지문마다 한 장", "단일 레코드 — 레코드 하나에 한 장"), ("지문 2개씩 한 장", "여러 레코드 — 한 장에 2개"),
           ("「여러 레코드」 — 원고(지문)가 12개면 이 면을 12장 찍고 한 장에 한 지문씩 넣는다", "레코드 — 단일 레코드는 레코드(지문)가 12개면 이 페이지를 12장 찍고 한 장에 하나씩, 여러 레코드는 한 장에 여럿"),
           ("원고(지문)마다", "레코드마다"), ("「지문마다」", "「단일 레코드」"), ("원고마다 몰아서", "레코드 단위로 몰아서"), ("원고마다 면 한 벌씩", "레코드 하나에 페이지 한 벌씩")]
EXACT = {"면": "사각형", "원고마다": "레코드", "넘치면 이어 갈 면": "스마트 텍스트 리플로우 — 이어 받을 페이지"}                            # 도구 막대 이름(사각형 도구) · 레코드 옵션 칸 이름


AMBIGUOUS = {"면", "구성", "디자인", "카드", "세트", "틀", "문서", "원본", "자리", "쪽", "지면", "목표 PDF", "PDF 등록 카드", "원고 덩어리마다 면 고르기",
             "면 나누기", "구성 나누기", "원본 차례 견본", "되풀이 묶음", "붙어 다니는 쪽", "펼침면 면"}   # 뜻이 여럿이거나 화면에 없는 말 — 자동으로 안 바꾼다(EXPLICIT 표에서 한 줄씩)
WORDS = [("지면", "페이지"), ("쪽 번호", "페이지 번호"), ("쪽번호", "페이지 번호")]      # 뜻이 하나인 짧은 말
NO_BATCHIM = ("페이지", "데이터 필드", "분류", "레코드", "고정 개체", "페이지 크기", "단일 레코드", "여러 레코드", "레코드 미리 보기", "페이지 번호", "문서", "레코드 단위", "스토리")
BATCHIM = ("텍스트 프레임", "그래픽 프레임", "템플릿", "데이터 병합", "텍스트 스레드", "탭 위치", "자리 표시자 텍스트", "사각형")


def convert(t, rules):
    """한 번에 훑어 바꾼다(바꾼 글자는 다시 안 바꾼다) — 문맥 예외(KEEP · CONTEXT) > 용어집 옛말(뜻이 하나인 것) > 짧은 말"""
    if t.strip() in EXACT:
        return t.replace(t.strip(), EXACT[t.strip()])
    if t in EXPLICIT:
        return EXPLICIT[t]
    table = {k: k for k in KEEP}
    table.update({a: b for a, b in rules if a not in AMBIGUOUS and "/" not in b})
    table.update({"두 페이지짜리": "펼침면 상위 페이지"})
    table.update(dict(WORDS))
    table.update(dict(CONTEXT))
    keys = sorted(table, key=len, reverse=True)
    pat = re.compile("|".join(("(?<![가-힣])" if re.match(r"[가-힣]", k) else "") + re.escape(k) for k in keys))
    n = pat.sub(lambda m: table[m.group(0)], t)
    for w in NO_BATCHIM + BATCHIM:                                          # 바뀐 말 뒤 조사(」» 안에 있어도)
        has = w in BATCHIM
        for a, b in (("을", "를"), ("은", "는"), ("이", "가"), ("과", "와"), ("으로", "로")):
            right, wrong = (a, b) if has else (b, a)
            n = re.sub(re.escape(w) + r"([」»]*)" + wrong + r"(?=만|도|부터|까지|$|[^가-힣])", w + r"\1" + right, n)
    return n


EXPLICIT = {}                                                              # 짧은 말이 든 글 — 한 줄씩 정한 것(terms_explicit.json)
_ex = os.path.join(E2E, "terms_explicit.json")
if os.path.exists(_ex):
    EXPLICIT.update(json.load(open(_ex, encoding="utf-8")))


PATS = [r">([^<>`\n]{1,300})<", r'title="([^"]{2,1500})"', r'placeholder="([^"]{1,120})"', r'(?:say|textContent\s*=)\(?\s*[`"]([^`"]{2,300})[`"]']
CODE = re.compile(r"=>|\bconst\b|\breturn\b|\bfunction\b|\bif\s*\(|;\s*$|===|!==|&&|\|\|")


LIT_DATA = {"자리", "빈 면", "본문", "간지", "표지"}                              # 새 데이터 필드 기본 이름 · 새 페이지 기본 이름(저장되는 데이터)
LIT = re.compile(r'"([^"\n]*)"|`([^`]*)`')                                  # 코드 안 글자 묶음 — 표(EXPLICIT)에 똑같이 적힌 것만(데이터 글자는 안 건드리게)


def changes(src, rules):
    seen = set()
    for m in LIT.finditer(src):
        g = 1 if m.group(1) is not None else 2
        t = m.group(g)
        if t in LIT_DATA:                                                  # 코드가 데이터로 쓰는 글자 — 안 바꾼다
            continue
        n = EXPLICIT.get(t, t)
        if t == "면":                                                       # 같은 글자 둘 — 도구 목록의 사각형(["rect", "면"])과 등록 쪽 수(+ "면")
            n = "사각형" if src[max(0, m.start() - 10):m.start()].rstrip().endswith('"rect",') else "페이지"
        if n != t:
            seen.add((m.start(g), m.end(g)))
            yield m.start(g), m.end(g), t, n
    for p in PATS:
        for m in re.finditer(p, src):
            a, b, t = m.start(1), m.end(1), m.group(1)
            if (a, b) in seen or any(x <= a < y for x, y in seen) or not re.search(r"[가-힣]", t) or (p.startswith(">") and CODE.search(t)):
                continue
            seen.add((a, b))
            n = convert(t, rules)
            if n != t:
                yield a, b, t, n


def skeleton(s):
    """한글 · 공백 · 문장부호를 뺀 글 — 코드에 쓰이는 글자(영문 · 숫자 · 따옴표 · 괄호{}[] · $ = ; < > 등)가 그대로인지"""
    return re.sub(r"[가-힣\s「」『』·…—→←↔«»(),.:＋]", "", s)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    rules = glossary()
    rows = []
    for f in FILES:
        src = open(f, encoding="utf-8").read()
        ch = sorted(changes(src, rules), key=lambda c: c[0])
        over = [(c, d) for c, d in zip(ch, ch[1:]) if d[0] < c[1]]            # 겹친 곳(같은 글을 두 틀로 잡음)
        if over:
            sys.exit(f"✗ 겹친 곳 {len(over)} — 정규식을 고친다")
        rows += [(os.path.relpath(f, REPO), src.count("\n", 0, a) + 1, t, n) for a, b, t, n in ch]
        if cmd == "apply":
            dst = src
            for a, b, t, n in reversed(ch):
                dst = dst[:a] + n + dst[b:]
            if skeleton(dst) != skeleton(src):
                sys.exit(f"✗ {f}: 한글 아닌 글자가 바뀐다 — 안 바꿈")
            open(f, "w", encoding="utf-8").write(dst)
            print(f"바꿈 {os.path.relpath(f, REPO)} — {len(ch)}곳 (코드 · id · 값 그대로 확인)")
    out = os.path.expanduser("~/Downloads/편집기재현/용어_바꾸기.html")
    body = "".join(f"<tr><td>{html.escape(f)}:{ln}</td><td>{html.escape(t)}</td><td>{html.escape(n)}</td></tr>" for f, ln, t, n in rows)
    open(out, "w", encoding="utf-8").write(f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>편집기 용어 바꾸기</title><style>
body{{font-family:-apple-system,"Apple SD Gothic Neo",sans-serif;max-width:1200px;margin:0 auto;padding:16px;background:#f6f6f8}}
table{{border-collapse:collapse;width:100%;background:#fff;font-size:13px}} td,th{{border:1px solid #ddd;padding:5px 7px;vertical-align:top;text-align:left}} th{{background:#eee}}
td:first-child{{color:#888;white-space:nowrap}}</style></head><body><h1>편집기 화면 용어 바꾸기 — {len(rows)}곳</h1>
<p>바꿀 말은 용어집(docs/편집기_재현/용어.md)에서만. 화면에 나오는 우리 말은 분류 · 템플릿 등록 둘뿐. 코드 · id · 저장 데이터 이름은 그대로.</p>
<table><tr><th>곳</th><th>지금</th><th>바꿀 말</th></tr>{body}</table></body></html>''')
    json.dump(rows, open(os.path.splitext(out)[0] + ".json", "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(f"{len(rows)}곳 → {out}")


if __name__ == "__main__":
    main()
