"""문항 IR -> 시험지 HTML (Vivliostyle Paged Media 용).

레이아웃 결정은 전부 CSS(exam_theme.css)에 있고 여기서는 의미 마크업만 낸다.
문항 한 개 = <section class="q"> 이고, CSS 의 break-inside:avoid 가
"한 문제가 페이지(단)를 넘어가지 않는다"는 요구를 강제한다.
"""
import html
import re

RE_ABC_SPLIT = re.compile(r"\s*(?:……|·{3,}|\.{3,}|…{2,}|―{2,})\s*")


def esc(s):
    return html.escape(s, quote=False)


def _run_html(r, boxify=False):
    """run -> inline HTML. boxify: 밑줄/네모를 모두 네모(어휘 선택)로 본다."""
    if r.get("blank"):
        return '<span class="blank"></span>'
    t = esc(r["t"])
    if not t:
        return ""
    if r.get("box") or (boxify and r.get("ul")):
        # 네모 안 낱말은 한 줄에 두고 슬래시로 구분한다 (2줄 스택 금지 — 행간이 튄다)
        words = [w.strip() for w in re.split(r"\s*/\s*", r["t"].strip()) if w.strip()]
        inner = esc(" / ".join(words)) if words else t
        return f'<span class="boxword">{inner}</span>'
    if r.get("ul"):
        t = f"<u>{t}</u>"
    if r.get("bold"):
        t = f"<b>{t}</b>"
    if r.get("italic"):
        t = f"<i>{t}</i>"
    if r.get("sup"):
        t = f"<sup>{t}</sup>"
    elif r.get("sub"):
        t = f"<sub>{t}</sub>"
    return t


# (A)/(B)/(C) 라벨과 그 뒤 네모가 줄바꿈으로 갈라지지 않게 묶는다.
_LABEL_BOX = re.compile(r'(\((?:A|B|C)\)\s*)(<span class="boxword">[^<]*</span>)')


def _runs_html(runs, boxify=False):
    out = "".join(_run_html(r, boxify) for r in runs)
    return _LABEL_BOX.sub(r'<span class="nb">\1\2</span>', out)


def _choices_html(item):
    chs = item["choices"]
    if not chs:
        return ""
    texts = ["".join(r["t"] for r in c["runs"]) for c in chs]

    # (A)(B)(C) 어휘 선택: 구분자로 쪼개 3열 격자로 정렬
    if item["abc_header"]:
        rows = []
        for c, t in zip(chs, texts):
            cells = RE_ABC_SPLIT.split(t.strip())
            if len(cells) < 2:
                cells = [t.strip()]
            tds = "".join(f"<span>{esc(x)}</span>" for x in cells)
            rows.append(f'<li><span class="mk">{esc(c["label"])}</span>{tds}</li>')
        head = ('<li class="abc-head"><span class="mk"></span>'
                '<span>(A)</span><span>(B)</span><span>(C)</span></li>')
        return f'<ol class="choices abc">{head}{"".join(rows)}</ol>'

    # 한 줄 배열은 기호형 선지(ⓐ ⓑ …)에만. 낱말 선지까지 인라인으로 돌리면
    # 그 문항만 지면 형식이 튀고 선지 간격이 제각각이 된다 (검수 지적).
    cls = "choices"
    if max(len(t) for t in texts) <= 4:
        cls += " inline"
    lis = "".join(
        f'<li><span class="mk">{esc(c["label"])}</span>'
        f'<span class="ct">{_runs_html(c["runs"])}</span></li>'
        for c in chs)
    return f'<ol class="{cls}">{lis}</ol>'


def _item_html(item):
    boxify = item["abc_header"]
    q = _runs_html(item["question"])
    score = f' <span class="score">[{item["score"]:.1f}점]</span>' if item["score"] else ""

    body = []
    for runs in item["passage"]:
        body.append(f'<p>{_runs_html(runs, boxify)}</p>')
    for n in item["notes"]:
        body.append(f'<p class="note">{esc(n)}</p>')
    passage = f'<div class="passage">{"".join(body)}</div>' if body else ""

    return (
        f'<section class="q" id="q{item["n"]}">'
        f'<p class="stem"><span class="qnum">{item["n"]}.</span> {q}{score}</p>'
        f'{passage}'
        f'{_choices_html(item)}'
        f'</section>'
    )


def _answer_table(items, answers):
    cells = []
    for it in items:
        a = answers.get(it["src"], "")
        cells.append(f'<li><span class="mk">{it["n"]}</span>'
                     f'<span class="av">{esc(a)}</span></li>')
    return ('<section class="answers"><h2>정답</h2>'
            f'<ol class="anslist">{"".join(cells)}</ol></section>')


def build_html(doc, cfg, answers=None, css="exam_theme.css"):
    items = doc["items"]
    head = (
        '<meta charset="utf-8">'
        f'<title>{esc(cfg["title"])}</title>'
        f'<link rel="stylesheet" href="{css}">'
    )
    # 제목 아래 한 줄 정보 — 문항 수·총점은 조판 데이터에서 계산한다.
    total = round(sum(it.get("score") or 0 for it in items), 1)
    info = " · ".join(x for x in (
        f"선택형 {len(items)}문항",
        f"{total:g}점",
        cfg.get("exam_date_short", ""),
    ) if x)
    masthead = (
        '<header class="masthead">'
        f'<p class="line1">{esc(cfg["subtitle"])}</p>'
        f'<h1><span class="period">{esc(cfg["period"])}</span>'
        f'<span class="maintitle">{esc(cfg["title"])}</span></h1>'
        f'<p class="info">{esc(info)}</p>'
        '</header>'
    )
    running = (
        '<div class="runhead" role="presentation">'
        f'<span class="rh-title">{esc(cfg["title"])}</span></div>'
    )
    body = "".join(_item_html(it) for it in items)
    ans = _answer_table(items, answers) if answers else ""
    return (
        f"<!doctype html><html lang=ko><head>{head}</head><body>"
        f"{running}{masthead}"
        f'<main class="flow">{body}</main>'
        f"{ans}"
        "</body></html>"
    )
