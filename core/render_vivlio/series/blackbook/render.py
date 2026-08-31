"""블랙북 계열 렌더러 — data.json → build/index.html (Vivliostyle 입력).

조판 순서(사용자 지시): 1과 연관어휘 → 1과 문제 → 2과 연관어휘 → 2과 문제 →
1과 해설 → 2과 해설.

책마다 다른 것(머리말 표기·과 구성·판면 수치)은 config 에서 온다. 머리말은
**원고 표기 그대로**(`book.subject`) 쓴다.

세 가지 HTML 을 만든다 — 본 조판과, 자연 높이를 재기 위한 측정용 둘:
    mode=None          index.html       본 조판(문항 높이·해설 높이 반영)
    mode="measure"     measure.html     문항만 한 면 1문항 (natural height 측정)
    mode="measure-ans" measure_ans.html 해설 항목을 한 단 폭·한 면 1항목

핵심 규칙:
  · **한 면 2문항 가변 배치** — 실측 높이로 짝을 지어 위 문항의 슬롯을 줄인다.
    합이 판면을 넘으면 한 면 1문항. 두 문항 사이 최소 간격 QGAP.
  · **해설은 펼침면(왼+오 = 4단) 단위로 흐른다** — 한 항목이 왼쪽→오른쪽으로
    이어지는 것은 허용하고 펼침면을 넘어가는 것은 금지. 높이를 재서 미리 끊는다.
    (반복 조판으로 수렴시키려 하면 발산한다: 10→8→7)
  · **빈칸**은 3칸 이상 공백을 밑줄 빈칸으로. 공백–라벨–공백은 한 줄로 이어 붙여
    `__(A)__` 처럼 밑줄이 끊기지 않게 한다.
  · **대화문**은 덩어리 단위로 판정 — 화자 줄이 둘 이상일 때만 바탕을 준다
    (제목 `De Ceuvel: …` 오인 방지 + 줄마다 스타일이 달라지는 사고 방지).
"""
import html, json, os, re

from core.render_vivlio import stage

# 판면 기본값(mm) — 인디자인 완성본 실측. 책이 필요하면 config.metrics 로 덮는다.
DEFAULT_METRICS = {
    "content_h": 245.0,   # 판면 높이
    "slot": 122.5,        # 기본 반 면
    "qgap": 4.0,          # 두 문항 사이 최소 간격
    "col_w": 82.27,       # 해설 한 단 폭
    "col_h": 240.0,       # 해설 한 단에 담기는 높이(고아·과부 여유 포함)
    "agap": 2.5,          # 해설 항목 아래 여백
    "body_top": 31.5,     # 본문 시작 y (높이 측정의 원점)
    "body_bottom": 279.0,
}


def metrics_of(cfg):
    m = dict(DEFAULT_METRICS)
    m.update(cfg.section("metrics") or {})
    return m


# 화자: 이름은 두세 낱말까지 (American Sam:, Singaporean Sam:, 이름:)
RE_DLG = re.compile(r'^(?:[A-Z][A-Za-z.\'-]*(?: [A-Z][A-Za-z.\'-]*){0,2}'
                    r'|[가-힣]{1,6})\s*:\s')
RE_GAP = re.compile(r' {3,}')
RE_BLKJOIN = re.compile(r'</span>((?:&nbsp;| )*\(?[A-Za-z0-9]{1,3}\)?'
                        r'(?:&nbsp;| )*)<span class="blk">')


# ------------------------------------------------------------------ 인라인

def esc_gap(s):
    """연속 공백(의미 있는 간격)을 보존."""
    return re.sub(r' {2,}', lambda m: '&nbsp;' * (len(m.group(0)) - 1) + ' ', s)


def esc_blank(s):
    """지문 속 '   (A)   ' 같은 공백 빈칸을 밑줄 빈칸으로.

    공백-라벨-공백은 **한 줄로 이어진** 밑줄이어야 한다 → 사이의 (A) 를 흡수한다.
    """
    def rep(m):
        n = len(m.group(0))
        return f'<span class="blk">{"&nbsp;" * n}</span>'
    out = RE_GAP.sub(rep, s)
    prev = None
    while prev != out:                       # (A) 를 사이에 둔 두 빈칸을 잇는다
        prev = out
        out = RE_BLKJOIN.sub(lambda m: m.group(1), out)
    return out


def inl(x, blank=False):
    """rich 세그먼트 → HTML"""
    if x is None:
        return ''
    if isinstance(x, str):
        t = html.escape(x)
        return esc_blank(t) if blank else esc_gap(t)
    if isinstance(x, dict):
        t = html.escape(x.get('t', ''))
        t = esc_blank(t) if blank else esc_gap(t)
        if x.get('u'):
            t = f'<u>{t}</u>'
        if x.get('b'):
            t = f'<b>{t}</b>'
        if x.get('i'):
            t = f'<i>{t}</i>'
        return t
    return ''.join(inl(i, blank) for i in x)


def plain(x):
    if isinstance(x, str):
        return x
    if isinstance(x, dict):
        return x.get('t', '')
    if x is None:
        return ''
    return ''.join(plain(i) for i in x)


# ── 클릭 편집용 자리표 — 공용 구현을 쓴다(core/render_vivlio/refs.py)
from core.render_vivlio import refs as _refs

REF_SPEC = ("lessons", ("vocab", "problems", "answers"))


def index_refs(data):
    return _refs.index(data, REF_SPEC)


def ref_of(obj, sub=''):
    return _refs.of(obj, sub)


def _mark(ref, base=''):
    return _refs.mark(ref, base)


def ref_table():
    return _refs.table()


def paras_html(paras, blank=False, cls='', ref=''):
    """단락 목록 → HTML. 연속된 대화문 줄은 배경 블록으로 묶는다."""
    out, dlg = [], []
    # 화자 줄이 둘 이상인 덩어리만 대화문으로 본다(제목 'De Ceuvel: …' 오인 방지).
    # 판정은 **덩어리 전체 기준** — 사이에 다른 줄이 끼어도 같은 대화로 취급한다.
    speakers = sum(1 for p in paras if RE_DLG.match(plain(p).strip()))
    is_dlg = speakers >= 2

    def flush():
        if dlg:
            out.append('<div class="dlg">' + ''.join(dlg) + '</div>')
        dlg.clear()

    for i, p in enumerate(paras):
        body = inl(p, blank)
        r = f'{ref}.{i}' if ref else ''
        if is_dlg and RE_DLG.match(plain(p).strip()):
            # ⚠ 대화문 줄에는 **원래 클래스가 없다.** 자리표를 붙이면서 `cls` 를
            #   같이 얹었더니 `<보기>` 상자 안 대화문이 `.t` 를 물어 줄바꿈이
            #   달라졌다(26·61면). 자리표만 붙이고 클래스는 원래대로 둔다.
            dlg.append(f'<p{_mark(r)}>{body}</p>')
        else:
            flush()
            out.append(f'<p{_mark(r, cls)}>{body}</p>')
    flush()
    return ''.join(out)


# ------------------------------------------------------------------ 조각

def sec_open(cls, mark):
    return (f'<section class="sec {cls}">'
            f'<div class="secmark">{html.escape(mark)}</div>')


# ── 머리 띠 ─────────────────────────────────────────────────────────
# 머리 띠 글은 **원고가 아니라 책 설정**(`book.subject`)에서 온다. 그래서
# 자리표를 `book.subject` 로 준다 — 작업대가 그걸 보고 config 를 고친다.
# 띠·탭처럼 조판이 만든 조각은 `#…` 로 준다(고를 수만 있고 글은 없다).
def hdr_unit(no, title):
    return (f'<div{_mark("#머리띠", "sechdr voca")}>'
            '<div class="mask"></div>'
            f'<div{_mark("#유닛탭", "tab")}><span class="u">Unit</span>'
            f'<span class="n"> {no}</span></div>'
            f'<div{_mark("book.subject", "ttl")}>{title}</div></div>')


def hdr_exer(title):
    return (f'<div{_mark("#머리띠", "sechdr")}>'
            '<div class="panel"></div>'
            f'<div{_mark("#문제탭", "tab")}><span class="x">Exercise</span></div>'
            f'<div{_mark("book.subject", "ttl")}>{title}</div>'
            f'<div{_mark("#기입칸", "meta")}>Date |      .      .         Time |'
            '                  점 수 |</div></div>')


def hdr_ans(no, title):
    return (f'<div{_mark("#머리띠", "sechdr ans")}>'
            '<div class="panel"></div>'
            f'<div{_mark("#유닛탭", "tab")}><span class="u">Unit</span>'
            f'<span class="n"> {no}</span></div>'
            f'<div{_mark("#해설제목", "ttl")}>정답 및 해설 <b>{title}</b></div></div>')


def render_vocab(unit):
    u = ref_of(unit)
    o = ['<div class="vunit">']
    o.append('<div><span'
             + _mark(u and u + '.label', 'chip')
             + f'>{html.escape(unit["label"])}</span></div>')
    o.append('<div class="rule"></div>')
    o.append('<div class="pbox">')
    if unit['title']:
        o.append(f'<p{_mark(u and u + ".title")}>{inl(unit["title"])}</p>')
    o.append(paras_html(unit['paras'], ref=u and u + '.paras'))
    o.append('</div>')
    o.append('<div class="chipline" style="margin-top:5.4mm">'
             '<span class="chip chip-v">연관 어휘</span></div>')
    o.append('<div class="rule rule-v"></div>')
    o.append('<div class="vwords">')
    for wi, w in enumerate(unit['words']):
        wr = f'{u}.words.{wi}' if u else ''
        o.append('<div class="vw">')
        # 표제어와 뜻은 한 줄에 붙어 있다 — 자리표는 **뜻**에 건다(고칠 것은 뜻이다)
        o.append(f'<p{_mark(wr and wr + ".mean", "wh")}>'
                 f'<b>{html.escape(w["word"])}</b>'
                 f'<span class="gap"></span> {html.escape(w["mean"])}</p>')
        for ri, r in enumerate(w['rel']):
            cls = 'rel ant' if r['kind'] == '반의어' else 'rel'
            o.append(f'<p{_mark(wr and f"{wr}.rel.{ri}.body", cls)}>'
                     f'<span class="lab">{r["kind"]}:</span>'
                     f'<span class="gap"></span> {inl(r["body"])}</p>')
        o.append('</div>')
    o.append('</div></div>')
    return ''.join(o)


def render_question(item, style=''):
    q = ref_of(item)
    o = [f'<div class="q"{style}>']
    o.append(f'<p{_mark(q and q + ".stem", "head")}>'
             f'<span class="no">{item["no"]:02d}</span>'
             f'{inl(item["stem"])}</p>')
    for bi, b in enumerate(item['blocks']):
        t = b['t']
        br = f'{q}.blocks.{bi}' if q else ''
        if t == 'passage':
            o.append('<div class="pbox">'
                     + paras_html(b['paras'], blank=True,
                                  ref=br and br + '.paras')
                     + '</div>')
        elif t == 'arrow':
            o.append('<div class="arrow">↓</div>')
        elif t == 'summary':
            o.append('<div class="summary">'
                     + paras_html(b['paras'], blank=True,
                                  ref=br and br + '.paras') + '</div>')
        elif t == 'bogi':
            o.append('<div class="bogi"><p class="t">&lt; 보 기 &gt;</p>'
                     + paras_html(b['items'], blank=True, cls='t',
                                  ref=br and br + '.items')
                     + '</div>')
        elif t == 'choice':
            o.append(f'<p{_mark(br and br + ".body", "ch")}>'
                     f'<span class="m">{b["mark"]}</span> '
                     f'{inl(b["body"], blank=True)}</p>')
        elif t == 'ansline':
            o.append('<div class="ansline">')
            for ln in b['lines']:
                o.append(f'<p>{inl(ln)}</p>')
            o.append('</div>')
        elif t == 'crit':
            o.append('<div class="crit">')
            o.append(f'<p>{html.escape(b["title"])}</p>')
            for it in b['items']:
                o.append(f'<p>{inl(it)}</p>')
            o.append('</div>')
    o.append('</div>')
    return ''.join(o)


def render_answer(a, brk=False):
    ar = ref_of(a)
    o = [f'<div class="a{" brk" if brk else ""}">']
    o.append(f'<p{_mark(ar and ar + ".answer")}><span class="no">{a["no"]}.</span>'
             f'<span class="ans"> {inl(a["answer"])}</span></p>')
    for k, e in enumerate(a['trans']):
        lab = '<span class="lab tr">해석 |</span> ' if k == 0 else ''
        cls = 'expl tr lead' if k == 0 else 'expl tr'
        o.append(f'<p{_mark(ar and f"{ar}.trans.{k}", cls)}>{lab}{inl(e)}</p>')
    for k, e in enumerate(a['expl']):
        lab = '<span class="lab">해설 |</span> ' if k == 0 else ''
        cls = 'expl lead' if k == 0 else 'expl'
        o.append(f'<p{_mark(ar and f"{ar}.expl.{k}", cls)}>{lab}{inl(e)}</p>')
    o.append(f'<span class="mk">§A{a["no"]}§</span></div>')
    return ''.join(o)


# ------------------------------------------------- 문항 배치(가변 2문항/면)

def layout_pages(items, heights, m):
    """[(item, min-height mm 또는 None, 면 끝인가)] — 두 문항이 한 면에 들어가면 넣는다.

    둘 다 짧으면 반반(SLOT), 아래가 길면 위를 그만큼 줄여 한 면에 넣는다.
    합이 판면(CONTENT_H)을 넘으면 한 면 1문항.
    """
    SLOT, QGAP, CONTENT_H = m["slot"], m["qgap"], m["content_h"]
    groups, cur = [], []
    for it in items:
        h = heights.get(str(it['no']), heights.get(it['no'], SLOT))
        if cur and (len(cur) >= 2 or sum(x[1] for x in cur) + QGAP + h > CONTENT_H):
            groups.append(cur)
            cur = []
        cur.append((it, h))
    if cur:
        groups.append(cur)

    out = []
    for g in groups:
        if len(g) == 2:
            (it0, h0), (it1, h1) = g
            slot = min(SLOT, CONTENT_H - h1 - QGAP)
            slot = max(slot, h0 + QGAP)
            out.append((it0, slot, False))
            out.append((it1, None, True))
        else:
            out.append((g[0][0], None, True))
    if out:
        out[-1] = (out[-1][0], out[-1][1], False)
    return out


def layout_answers(answers, heights, m):
    """해설 항목을 **펼침면(왼+오 = 4단)** 단위로 묶는다.

    한 항목이 단 경계를 넘어 이어지는 것은 좋지만, 펼침면을 넘어가면 읽는 흐름이
    끊긴다(사용자 규칙). 그래서 펼침면 용량(4단)에 맞춰 미리 나눈다.
    """
    cap = m["col_h"] * 4
    res, used = [], 0.0
    for k, a in enumerate(answers):
        h = heights.get(str(a['no']), 60.0) + m["agap"]
        brk = False
        if k and used + h > cap:
            brk, used = True, 0.0
        used += h
        res.append((a, brk))
    return res


# ------------------------------------------------------------------ 문서

MODE_FILE = {None: "index.html", "measure": "measure.html",
             "measure-ans": "measure_ans.html"}


def document(cfg, data, heights=None, aheights=None, mode=None):
    m = metrics_of(cfg)
    subject = cfg.book.get("subject", "")
    heights = {} if mode == "measure" else (heights or {})
    aheights = aheights or {}

    o = ['<!doctype html><html lang="ko"><head><meta charset="utf-8">',
         f'<title>{html.escape(cfg.book.get("title", ""))}</title>',
         '<link rel="stylesheet" href="theme.css">',
         # 손잡이 + 탈출구. config 에 값이 없으면 **빈 파일**이라 아무것도 안 바뀐다.
         stage.BOOK_CSS_LINKS]
    if mode == "measure":
        o.append('<style>.q{min-height:0!important;break-before:page}</style>')
    if mode == "measure-ans":
        o.append(f'<style>.answers{{column-count:1;width:{m["col_w"]}mm}}'
                 '.a{break-before:page}</style>')
    o.append('</head><body>')

    if mode == "measure-ans":
        o.append(sec_open('sec-ans', '측정'))
        o.append(hdr_ans('01', subject))
        o.append('<div class="answers">')
        for L in data['lessons']:
            for a in L['answers']:
                o.append(render_answer(a))
        o.append('</div></section></body></html>')
    elif mode == "measure":
        o.append(sec_open('sec-exer', '측정'))
        o.append(hdr_exer(subject))
        for L in data['lessons']:
            for it in L['problems']:
                o.append(render_question(it))
        o.append('</section></body></html>')
    else:
        o.append('<div class="divider"><span style="color:#fff">§DIV1§</span></div>')
        for L in data['lessons']:
            n = L['lesson']
            mark = f'{subject} {n}과'   # 꼬리말 라벨 — 머리 제목 전체와 같은 말로
            unit = f'{n:02d}'
            o.append(sec_open('sec-voca', mark))
            o.append(hdr_unit(unit, f'{subject}&nbsp; {n}과 연관어휘'))
            for u in L['vocab']:
                o.append(render_vocab(u))
            o.append('</section>')

            o.append(sec_open('sec-exer', mark))
            o.append(hdr_exer(f'{subject}&nbsp; {n}과'))
            for it, slot, brk in layout_pages(L['problems'], heights, m):
                st = []
                if slot:
                    st.append(f'min-height:{slot:.1f}mm')
                if brk:
                    st.append('break-after:page')
                style = f' style="{";".join(st)}"' if st else ''
                o.append(render_question(it, style))
            o.append('</section>')

        o.append('<div class="divider left">'
                 '<span style="color:#fff">§DIV2§</span></div>')
        for L in data['lessons']:
            n = L['lesson']
            o.append(sec_open('sec-ans', '정답 및 해설'))
            o.append(hdr_ans(f'{n:02d}', f'{subject} {n}과'))
            o.append('<div class="answers">')
            for a, brk in layout_answers(L['answers'], aheights, m):
                o.append(render_answer(a, brk))
            o.append('</div></section>')
        o.append('</body></html>')
    return '\n'.join(o)


def write(cfg, data, build_dir, heights=None, aheights=None, mode=None,
          log=None):
    index_refs(data)          # 클릭 편집용 자리표 — 렌더 직전에 한 번
    text = document(cfg, data, heights, aheights, mode)
    os.makedirs(build_dir, exist_ok=True)
    out = os.path.join(build_dir, MODE_FILE[mode])
    with open(out, 'w', encoding='utf-8') as f:
        f.write(text)
    _refs.dump(build_dir)   # 번호 ↔ 경로 표
    if log:
        log(f'[렌더] {os.path.basename(out)} {len(text):,} bytes'
            + ('  [측정용]' if mode else
               f'  [문항 높이 {len(heights or {})} · '
               f'해설 높이 {len(aheights or {})} 반영]'))
    return out


def load_heights(path):
    if path and os.path.exists(path):
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    return {}
