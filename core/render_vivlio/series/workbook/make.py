"""만들기 — 워크북 사다리를 **한 칸씩** 지면으로 본다.

    부품(parts)  역할마다 원고 단락 하나 → 그 역할이 그리는 지면 조각
    틀(frames)   원고 없이 빈 칸 + 껍데기(머리말·탭·쪽번호) + 간지
    스텝(step)   틀 + 부품 + 지문 n개 → 구간 하나
    책(book)     `book.py render --sample` / `build` — 여기서 다시 만들지 않는다

책은 `render.document()` 가 만든다. 그 아래 칸은 **같은 함수를 일부만** 불러
따로 본다 — 그리는 코드가 둘이 되면 둘이 어긋난다.

산출은 `build/make_<칸>.html`. `index.html` 과 같은 폴더라 테마·서체·손잡이
링크(`theme.css`, `fonts/…`, `knobs.css`)가 그대로 맞는다.
"""
import os

from core.render_vivlio.series.workbook import data as data_mod
from core.render_vivlio.series.workbook import render as R
from core.render_vivlio.series.workbook import roles

# 부품 목록 순서 = 역할 어휘 순서(구체적인 것부터) + 역할 어휘 밖의 둘
PART_ORDER = [r for r, _ in roles.ROLE_WORDS] + [roles.BASIC, "intro"]

# 역할 → 사람이 읽는 부품 이름. 없으면 역할 이름 그대로.
PART_NAMES = {
    "vocab_sel": "어휘 선택 지문", "box_body": "본문 박스", "ox_item": "O/X 문항",
    "sum_topic": "내용 정리 · 주제", "sum_title": "내용 정리 · 제목",
    "sum_line": "내용 정리 · 줄", "b2_q": "내용 종합 발문", "b2_choice": "내용 종합 선지",
    "arr_line": "문장 배열 줄", "arr_given": "주어진 문장", "arr_bottom": "문장 배열 하단 지문",
    "blank_vocab": "빈칸 어휘", "blank_kr": "빈칸 해석", "gram_sel": "어법 선택 지문",
    "gram_bottom": "어법 선택 하단(주황)", "gram_ox": "어법 O/X", "blank_gram": "빈칸 어법",
    "write_kr": "영작 배열 해석", "write_box": "영작 배열 보기",
    "q_prompt": "하단 문제 발문", "q_passage": "하단 문제 지문", "q_choice": "하단 문제 선지",
    "s3_q": "실전 발문", "s3_passage": "실전 지문", "s3_choice": "실전 선지",
    "s3_bg": "실전 배경 상자", "s3_cond": "실전 <조건>", "s3_bogi": "실전 <보기>",
    "s3_answer": "실전 답란", "s3_word": "실전 영단어",
    "basic": "기본 줄(라벨·빈 줄·아이콘)", "intro": "실전 세트 안내문",
}

# 틀 5종 — 어느 스텝을 대표로 보여 줄지
FRAME_KEYS = {
    "a1": "step1_a1", "sheet": "step1_a2", "pair": "step1_b1",
    "flow": "step2_c2", "s3": "step3",
}
FRAME_NAMES = {
    "a1": "상·하 두 칸 고정 (지문 2개 = 한 면)",
    "sheet": "한 칸 (지문 1개 = 한 면, 길면 이어짐)",
    "pair": "상 지문 + 하 문제 (지문 1개 = 한 면)",
    "flow": "흘림 (면 수는 조판이 정함)",
    "s3": "2단 흘림 (실전 문제)",
}

_CSS = """
.mk-part { margin: 0 0 6mm; padding: 2mm 3mm; border: 0.3pt dashed #999; break-inside: avoid; }
.mk-lab { font: 7pt/1.4 -apple-system, "Apple SD Gothic Neo", sans-serif; color: #888; margin-bottom: 1.5mm; }
.mk-lab b { color: #333; }
.mk-head { font: 700 11pt/1.4 -apple-system, "Apple SD Gothic Neo", sans-serif; margin: 0 0 4mm; }
"""


def _reset():
    """`render.write()` 가 하는 되돌리기 — 문서 순서 번호들."""
    R._SIDX[0] = 0
    R._PGI[0] = 0
    R._BIDX[0] = 0
    del R.PGMETA[:]


def _doc(title, body):
    return ("<!DOCTYPE html>\n<html lang=\"ko\">\n<head>\n<meta charset=\"utf-8\">\n"
            f"<title>{R.esc(title)}</title>\n<style>\n{R.font_css()}\n{_CSS}</style>\n"
            "<link rel=\"stylesheet\" href=\"theme.css\">"
            + R.stage.BOOK_CSS_LINKS + "\n</head>\n<body>\n" + body + "\n</body>\n</html>\n")


def _write(build_dir, name, text):
    os.makedirs(build_dir, exist_ok=True)
    p = os.path.join(build_dir, name)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


# ── 부품 ────────────────────────────────────────────────────────────

def _first_blocks(data):
    """역할마다 **글이 있는 첫 단락** 하나. 실전 유닛은 통째로 하나 더."""
    seen = {}
    s3_unit = None
    for st in data.get("steps") or []:
        for g in st.get("groups") or []:
            for key in ("units", "attach"):
                for u in g.get(key) or []:
                    if s3_unit is None and st["layout"] == "s3" and len(u) >= 3:
                        s3_unit = (u, st)
                    for b in u:
                        role = b.get("role")
                        if role in seen:
                            continue
                        if R._btext(b).strip() or b.get("icon"):
                            seen[role] = (b, st)
    return seen, s3_unit


def parts(cfg, data, log=print):
    _reset()
    R.index_refs(data)
    seen, s3_unit = _first_blocks(data)
    order = PART_ORDER + [r for r in seen if r not in PART_ORDER]
    by_step = {1: [], 2: [], 3: []}
    for role in order:
        if role not in seen:
            continue
        b, st = seen[role]
        n = st["step"]
        if st["layout"] == "s3":
            html_s, _ = R.s3_blocks([b], 1)
        else:
            html_s = R.blocks_html([b], n, st["key"])
        if not html_s.strip():
            html_s = '<p style="color:#bbb">(이 역할은 홀로 그리지 않는다 — 다른 부품에 딸림)</p>'
        by_step[n].append(
            f'<div class="mk-part s{n} k-{st["key"]}"><div class="mk-lab">'
            f'<b>{R.esc(PART_NAMES.get(role, role))}</b> · {role} · {st["key"]}</div>'
            f'{html_s}</div>')
    if s3_unit:
        u, st = s3_unit
        html_s, _ = R.s3_blocks(u, 1)
        by_step[3].append(
            f'<div class="mk-part s3 k-{st["key"]}"><div class="mk-lab">'
            f'<b>실전 유닛 통째</b> · 세트 안내문 + 지문 + 문항 · {st["key"]}</div>'
            f'<div class="flowbody">{html_s}</div></div>')
    secs = []
    for n in (1, 2, 3):
        if not by_step[n]:
            continue
        secs.append(f'<section class="sec flow onecol s{n}">'
                    f'<div class="mk-head">STEP 0{n} 부품 {len(by_step[n])}개</div>'
                    + "".join(by_step[n]) + '</section>')
    log(f"  부품 {sum(len(v) for v in by_step.values())}개 (역할 {len(seen)}종)")
    return _doc("부품", "".join(secs))


# ── 틀 ────────────────────────────────────────────────────────────

def _empty_step(key, n_groups):
    st = dict(data_mod.STEP_META[key], key=key)
    st["groups"] = [{"label": f"{i + 1:02d}", "units": [[]]} for i in range(n_groups)]
    return st


def frames(cfg, data, log=print):
    _reset()
    R.index_refs({"steps": []})
    book = data.get("book") or {}
    parts_ = ['<section class="sec blank"><div class="pg"></div></section>']
    idx = 0
    for n in (1, 2, 3):
        parts_.append(R.divider_section(n, book.get("line1", ""), book.get("line2", "")))
    for lay, key in FRAME_KEYS.items():
        idx += 1
        st = _empty_step(key, 2 if lay == "a1" else 1)
        if lay in ("flow", "s3"):
            parts_.append(R.flow_sec(st, idx))
        else:
            parts_.append(R.fixed_section(st, idx)[0])
    log(f"  간지 3벌 + 틀 {len(FRAME_KEYS)}종")
    return _doc("틀", "\n".join(parts_))


# ── 스텝 ────────────────────────────────────────────────────────────

def step(cfg, data, key, n=2, log=print):
    _reset()
    sts = [s for s in (data.get("steps") or []) if s["key"] == key]
    if not sts:
        raise SystemExit(f"모르는 스텝: {key} — 있는 것: "
                         + ", ".join(s["key"] for s in data.get("steps") or []))
    st = dict(sts[0], groups=sts[0]["groups"][:max(1, int(n))])
    text, rows = R.document(dict(data, steps=[st], order=None),
                            (cfg.book or {}).get("title") or "워크북")
    for k, v in rows:
        log(f"    {k:<14} {v}면" if isinstance(v, int) else f"    {k:<14} {v}")
    return text


# ── 진입 ────────────────────────────────────────────────────────────

def make(cfg, what, log=print, key=None, n=2, **_):
    """`what` 한 칸을 `build/make_<what>[_<key>].html` 로. 경로를 돌려준다."""
    data = data_mod.load(cfg)
    build_dir = cfg.build_dir
    if what == "parts":
        return _write(build_dir, "make_parts.html", parts(cfg, data, log))
    if what == "frames":
        return _write(build_dir, "make_frames.html", frames(cfg, data, log))
    if what == "step":
        if not key:
            raise SystemExit("--key=<스텝 키> 가 필요하다 (예: step1_a1)")
        return _write(build_dir, f"make_step_{key}.html", step(cfg, data, key, n, log))
    raise SystemExit(f"모르는 칸: {what} — parts · frames · step")
