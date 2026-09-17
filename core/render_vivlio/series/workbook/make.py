"""만들기 — 워크북 사다리를 **한 칸씩** 지면으로 본다.

    부품(parts)  역할마다 원고 단락 하나 → 그 역할이 그리는 지면 조각 (해부도)
    틀(frames)   원고 없이 빈 칸 + 껍데기(머리말·탭·쪽번호) + 간지 (해부도)
    스텝(step)   틀 + 부품 + 지문 n개 → 구간 하나
    조립(compose) 부품(스텝 단위) 목록 + 순서 + 지문 수 + 가로/세로 → 견본 HTML.
                 config 를 건드리지 않는다 — data.json 을 메모리에서 골라 그린다
    썸네일(thumbs) 부품마다 대표 면 한 장 PNG → catalog/<계열>/parts/ (라이브러리 카드)
    책(book)     `book.py render --sample` / `build` — 여기서 다시 만들지 않는다

조립의 "부품"은 지금 **스텝 단위**다(원고 파일도 스텝 단위라 이 크기가 원고와 맞는다).
면 안에서 둘을 섞는 더 잘은 부품은 계열 렌더러에서 부품을 빼낸 뒤에 온다.

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


# ── 조립 부품 = 스텝 단위 ─────────────────────────────────────────

# 부품 설명 — 카드에 적히는 한 줄. 스텝 키가 곧 부품 id 다.
PART_DESC = {
    "step1_a1": "지문 속 낱말 둘 중 고르기 · 한 면에 지문 2개",
    "step1_a1_2": "어휘 선택 두 번째 벌 · 한 면에 지문 2개",
    "step1_a2": "본문 문장 O/X 판단 · 한 면에 지문 1개",
    "step1_b1": "주제·제목·정리 줄 + 하단 문제 · 한 면에 지문 1개",
    "step1_b2": "내용 종합 객관식 · 한 면에 지문 1개",
    "step1_c1": "문장 배열 + 주어진 문장 · 한 면에 지문 1개",
    "step1_c2": "빈칸 어휘 + 해석 · 한 면에 지문 1개",
    "step2_a1": "어법 선택 지문 + 하단 문제(주황 상자)",
    "step2_b1": "문장마다 어법 O/X 표시하고 고치기",
    "step2_c1": "빈칸 어법 + 해석",
    "step2_c2": "청크 영작 배열 · 흘림",
    "step3": "실전 문항 세트(안내문+지문+문항) · 2단 흘림",
    "step3_short": "짧은 실전 문항 · 2단 흘림",
}


def parts_list():
    """조립 화면의 부품 카드 목록. 딸린 조각(attach)은 부품이 아니다."""
    out = []
    for key, m in data_mod.STEP_META.items():
        if m.get("attach_to"):
            continue
        out.append({"key": key, "name": m.get("title") or key, "step": m.get("step"),
                    "tag": m.get("tag"), "logo": m.get("logo"), "layout": m.get("layout"),
                    "frame": FRAME_NAMES.get(m.get("layout"), m.get("layout")),
                    "desc": PART_DESC.get(key, "")})
    return out


def compose(cfg, data, steps, limits=None, cycle=False, n=2, log=print):
    """부품 목록(순서대로) → 견본 HTML. `data.json` 을 메모리에서 골라 그린다.

    steps  : 스텝 키 목록 — 이 순서가 책의 순서
    limits : {키: 지문 수}
    cycle  : True 면 세로(지문마다 스텝을 돎)
    n      : 견본에 남길 지문 수(0 이면 전부)
    """
    steps = [k for k in (steps or []) if k in data_mod.STEP_META]
    if not steps:
        raise SystemExit("부품이 하나도 없다 — --steps=step1_a1,step3 처럼")
    sel = {"steps": steps, "order": steps,
           "limits": {k: {"passages": int(v)} for k, v in (limits or {}).items()
                      if k in steps and int(v) > 0}}
    picked = data_mod.apply_select([dict(s) for s in data["steps"]], sel, log)
    missing = [k for k in steps if k not in {s["key"] for s in picked}]
    if missing:
        log("  [조립] 이 원고에 없는 부품(건너뜀): " + ", ".join(missing))
    order = None
    if cycle:
        picked = data_mod.to_cycles(picked, log)
        order = "cycle"
    if n and int(n) > 0:
        picked = [dict(s, groups=s["groups"][:int(n)]) for s in picked]
    _reset()
    text, rows = R.document(dict(data, steps=picked, order=order),
                            (cfg.book or {}).get("title") or "워크북")
    for k, v in rows:
        log(f"    {k:<14} {v}면" if isinstance(v, int) else f"    {k:<14} {v}")
    return text


def thumbs(cfg, data, out_dir, log=print, dpi=40):
    """부품마다 대표 면 한 장 PNG. 간지 3장도 함께. → parts.json 목록."""
    import json as _json
    import warnings
    from core.render_vivlio import cli
    warnings.filterwarnings("ignore")
    import fitz
    os.makedirs(out_dir, exist_ok=True)
    build_dir = cfg.build_dir
    made = []
    for part in parts_list():
        key = part["key"]
        if not any(s["key"] == key for s in data.get("steps") or []):
            log(f"  [썸네일] 원고에 없는 부품 {key} — 건너뜀")
            continue
        html = _write(build_dir, f"make_thumb_{key}.html", step(cfg, data, key, 1, lambda *a: None))
        pdf = os.path.join(build_dir, f"make_thumb_{key}.pdf")
        cli.run_build(html, pdf, log=lambda *a: None, extra=["-f", "pdf"])
        doc = fitz.open(pdf)
        # 첫 면 빈 간지 자리 · 간지 2면 다음이 부품의 첫 면 (문서 = blank + divider(2) + 면들)
        idx = min(3, doc.page_count - 1)
        doc[idx].get_pixmap(dpi=dpi).save(os.path.join(out_dir, f"{key}.png"))
        if key in ("step1_a1", "step2_a1", "step3"):        # 스텝 간지 앞면은 스텝마다 한 장
            doc[1].get_pixmap(dpi=dpi).save(os.path.join(out_dir, f"divider_{part['step']}.png"))
        doc.close()
        os.remove(pdf)
        os.remove(html)
        made.append(dict(part, thumb=f"{key}.png"))
        log(f"  [썸네일] {key} ← {idx + 1}면")
    with open(os.path.join(out_dir, "parts.json"), "w", encoding="utf-8") as f:
        _json.dump({"series": "workbook", "from": cfg.root, "parts": made}, f,
                   ensure_ascii=False, indent=1)
    log(f"  부품 {len(made)}개 → {out_dir}")
    return os.path.join(out_dir, "parts.json")


# ── 진입 ────────────────────────────────────────────────────────────

def make(cfg, what, log=print, key=None, n=2, steps=None, limits=None, cycle=False,
         out=None, **_):
    """`what` 한 칸을 `build/make_<what>[_<key>].html` 로. 경로를 돌려준다."""
    data = data_mod.load(cfg)
    build_dir = cfg.build_dir
    if what == "compose":
        keys = [k.strip() for k in str(steps or "").split(",") if k.strip()]
        lim = {}
        for part in str(limits or "").split(","):
            if "=" in part:
                k, _, v = part.partition("=")
                if v.strip().isdigit():
                    lim[k.strip()] = int(v)
        return _write(build_dir, "make_compose.html",
                      compose(cfg, data, keys, lim, bool(cycle), n, log))
    if what == "thumbs":
        return thumbs(cfg, data, out or os.path.join(build_dir, "parts"), log)
    if what == "parts":
        return _write(build_dir, "make_parts.html", parts(cfg, data, log))
    if what == "frames":
        return _write(build_dir, "make_frames.html", frames(cfg, data, log))
    if what == "step":
        if not key:
            raise SystemExit("--key=<스텝 키> 가 필요하다 (예: step1_a1)")
        return _write(build_dir, f"make_step_{key}.html", step(cfg, data, key, n, log))
    raise SystemExit(f"모르는 칸: {what} — parts · frames · step")
