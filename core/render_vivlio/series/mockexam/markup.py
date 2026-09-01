# -*- coding: utf-8 -*-
"""IR → 시맨틱 HTML (프로파일 구동).

기존 경로는 IR 을 `ir_to_render_plan` 으로 **평탄한 단락 목록**(InDesign 스타일명)
으로 눌러 놓고 그걸 HTML 로 옮겼다. 그 과정에서 학교 규칙에 필요한 것이 다 사라진다 —
보기인지 조건인지, 묶음의 몇 번째 문항인지, 서답형인지, 배점이 얼마인지.

여기는 **IR 을 직접** 읽어 학교 프로파일대로 표기를 만들어 넣는다. 원고가 안 주는
것(문항 번호·묶음 머리·서답형 라벨·배점)은 전부 이 단계에서 생성된다.
"""
import html
import re

from core.render_vivlio.series.mockexam import profile as P

# HWP 사설영역 글리프 → 유니코드. 학교마다 쓰는 화살표가 다르므로
# **프로파일이 정한 글리프로** 바꾼다(고정 치환표가 아니다).
PUA_ARROW = "\U000f003b"

_RE_BLANK_RUN = re.compile(r"_{6,}")
_RE_GREP_BOLD = re.compile(r"(\(\s*[A-Ea-e]\s*\)|\[[AB]\])")
_RE_SOURCE_TAG = re.compile(
    r"\s*\[\s*(?:\d{2}년\s*\d{1,2}월[^\]]*|\d{4}\.[^\]]*번[^\]]*|"
    r"\d+\s*과[^\]]*|\d+강[^\]]*|[^\]]*수능특강[^\]]*)\]\s*")


def esc(t):
    return html.escape(t or "", quote=False)


# 출처로 **확신할 때만** 지운다. 발문 끝 괄호에는 출처와 작성 조건이 섞여
# 오는데(`[리딩파워 유형편 14-2]` vs `[단, 어형 변형 없음]`), 조건을 잘못
# 지우면 문제가 성립하지 않는다. 그래서 조건을 알아보려 하지 않고,
# 출처임이 분명한 것만 지운다 — 정본 세종1 실측: 교재 출처는 인쇄되지 않고
# `(단, …)` 조건은 인쇄된다.
_RE_TAIL_TAG = re.compile(r"\s*[\[［]([^\[\]［］]{1,40})[\]］]\s*$")
_RE_HANGUL = re.compile(r"[가-힣]")
_RE_NUMBERISH = re.compile(r"^(?:\d+\s*(?:번|과|강|쪽)|\d{2}년\s*\d{1,2}월"
                           r"|\d{4}\.[\d.]*)[^가-힣]*$")
_SOURCE_WORDS = ("리딩파워", "유형편", "올림포스", "수능특강", "교과서", "EBS",
                 "모의고사", "기출", "능률", "천재", "비상", "동아", "미래엔",
                 "워크북", "부교재")


def _is_source_tag(inner):
    """대괄호 안이 출처인가. 아니면(=조건일 수 있으면) 건드리지 않는다."""
    t = (inner or "").strip()
    if not t:
        return False
    if any(w in t for w in _SOURCE_WORDS):
        return True
    if _RE_NUMBERISH.match(t):
        return True
    if not _RE_HANGUL.search(t):
        # 한글이 한 자도 없는 꼬리 태그 — `[Further Reading]` `[TED]` `[14-E]`.
        # 작성 조건은 전부 한국어 문장이라 여기 걸리지 않는다.
        return True
    return False


def strip_source(text):
    """출처 태그 제거 — 시험지에 인쇄되면 안 된다(현행 결함 중 하나)."""
    t = _RE_SOURCE_TAG.sub(" ", text or "").strip()
    m = _RE_TAIL_TAG.search(t)
    if m and _is_source_tag(m.group(1)):
        t = t[:m.start()].rstrip()
    return t


class Renderer(object):
    def __init__(self, spec, case=None):
        self.s = spec
        self.case = case or {}
        self.q_no = 0
        self.essay_no = 0
        self.warnings = []
        self.images = []          # (파일명, 바이트) — build 가 빌드 폴더에 쓴다

    def stash_image(self, img):
        """원고 그림을 모아 두고 파일명을 돌려준다. 도표 문항은 그림이 빠지면
        문제가 성립하지 않으므로 조판이 반드시 실어야 한다."""
        data = img.get("data")
        if not data:
            return ""
        name = f"fig{len(self.images) + 1}{img.get('ext') or '.png'}"
        self.images.append((name, data))
        return name

    # ── 인라인 ────────────────────────────────────────────────────────────
    def inline(self, text, marks=None, grep_bold=False):
        text = text or ""
        arrow = self.s.summary.get("arrow")
        if arrow:
            text = text.replace(PUA_ARROW, arrow)
        if marks:
            spans = sorted((m["span"][0], m["span"][1]) for m in marks
                           if m.get("type") == "underline" and m.get("span"))
            if spans:
                out, pos = [], 0
                for a, b in spans:
                    a, b = max(a, pos), min(b, len(text))
                    if a > pos:
                        out.append(esc(text[pos:a]))
                    if b > a:
                        out.append(f"<u>{esc(text[a:b])}</u>")
                    pos = max(pos, b)
                out.append(esc(text[pos:]))
                s = "".join(out)
            else:
                s = esc(text)
        else:
            s = esc(text)
        if grep_bold:
            s = _RE_GREP_BOLD.sub(r"<b>\1</b>", s)
        # 답란·빈칸의 연속 밑줄은 한 낱말이라 줄바꿈이 안 돼 **지면 밖으로
        # 나간다**(명일1 7쪽 실측 257.6mm > 지면 257mm). 폭이 제한되는 칸으로
        # 바꿔 판면 안에 가둔다.
        s = _RE_BLANK_RUN.sub(
            lambda m: f'<span class="blank" style="width:'
                      f'{len(m.group(0)) * 0.5:.1f}em"></span>', s)
        return s

    # ── 표기 생성 (원고가 안 주는 것들) ───────────────────────────────────
    def score_str(self, value):
        if value is None:
            return ""
        v = self.s.fmt_score(value)
        return f'<span class="score">{esc(v)}</span>' if v else ""

    def qnum(self, n):
        return esc(self.s.q_template.replace("{n}", str(n)))

    def essay_label(self, n, qtype=None, score=None):
        """서답형 라벨. 학교에 따라 문자열이거나 **표**다(상일 계열).

        Returns:
            (html, took_score) — 라벨이 배점을 이미 인쇄했는지. 상일 계열은
            배점이 라벨 표 오른쪽 `【X점】` 한 곳뿐이라, 여기서 찍었으면
            발문 끝에 또 붙이면 안 된다(정본 실측).
        """
        s = self.s
        if s.essay_is_table:
            cells = []
            for c in (s.essay_cells or []):
                txt = (c.get("text") or "").replace("{n}", str(n))
                if "|" in txt and qtype:
                    txt = qtype
                elif "|" in txt:
                    txt = txt.split("|")[0].strip()
                    self.warnings.append(
                        f"서답형 {n}: 유형칸을 원고에서 못 정해 첫 값으로 뒀다")
                cls = "chip" if (c.get("role") == "chip" or c.get("i") == 1) else "type"
                cells.append(f'<td class="{cls}">{esc(txt)}</td>')
            tail = ""
            if score is not None and s.essay_score_bracket:
                b = s.essay_score_bracket
                body = b.replace("{점수}", str(score)) if "{" in b \
                    else f"{b[0]}{score}점{b[-1]}"
                tail = f'<span class="essay-score">{esc(body)}</span>'
            return (f'<div class="essay-label-row">'
                    f'<table class="essay-chip"><tr>{"".join(cells)}</tr></table>'
                    f'{tail}</div>', bool(tail))
        tpl = s.essay_template or "[서답형 {n}]"
        return (f'<span class="essay-no">{esc(tpl.replace("{n}", str(n)))}</span>',
                False)

    def ab_table(self, items, cols, stem="", heads=None):
        """(A)(B)(C) 짝맞추기 선지. 정본 대부분이 **열 표**다.

        원고는 짝을 탭으로만 준다(`However\tStill\tAlthough`). 표로 앉히지
        않으면 열이 어긋나 실물과 전혀 달라진다. 열 수는 원고 구조에서 얻고
        (발문의 `(A)~(C)` 가 아니라 실제 갈린 칸 수), 머리행 레이블만 발문에서
        읽는다.
        """
        s = self.s
        n = len(cols[0])
        heads = heads or _ab_heads(stem, n)
        sep = _ab_sep(s)
        if s.ab_layout == "inline_dash" or s.choice_layout == "inline":
            glue = f" {esc(sep)} " if sep else " "
            body = "".join(
                f'<p class="choice">'
                f'{self.inline((it.get("label") or "") + " ")}'
                f'{glue.join(self.inline(c) for c in row)}</p>'
                for it, row in zip(items, cols))
            return body
        def join(cells, tag="td", mark=True):
            """구분자는 열 사이에 실제로 인쇄되는 문자다. 다만 **머리행에는
            넣지 않는다** — 배재1·배재2·세종1 정본 전수에서 머리행 `(A) (B)`
            에는 구분자가 없고 선지 행에만 있다. 열은 어긋나면 안 되므로
            머리행에도 빈 칸을 같은 자리에 넣는다."""
            if not sep:
                return "".join(cells)
            body = esc(sep) if mark else ""
            gap = f'<{tag} class="ab-sep">{body}</{tag}>'
            return gap.join(cells)

        rows = []
        if s.ab_header_row and heads:
            cells = [f"<th><u>{esc(h)}</u></th>" for h in heads]
            rows.append(f'<tr><th class="ab-mark"></th>'
                        f'{join(cells, "th", mark=False)}</tr>')
        for it, row in zip(items, cols):
            cells = [f"<td>{self.inline(c)}</td>" for c in row]
            rows.append(f'<tr><td class="ab-mark">'
                        f'{esc(it.get("label") or "")}</td>{join(cells)}</tr>')
        return f'<table class="ab-table">{"".join(rows)}</table>'

    def group_head(self, a, b, intro, essay_ns=None, score=None):
        """묶음 머리. 학교마다 괄호·구분자·혼합 표기가 다르다.

        한영1 정본 실측: `[7~8] 다음 질문에 대한 답으로 … 고르시오. [각 3점씩]`
        — 범위·지시문·배점이 **한 줄**에 들어가고, 구성원은 번호만 갖는다.
        지시문은 원고가 `[9~10] 다음 글의 …` 처럼 범위를 달고 오므로 벗긴다.
        """
        s = self.s
        if not s.group_template:
            # 묶음 표기를 안 쓰는 학교(상일1·광문2·세종1 일부) — 머리를 만들지 않는다
            return ""
        intro = _strip_range_prefix(intro)
        mixed = s.group_mixed
        if mixed and mixed.strip() in ("없음", "None", "-"):
            mixed = None       # 프로파일이 '없음' 이라 적어 둔 학교(한영3)
        if essay_ns and mixed and a is None:
            # 서답형만 있는 묶음 — 혼합 템플릿의 객관식 자리를 채울 수 없다.
            # 없는 번호를 지어내느니 머리를 만들지 않는다.
            return f'<p class="group-intro">{esc(intro)}</p>' if intro else ""
        if essay_ns and mixed:
            # 혼합 템플릿도 학교마다 자리가 다르다 — `{n}/{m}` 을 쓰는 곳도,
            # `{a}~{b}, 서답형 {m}` 처럼 범위를 쓰는 곳도 있다.
            marker = (mixed.replace("{a}", str(a)).replace("{b}", str(b))
                      .replace("{n}", str(a)).replace("{m}", str(essay_ns[0])))
            if "{지시문}" not in mixed and _RE_HANGUL_SENT.search(mixed):
                # 혼합 템플릿이 지시문까지 품고 있는 학교(명일1) — 원고 지시문을
                # 덧붙이면 같은 문장이 두 번 나온다.
                intro = ""
        else:
            marker = s.group_template.replace("{a}", str(a)).replace("{b}", str(b))
        if "{지시문}" in marker:
            # 템플릿이 지시문 자리를 정해 뒀으면 거기에 끼운다. 지시문이 이미
            # 마침표로 끝나면 템플릿의 마침표를 겹쳐 찍지 않는다.
            body_txt = (intro or "").rstrip()
            if body_txt.endswith((".", "?", "!")) and "{지시문}." in marker:
                marker = marker.replace("{지시문}.", body_txt)
            else:
                marker = marker.replace("{지시문}", body_txt)
            text = marker
        else:
            text = f"{marker} {intro}".strip() if s.group_intro_same_line and intro \
                else marker
        text = _fill_group_score(text, score, s)
        text = re.sub(r"\s{2,}", " ", text).strip()
        # `[각 2.8점씩]` 이 줄에서 갈리면 안 된다
        body = _RE_EACH_SCORE.sub(
            lambda m: f'<span class="score">{esc(m.group(0))}</span>',
            esc(text))
        if not s.group_intro_same_line and intro and "{지시문}" not in \
                (s.group_template or ""):
            body += f'</p><p class="group-intro">{esc(intro)}'
        return f'<p class="group">{body}</p>'

    # ── 상자 ──────────────────────────────────────────────────────────────
    def box(self, cls, box_spec, label, lines):
        """보기/조건 — 프로파일의 render 방식대로."""
        if not lines:
            return ""
        render = box_spec.get("render") or "plain_line"
        marker = label or box_spec.get("marker") or ""
        # 상자 안이 낱말 나열이냐 문단이냐에 따라 정렬이 달라진다.
        # 정본 실측 — 강동1·상일2·명일2 는 낱말 나열을 가운데로 놓지만,
        # 강동2 처럼 보기 안에 지문이 통째로 들어가면 양끝정렬이다. 문단을
        # 가운데로 놓으면 줄마다 들쭉날쭉해져 실물과 전혀 달라진다.
        prose = _is_prose_box(lines)
        pcls = f"{cls} {cls}-prose" if prose else cls
        body = "".join(f'<p class="{pcls}">{self.inline(l)}</p>' for l in lines)

        if render == "plain_line":
            head = (f'<p class="{cls}-label {cls}">{esc(marker)}</p>'
                    if marker else "")
            return head + body
        if render == "table":
            rows = "".join(f"<tr><td>{self.inline(l)}</td></tr>" for l in lines)
            lbl = esc(marker).replace("<", "").replace(">", "")
            return (f'<table class="{cls}-table"><tr>'
                    f'<td class="lbl" rowspan="{len(lines)}">{lbl}</td>'
                    f'<td>{self.inline(lines[0])}</td></tr>'
                    + "".join(f"<tr><td>{self.inline(l)}</td></tr>"
                              for l in lines[1:]) + "</table>")
        # 테두리 상자 계열
        lab = f'<span class="{cls}-label">{esc(marker)}</span>' if marker else ""
        if render == "boxed_caption_above":
            return f'{lab}<div class="{cls}-box">{body}</div>'
        return f'<div class="{cls}-box">{lab}{body}</div>'

    # ── 문항 ──────────────────────────────────────────────────────────────
    def item(self, it, group_ctx=None):
        s = self.s
        out = []
        # 묶음의 **공유 지문은 묶음 머리 바로 뒤**, 첫 문항 발문 앞에 온다
        # (정본 배재1 `【 8 – 9 】 다음 글을 읽고 물음에 답하시오.` → 대화 지문
        # → `8. 윗글의 …`). 발문이 '윗글'을 가리키므로 순서가 뒤집히면 안 된다.
        lead = bool(group_ctx and group_ctx.get("shared_passage"))
        # 원고가 지문 첫머리에 문항 번호를 달아 두면 조판 번호와 겹쳐 두 번
        # 나온다(강동2 `10. 10 아래 문장의 …`, 강동3 `2.` + `2. Some …`).
        # **그 문항의 번호와 같을 때만** 뗀다 — 본문 안 숫자는 건드리지 않는다.
        qno = (group_ctx or {}).get("qno")
        is_essay = it.get("kind") == "서술형"
        score = (it.get("header") or {}).get("score")
        # 짝맞추기 선지 여부를 **지문보다 먼저** 안다 — 원고가 선지 바로 앞에
        # 머리줄 `(A) (B) (C)` 를 지문처럼 주기 때문에, 표를 만들 문항이면
        # 그 줄을 지문에서 빼야 머리행이 두 번 찍히지 않는다.
        ab_cols = (_ab_columns((it.get("choices") or {}).get("items") or [])
                   if _ab_labeled(it) else None)
        ab_head = None

        # 발문 — 번호(또는 서답형 라벨) + 본문 + 배점
        stem_at = len(out)
        q = strip_source(it.get("question") or "")
        if is_essay:
            self.essay_no += 1
            label, took = self.essay_label(self.essay_no, it.get("label"), score)
            tail = "" if took else self.score_str(score)
            qm = it.get("question_marks")
            if s.essay_is_table or s.essay_pos == "own_line":
                out.append(label)
                out.append(f'<p class="stem srv">{self.inline(q, qm)}{tail}</p>')
            else:
                out.append(f'<p class="stem srv">{label} '
                           f'{self.inline(q, qm)}{tail}</p>')
        else:
            self.q_no += 1
            num = f'<span class="qnum">{self.qnum(self.q_no)}</span> '
            if group_ctx and group_ctx.get("member_no_stem"):
                out.append(f'<p class="stem">{num}{self.score_str(score)}</p>')
            else:
                out.append(f'<p class="stem">{num}'
                           f'{self.inline(q, it.get("question_marks"))}'
                           f'{self.score_str(score)}</p>')

        stem_end = len(out)
        # 지문 — 순서·삽입 문항의 '주어진 글/문장' 은 정본에서 본문 **앞**에
        # 상자로 놓인다. 원고는 삽입 문장을 뒤에 주므로 여기서 앞으로 옮긴다.
        blocks = list((it.get("stimulus") or {}).get("blocks", []))
        _ch = (it.get("choices") or {}).get("items") or []
        given_first, blocks = _split_given_first(
            blocks, _is_order_choices(_ch), _is_slot_choices(_ch))
        if given_first:
            body = "".join(
                f'<p class="passage">'
                f'{self.inline(strip_source(b.get("content") or ""), b.get("marks"), grep_bold=True)}</p>'
                for b in given_first)
            gs = s.given_sentence or {}
            cls = "givensent-box" if (gs.get("render") or "").startswith("box") \
                else "givensent"
            out.append(f'<div class="{cls}">{body}</div>')

        in_summary = False
        for blk in blocks:
            if blk.get("kind") == "image":
                src = self.stash_image(blk.get("image") or {})
                if src:
                    out.append(f'<figure class="fig">'
                               f'<img src="{esc(src)}" alt=""></figure>')
                continue
            content = strip_source(blk.get("content") or "")
            if not content:
                continue
            if qno:
                content = _strip_leading_no(content, qno)
                if not content:
                    continue
            if ab_cols and ab_head is None:
                h = _ab_head_line(content, len(ab_cols[0]))
                if h:
                    ab_head = h        # 표 머리행으로 옮긴다 — 지문 아님
                    continue
            label = blk.get("label")
            if label == "Sym":
                arrow = s.summary.get("arrow") or content
                out.append(f'<p class="summary-arrow">{esc(arrow)}</p>')
                in_summary = True      # 화살표 아래가 요약문이다
                continue
            if blk.get("kind") == "image":
                continue        # 그림은 아래 별도 분기에서 처리한다
            cls = "passage"
            if blk.get("kind") == "para":
                cls = "passage passage-context"
            if label == "Ans":
                cls = "answer"
            body = (f'<p class="{cls}">'
                    f'{self.inline(content, blk.get("marks"), grep_bold=True)}</p>')
            if label == "Sum" or in_summary:
                in_summary = False
                wrap = ("summary-box"
                        if (_summary_render(s, is_essay) or "").startswith("box")
                        else "summary")
                out.append(f'<div class="{wrap}">{body}</div>')
                continue
            out.append(body)

        if lead and len(out) > stem_end:
            # 묶음 첫 문항 — 공유 지문을 발문 위로 올린다
            out = (out[:stem_at] + out[stem_end:] + out[stem_at:stem_end])

        # 보기
        given = it.get("given")
        if given and given.get("content"):
            lines = [l for l in given["content"].split("\n") if l.strip()]
            # 원고가 짝맞추기 선지의 머리줄 `(A) (B) (C)` 를 보기 상자로 준다.
            # 그건 보기가 아니라 표의 머리행이다 — 상자로 그리면 실물과 다르고
            # 머리행이 두 번 찍힌다.
            h = (_ab_head_line(lines[0], len(ab_cols[0]))
                 if ab_cols and len(lines) == 1 else None)
            if h:
                ab_head = h
            else:
                out.append(self.box("given", s.given, s.given.get("marker"),
                                    lines))

        # 조건
        if it.get("constraints"):
            out.append(self.box("cond", s.cond, s.cond.get("marker"),
                                list(it["constraints"])))

        # 선지
        ch = it.get("choices")
        if ch and ch.get("items"):
            items = ch["items"]
            if ab_cols:
                out.append(self.ab_table(items, ab_cols, q, ab_head))
                return "\n".join(x for x in out if x)
            layout = s.choice_layout or "one_per_line"
            if _is_order_choices(items):
                layout = _order_layout(items, s)
            elif _is_tiny_choices(items):
                # 어법 `① ⓐ ② ⓑ ③ ⓒ ④ ⓓ ⑤ ⓔ` 처럼 아주 짧은 선지는
                # 정본에서 한 줄에 늘어선다(명일2 26-1-기말 18번 실측).
                layout = "inline_row"
            cells = []
            for c in items:
                lab = c.get("label") or ""
                head = (lab + " ") if lab else ""
                cells.append(f'<p class="choice">{esc(head)}'
                             f'{self.inline(c["content"], c.get("marks"))}</p>')
            if layout in ("grid2", "grid3", "grid5"):
                n = int(layout[-1])
                out.append(f'<div class="choice-grid g{n}">'
                           + "".join(cells) + "</div>")
            elif layout in ("inline_row", "inline"):
                out.append('<div class="choice-row">' + "".join(cells) + "</div>")
            else:
                out.append("".join(cells))
        return "\n".join(x for x in out if x)


_RE_AB_HEAD = re.compile(r"\(([A-Ea-e])\)")


def _ab_columns(items, min_cols=2):
    """선지가 (A)(B)(C) 짝인지 **구조로** 판정한다.

    유형 이름이나 발문 문구가 아니라, 선지가 모두 같은 칸 수로 갈리는지를 본다.
    원고는 탭으로 주고, 탭이 없으면 세 칸 이상 공백으로 준다.
    Returns: 열 리스트(선지마다) 또는 None.
    """
    if len(items) < 2:
        return None
    rows = []
    for c in items:
        t = (c.get("content") or "").strip() if isinstance(c, dict) else str(c)
        parts = _ab_split(t, min_cols)
        if not parts:
            return None
        rows.append(parts)
    n = len(rows[0])
    if any(len(r) != n for r in rows):
        return None
    # 한 칸이 문장만큼 길면 짝이 아니라 그냥 긴 선지가 갈린 것이다
    if max(len(x) for r in rows for x in r) > 40:
        return None
    # 순서 배열 선지 `(A)-(C)-(B)` 는 짝맞추기가 아니다 — 칸이 레이블뿐이다
    if all(re.fullmatch(r"\(?[A-Ea-e]\)?", x) for r in rows for x in r):
        return None
    return rows


# 원고가 짝을 주는 방식은 학교마다 다르다 — 탭, 여러 칸 공백, 또는 구분자.
_AB_SEPS = (r"\t", r"\s{3,}", r"\s+[-–—]\s+", r"\s*[…⋯]+\s*",
            r"\s*\.{3,}\s*", r"\s+~\s+")


def _ab_split(text, min_cols):
    """선지 한 줄을 짝의 칸들로 가른다. 가장 많이 갈리는 방식을 고른다."""
    best = None
    for pat in _AB_SEPS:
        parts = [x.strip() for x in re.split(pat, text) if x.strip()]
        if len(parts) >= min_cols and (best is None or len(parts) > len(best)):
            best = parts
    return best


# 구분자 방언이 넓다 — 반각/전각 하이픈, en/em 대시, 물결, 괘선 문자까지 쓴다
_RE_ORDER_SEP = re.compile(r"\s*[-–—―─－~∼〜]\s*")


def _is_order_choices(items, min_hit=3):
    """선지가 순서 배열 `(A)-(C)-(B)` 꼴인가 — **구조로** 판정한다.

    유형 이름이 아니라 선지 자체를 본다: 구분자로 가른 칸이 전부 `(A)` 류
    레이블뿐이면 순서 배열이다. 학교마다 이 유형만 선지 배치가 갈린다.
    """
    if len(items) < 3:
        return False
    hit = 0
    for c in items:
        t = (c.get("content") or "").strip() if isinstance(c, dict) else str(c)
        parts = [x.strip() for x in _RE_ORDER_SEP.split(t) if x.strip()]
        if len(parts) >= 2 and all(re.fullmatch(r"\(?[A-Ea-e]\)?", x)
                                   for x in parts):
            hit += 1
    return hit >= max(min_hit, len(items) - 1)


_RE_SLOT = re.compile(r"[(（]\s*[①-⑤]\s*[)）]|[①-⑤]")
# 자리표를 `(A)~(E)` 로 주고 선지를 `① (A) ② (B) …` 로 주는 원고가 있다.
# 같은 삽입 유형인데 표기 방언이 둘이다 — 선지 모양으로 가른다.
_RE_SLOT_AB = re.compile(r"[(（]\s*[A-E]\s*[)）]")
_RE_LABEL_ONLY = re.compile(r"^[(（]?\s*[A-E]\s*[)）]?$")


def _is_slot_choices(items, min_hit=4):
    """선지가 `① (A) ② (B) …` 꼴 — 삽입 문항의 자리표 방언."""
    if len(items) < 4:
        return False
    hit = sum(1 for c in items
              if _RE_LABEL_ONLY.match((c.get("content") or "").strip()))
    return hit >= max(min_hit, len(items) - 1)
# 괄호는 **필수**다 — 없으면 본문 첫 낱말 `A month ago…` 가 조각 (A) 로 잡힌다
_RE_SEG_A = re.compile(r"^[(（]\s*A\s*[)）]")
_RE_FOOTNOTE = re.compile(r"^\s*[*※＊]")


def _split_given_first(blocks, ordered, ab_slots=False):
    """순서·삽입 문항의 '주어진 글/문장' 을 본문에서 가려낸다.

    정본 실측(배재1·배재2 26-1): 둘 다 발문 바로 아래에 주어진 것이 오고
    그 뒤가 본문이다. 원고는 **삽입 문장을 맨 뒤에** 주므로 순서를 바로잡는다.
    유형 이름이 아니라 구조로 가른다 — 순서는 `(A)` 로 시작하는 조각이 있고,
    삽입은 본문에 `( ① )` 자리표가 박혀 있다.

    Returns: (주어진 블록들 또는 None, 나머지 블록들)
    """
    if len(blocks) < 2:
        return None, blocks
    # 출처 태그와 그림은 지문 문장이 아니다 — 자리 계산에서 빼고 그대로 남긴다.
    # (그림을 섞으면 도표가 '주어진 문장' 으로 뽑혀 통째로 사라진다.)
    def _aside(b):
        return b.get("label") == "UNKNOWN" or b.get("kind") == "image"
    head = [b for b in blocks if _aside(b)]
    core = [b for b in blocks if not _aside(b)]
    if len(core) < 2:
        return None, blocks
    texts = [(b.get("content") or "").strip() for b in core]

    # 순서 — `(A)` 로 시작하는 조각 앞이 주어진 글
    if ordered:
        for i, t in enumerate(texts):
            if _RE_SEG_A.match(t):
                return (core[:i] or None), head + core[i:]

    # 삽입 — 자리표가 두 개 이상 박힌 조각이 본문. 자리표 없는 짧은 조각 하나가
    # 주어진 문장이다. 원고는 뒤에 주기도 하고 앞에 주기도 하는데, 정본은
    # **언제나 본문 앞**이다(배재1·배재2 실측).
    pat = _RE_SLOT_AB if ab_slots else _RE_SLOT
    slotted = [i for i, t in enumerate(texts) if len(pat.findall(t)) >= 2]
    if not slotted:
        return None, blocks
    # 각주(`*neurogenesis: …`)는 지문이 아니다 — 후보에서 뺀다
    plain = [i for i, t in enumerate(texts)
             if i not in slotted and len(t) <= 300 and not _RE_FOOTNOTE.match(t)]
    if not plain:
        return None, blocks
    if len(plain) > 1:
        # 본문이 두 조각으로 갈려 자리표 없는 앞부분이 함께 남기도 한다.
        # 주어진 문장은 한 문장이라 눈에 띄게 짧다 — 그럴 때만 고른다.
        plain.sort(key=lambda i: len(texts[i]))
        if len(texts[plain[0]]) * 2 > len(texts[plain[1]]):
            return None, blocks
    j = plain[0]
    return [core[j]], head + [b for i, b in enumerate(core) if i != j]


def _summary_render(s, is_essay):
    """요약문 상자 여부. 명일2 처럼 선택형·서답형이 갈리는 학교가 있다."""
    r = P.dig(s.raw, "summary.render")
    if isinstance(r, dict):
        key = "서답형_요약" if is_essay else "선택형_요약"
        return r.get(key) or next(iter(r.values()), "")
    return r or (s.summary or {}).get("render") or ""


def _is_tiny_choices(items, limit=6):
    """선지가 전부 낱글자 수준으로 짧은가 — 한 줄에 늘어놓을 감."""
    if len(items) < 4:
        return False
    texts = [(c.get("content") or "").strip() for c in items]
    if not any(texts):
        return False        # 내용이 없으면 배치를 바꿀 근거도 없다
    return all(len(t) <= limit for t in texts)


_RE_HANGUL_SENT = re.compile(r"[가-힣]{2,}.*[.?!]\s*$")
_RE_EACH_SCORE = re.compile(r"[\[(（]\s*각\s*[\d.]+\s*점\s*씩?\s*[\])）]")
# `(1~3)` `[9~10]` `[선택형6~10]` — 학교마다 괄호도 접두도 다르다
_RE_RANGE_PREFIX = re.compile(r"^\s*[\[(（【〈]\s*(?:[가-힣]+\s*)?\d+\s*"
                              r"[~\-–—]\s*\d+\s*[\])）】〉]\s*")
_RE_RANGE_IN_INTRO = re.compile(r"[\[(（【〈]\s*(?:[가-힣]+\s*)?(\d+)\s*"
                                r"[~\-–—]\s*(\d+)\s*[\])）】〉]")


def _strip_range_prefix(intro):
    """원고가 지시문 앞에 붙여 준 `[9~10]` 범위 표기를 벗긴다.

    범위는 조판이 템플릿으로 다시 찍으므로, 그대로 두면 `[9~10] … [9~10] …`
    으로 두 번 나온다.
    """
    return _RE_RANGE_PREFIX.sub("", intro or "").strip()


def _fill_group_score(text, score, s):
    """묶음 머리의 `{점수}` 를 채운다. 못 채우면 그 표기를 **지운다**.

    정본은 `[각 3점씩]` 처럼 실제 값을 찍는다. 값을 모르는 채 `{점수}` 를
    그대로 인쇄하면 안 된다.
    """
    if "{점수}" not in text:
        return text
    if score is None:
        return re.sub(r"\s*[\[(（]\s*각?\s*\{점수\}[^\])）]*[\])）]", "",
                      text).strip()
    v = s.score_integer_form.replace("{n}", str(int(score))) \
        if float(score) == int(score) and "{n}" in (s.score_integer_form or "") \
        else None
    num = str(int(score)) if float(score) == int(score) else \
        f"{round(float(score), s.score_decimals)}"
    return text.replace("{점수}", num)


def _strip_leading_no(text, qno):
    """지문 머리의 원고 문항 번호를 뗀다. 번호가 그 문항 것일 때만."""
    m = re.match(r"\s*(\d{1,2})\s*[.)]?\s+", text)
    if m and int(m.group(1)) == int(qno):
        return text[m.end():]
    return text


def _is_prose_box(lines, limit=90):
    """상자 안이 문단인가(낱말 나열이 아니라) — 구조로 본다.

    나열은 슬래시·쉼표로 끊긴 짧은 토막이고, 문단은 긴 줄에 마침표가 있다.
    """
    text = " ".join(l.strip() for l in lines if l and l.strip())
    if not text:
        return False
    if len(text) < limit:
        return False
    # 슬래시·쉼표가 촘촘하면 나열이다
    seps = text.count("/") + text.count(",")
    return seps < max(3, len(text) // 60)


def _order_layout(items, s):
    """순서 배열 선지를 몇 열로 놓을까 — **단 폭에 들어가는 만큼**.

    정본 실측: 배재1 26-1-기말은 `(A)-(C)-(B)` 3칸이라 한 줄에 세 개가
    들어가고(①②③ / ④⑤), 26-1-중간은 5칸짜리라 한 줄에 하나씩 내려온다.
    같은 학교·같은 유형인데 배치가 다른 이유는 유형이 아니라 **길이**다.
    프로파일이 적어 둔 열 수를 상한으로 삼되, 폭이 모자라면 줄인다.
    """
    if s.order_layout in ("inline_row", "inline"):
        return "inline_row"
    if s.order_layout == "one_per_line":
        return "one_per_line"
    want = {"grid2": 2, "grid3": 3, "grid5": 5}.get(s.order_layout or "", 0)
    if not want:
        want = 3            # adaptive·auto·fit_per_line·미기재는 폭에 맡긴다
    longest = max((len((c.get("content") or "")) + 2 for c in items),
                  default=0)
    ch = s.role("choice")
    size = float(ch.get("size_pt") or 9.0)
    # 라틴 반각 기준 글자폭 ≈ 0.5em, 열 사이 여백 2mm
    per = longest * size * 0.5 * 25.4 / 72 + 2.0
    col = float(s.col_width or 100.0)
    n = want
    while n > 1 and per * n > col:
        n -= 1
    return f"grid{n}" if n > 1 else "one_per_line"


def _ab_labeled(it):
    """짝맞추기 표를 세울 근거가 있는가 — `(A)` `(B)` 레이블이 실제로 있는가.

    선지가 두 낱말로 갈린다고 다 짝이 아니다. 상일1 '두 단어가 반의어 관계에
    있지 않은 것은?' 은 어휘 쌍이라 표 머리행 `(A) (B)` 를 붙일 자리가 없다.
    발문·지문·보기 어디에도 레이블이 없으면 그냥 선지로 둔다.
    """
    parts = [it.get("question") or ""]
    parts += [b.get("content") or ""
              for b in (it.get("stimulus") or {}).get("blocks", [])]
    parts.append(((it.get("given") or {}) or {}).get("content") or "")
    blob = " ".join(parts)
    found = {m.group(1).upper() for m in _RE_AB_HEAD.finditer(blob)}
    return len(found & set("ABCDE")) >= 2


def _ab_head_line(text, n):
    """선지 표의 머리줄인지 — `(A) (B) (C)` 처럼 괄호 레이블만 있는 줄.

    원고가 선지 바로 앞에 지문처럼 끼워 준다. 열 수가 선지 칸 수와 같을
    때만 머리줄로 본다(우연히 본문에 나온 `(A)` 를 삼키지 않도록).
    """
    t = (text or "").strip()
    if len(t) > 40:
        return None
    parts = [x for x in re.split(r"[\s\t]+", t) if x]
    if len(parts) != n or not all(re.fullmatch(r"\(?[A-Ea-e]\)?", x)
                                  for x in parts):
        return None
    return [x if x.startswith("(") else f"({x})" for x in parts]


def _ab_heads(stem, n):
    """머리행 레이블 — 발문의 `(A)~(C)`·`(A), (B)` 에서 읽고, 없으면 자동."""
    seen = []
    for m in _RE_AB_HEAD.finditer(stem or ""):
        u = m.group(1).upper()
        if u not in seen:
            seen.append(u)
    if len(seen) < n:
        seen = [chr(ord("A") + i) for i in range(n)]
    return [f"({x})" for x in seen[:n]]


def _ab_sep(spec):
    """열 사이 구분자. 프로파일이 '없음(공백열)' 처럼 서술로 적어 둔 값도 있다."""
    v = spec.ab_sep
    if not v:
        return ""
    if any(w in v for w in ("없음", "공백", "탭", "정렬")):
        return ""
    return v if len(v) <= 8 else ""


def _number_items(doc):
    """문항에 번호를 미리 매기고 묶음 범위를 계산한다.

    원고는 번호도 묶음 범위도 주지 않는다(한영 계열 제외). 그래서 **먼저 전체를
    훑어 번호를 확정한 뒤** 묶음 머리를 쓴다 — 그러지 않으면 묶음 첫 문항에서
    범위 끝을 알 수 없어 `【 9 – 9 】` 같은 것이 나온다.
    """
    q = e = 0
    plan = []
    for it in doc.get("items", []):
        if it.get("kind") == "서술형":
            e += 1
            plan.append({"item": it, "essay": True, "no": e})
        else:
            q += 1
            plan.append({"item": it, "essay": False, "no": q})

    # 묶음. **원고가 준 묶음 id 를 먼저 믿는다** — `[9~10]` 처럼 범위를 명시한
    # 원고에서 도입문 사이 거리로 재면 다음 묶음까지 끌고 가 `[9~15]` 가 된다.
    gid = {}
    for i, r in enumerate(plan):
        g = (r["item"].get("header") or {}).get("group_id")
        if g:
            gid.setdefault(g, []).append(i)
    used = set()
    for g, idxs in gid.items():
        members = [plan[i] for i in idxs]
        _set_group(plan, idxs[0], members)
        used.update(idxs)

    # id 가 없는 원고는 도입문 사이 거리로 잡되, **지문 공유가 끝나는 곳**에서
    # 끊는다. 묶음은 지문 하나를 여러 문항이 나눠 쓰는 구조이므로, 자기 지문을
    # 다시 가진 문항은 그 묶음의 구성원이 아니다. 이 가름이 없으면 성덕2에서
    # `[8~22]` 15문항, 배재1에서 `[13~23]` 이 나온다(정본은 전부 2문항).
    starts = [i for i, r in enumerate(plan)
              if r["item"].get("_group_intro") and i not in used]
    bounds = sorted(starts + [i for i in used])
    for i in starts:
        nxt = [b for b in bounds if b > i]
        end = (nxt[0] - 1) if nxt else len(plan) - 1
        members = plan[i:end + 1]
        # 원고가 도입문에 `(1~3)` 처럼 범위를 적어 줬으면 **그 개수를 믿는다**.
        # 강동2·강동3 실증 — 어휘 묶음은 구성원마다 자기 예문을 갖는데, 지문
        # 공유 규칙만 쓰면 첫 문항만 남고 나머지가 묶음에서 떨어져 나간다.
        want = _declared_span(r_intro(plan[i]["item"]))
        if want and 1 < want <= len(members):
            members = members[:want]
        else:
            for j in range(1, len(members)):
                if _own_passage(members[j]["item"]):
                    members = members[:j]
                    break
        _set_group(plan, i, members)
    return plan


def _declared_span(intro):
    """도입문이 밝힌 묶음 크기. 번호가 아니라 **개수**만 쓴다(원고 번호와
    조판 번호가 어긋날 수 있다)."""
    m = _RE_RANGE_IN_INTRO.search(intro or "")
    if not m:
        return 0
    a, b = int(m.group(1)), int(m.group(2))
    n = b - a + 1
    return n if 1 < n <= 20 else 0


_OWN_PASSAGE_MIN = 200


def _own_passage(it, limit=_OWN_PASSAGE_MIN):
    """이 문항이 **자기 지문**을 갖는가 — 묶음 구성원이 아니라는 신호."""
    blocks = (it.get("stimulus") or {}).get("blocks") or []
    return sum(len(b.get("content") or "") for b in blocks) > limit


def _level_group_scores(plan, unit=0.1):
    """공통발문형 묶음의 구성원 배점을 **균등하게** 맞춘다.

    정본은 `[각 2.8점씩]` 처럼 묶음 안이 늘 같은 값이다. 배분표는 묶음을
    모르고 문항마다 다른 값을 주므로 여기서 고르게 편다. 고르게 펴면서
    생기는 차액은 **묶음 밖 문항**에 넘겨 총점을 그대로 지킨다.
    """
    spare = 0.0
    for row in plan:
        g = row.get("group")
        if not g or not g.get("common_stem"):
            continue
        hs = [m["item"].get("header") or {} for m in g["members"]]
        vals = [h.get("score") for h in hs]
        if any(v is None for v in vals) or len(set(vals)) == 1:
            continue
        n = len(vals)
        total = sum(vals)
        each = round(round(total / n / unit) * unit, 2)
        for h in hs:
            h["score"] = each
        spare = round(spare + total - each * n, 2)
    if abs(spare) < unit / 2:
        return
    # 차액은 묶음에 속하지 않은 문항 중 하나에 얹는다
    for row in plan:
        if row.get("no_stem"):
            continue
        h = row["item"].get("header") or {}
        if h.get("score") is None:
            continue
        nv = round(h["score"] + spare, 2)
        if 0.2 <= nv <= 12.0:
            h["score"] = nv
            return


def _set_group(plan, i, members):
    sel = [m for m in members if not m["essay"]]
    ess = [m for m in members if m["essay"]]
    intro = r_intro(plan[i]["item"])
    # 묶음 구성원이 저마다 발문을 갖는지 — 정본 한영1 규칙:
    # `…물음에 답하시오.` 면 개별발문형, 그 밖(주제·어휘·빈칸 …)은 공통발문형.
    common = bool(intro) and not _RE_GROUP_INDIV.search(intro)
    plan[i]["group"] = {
        "a": sel[0]["no"] if sel else None,
        "b": sel[-1]["no"] if sel else None,
        "essay_ns": [m["no"] for m in ess],
        "n": len(members),
        "intro": intro,
        "common_stem": common,
        "members": members,
    }
    if common:
        for m in members:
            m["no_stem"] = True


_RE_GROUP_INDIV = re.compile(r"물음에\s*답하시오|각\s*물음")


def r_intro(it):
    return strip_source(it.get("_group_intro") or "")


def build_body(doc, spec, case=None, scores=None):
    """IR 문서 → 본문 HTML + 경고."""
    r = Renderer(spec, case)
    scores = scores or {}
    sel_scores = list(scores.get("선택형") or [])
    ess_scores = list(scores.get("서답형") or [])
    plan = _number_items(doc)

    # 1패스 — 배점을 먼저 얹는다. 묶음 머리의 `[각 N점씩]` 이 구성원 배점을
    # 알아야 하므로 렌더보다 앞서야 한다.
    for row in plan:
        it = row["item"]
        pool = ess_scores if row["essay"] else sel_scores
        if len(pool) >= row["no"]:
            it.setdefault("header", {})["score"] = pool[row["no"] - 1]

    # 공통발문형 묶음은 배점을 머리에 한 번만 찍는다(정본 한영1 실측).
    # 묶음 머리에 배점 자리가 있는 학교만 해당한다. 자리가 없는데 구성원
    # 배점을 지우면 배점이 어디에도 안 찍힌다(강동2·강동3·한영2 실증).
    head_takes_score = "{점수}" in (spec.group_template or "")
    if head_takes_score:
        _level_group_scores(plan)
    for row in plan:
        g = row.get("group")
        if not g or not g.get("common_stem") or not head_takes_score:
            continue
        vals = [((m["item"].get("header") or {}).get("score"))
                for m in g["members"]]
        vals = [v for v in vals if v is not None]
        g["score"] = vals[0] if vals and len(set(vals)) == 1 else None
        if g["score"] is not None:
            for m in g["members"]:
                (m["item"].get("header") or {}).pop("score", None)

    # 2패스 — 렌더
    out = []
    for row in plan:
        it = row["item"]
        g = row.get("group")
        if g:
            if g["a"] is not None and g["b"] is not None and g["b"] > g["a"]:
                head = r.group_head(g["a"], g["b"], g["intro"], g["essay_ns"],
                                    g.get("score"))
            elif g["essay_ns"] and g["a"] is not None and spec.group_mixed:
                head = r.group_head(g["a"], g["a"], g["intro"], g["essay_ns"],
                                    g.get("score"))
            else:
                head = ""          # 묶음이 한 문항뿐 — 머리를 만들지 않는다
            if head:
                out.append(head)
            elif g["intro"]:
                out.append(f'<p class="group-intro">{esc(g["intro"])}</p>')
        ctx = {"member_no_stem": True} if row.get("no_stem") else {}
        ctx = dict(ctx, qno=row["no"])
        if g and not g.get("common_stem") and g.get("n", 0) > 1:
            # 개별발문형 묶음의 첫 문항: 지문을 공유하므로 발문 위로 올린다
            ctx = dict(ctx or {}, shared_passage=True)
        ctx = ctx or None
        out.append(r.item(it, ctx))
    return "\n".join(out), r.warnings, r.images


def score_table(spec, scores):
    """마지막 쪽 배점표(세종 계열).

    값은 배분표에서 오고 모양만 프로파일이 정한다 — 원고 문항 수가 정본과
    달라도 표가 따라 늘어난다. 가로 밴드형은 12칸씩 끊어 (번호행, 배점행)
    한 쌍을 만들고, 서답형이 있으면 마지막 밴드로 붙인다.
    """
    if not spec.score_table:
        return ""
    sel = list((scores or {}).get("선택형") or [])
    ess = list((scores or {}).get("서답형") or [])
    if not sel and not ess:
        return ""
    h_no, h_sc = spec.score_table_heads
    w = spec.score_table_band

    def band(labels, vals, span=1, whole=False):
        cells_n = "".join(f'<td colspan="{span}">{esc(str(x))}</td>'
                          for x in labels)
        cells_s = "".join(f'<td colspan="{span}">{esc(_fmt_cell(v, whole))}</td>'
                          for v in vals)
        pad = w - len(labels) * span
        if pad > 0:
            cells_n += f'<td colspan="{pad}"></td>'
            cells_s += f'<td colspan="{pad}"></td>'
        return (f'<tr><th>{esc(h_no)}</th>{cells_n}</tr>'
                f'<tr><th>{esc(h_sc)}</th>{cells_s}</tr>')

    rows = []
    for i in range(0, len(sel), w):
        chunk = sel[i:i + w]
        rows.append(band([str(i + j + 1) for j in range(len(chunk))], chunk))
    if ess and spec.score_table_essay:
        tpl = spec.score_table_essay_label or "서{n}"
        span = max(w // max(len(ess), 1), 1)
        rows.append(band([tpl.replace("{n}", str(j + 1))
                          for j in range(len(ess))], ess, span, whole=True))
    return ('<table class="score-table">'
            f'{"".join(rows)}</table>')


def _fmt_cell(v, whole=False):
    """표 안 표기 — **선택형은 항상 소수 한 자리**(`3.0`), 서답형만 정수(`5`).

    정본 실측: 선택형 밴드는 2.7·3.0 처럼 자릿수가 고르고, 서답형 밴드만
    `5` 로 적힌다. 값이 정수라고 선택형까지 `3` 으로 줄이면 실물과 어긋난다.
    """
    f = float(v)
    if whole and abs(f - round(f)) < 1e-9:
        return str(int(round(f)))
    return f"{f:.1f}"


def build_html(doc, spec, case=None, css_href="theme.css", scores=None,
               images=None):
    body, warns, imgs = build_body(doc, spec, case, scores)
    if images is not None:
        images.extend(imgs)
    s = spec
    case = case or {}
    head_html = _running_header(s, case)
    cont_html = continue_mark(s, case)
    foot_html = _running_footer(s, case)
    head_block = exam_head(s, case)
    notice = ""
    if s.notice_head:
        notice = ('<div class="notice-wrap">'
                  + "".join(f'<p class="notice">{esc(l)}</p>' for l in s.notice_head)
                  + "</div>")
    ending = ""
    if s.ending_lines:
        ending = "".join(f'<p class="ending">{esc(l)}</p>' for l in s.ending_lines)
    ending += score_table(s, scores)
    title = esc(f"{s.school} {s.grade} {s.subject_title}")
    doc_html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>{title}</title>
<link rel="stylesheet" href="{css_href}">
</head>
<body>
{head_html}
{foot_html}
{cont_html}
<section class="flow">
{head_block}
{notice}
{body}
{ending}
</section>
</body>
</html>
"""
    return doc_html, warns


def continue_mark(s, case=None):
    """'다음 쪽에 계속' 표시. **11개 학교에 있는데 아무도 그리지 않고 있었다.**

    표기가 학교마다 다르다 —
      · `text` 한 벌            (명일1·2·3, 배재2, 세종1)
      · `odd_text`/`even_text`  (강동1)  · `odd_pages`/`even_pages` (강동2)
      · `template_odd/even`     (성덕1)  · `parity_rule.{odd,even}`  (한영2)
      · `templates` 여러 벌      (성덕2)
    홀·짝이 갈리는 학교는 양면 인쇄라 문구가 다르다(같은 장 뒷면이냐 다음 장이냐).
    """
    cm = s.continue_marker or {}
    if not cm.get("on"):
        return ""
    odd = _first_str(cm, ("odd_text", "odd_pages", "template_odd"))
    even = _first_str(cm, ("even_text", "even_pages", "template_even"))
    par = cm.get("parity_rule")
    if isinstance(par, dict):
        odd = odd or _first_str(par, ("odd",))
        even = even or _first_str(par, ("even",))
    one = _first_str(cm, ("text",))
    if not one:
        tpl = cm.get("templates")
        if isinstance(tpl, dict):
            one = next((v for v in tpl.values() if isinstance(v, str)), "")
    odd = odd or one
    even = even or one
    if not odd and not even:
        return ""
    glyph = cm.get("glyph") or ""
    def one_html(txt, cls):
        t = _fill_marker(txt, glyph)
        return f'<div class="cont-mark {cls}">{esc(t)}</div>' if t else ""
    return one_html(odd, "cm-odd") + one_html(even, "cm-even")


def _first_str(d, names):
    for n in names:
        v = d.get(n)
        if isinstance(v, str) and v.strip():
            return v
    return ""


def _fill_marker(text, glyph):
    """`{유형}` 처럼 다음 쪽 내용에 달린 자리는 조판 시점에 못 채운다 —
    지어내지 말고 그 자리만 지운다(성덕1 `☞ 뒷면에 {유형} 계속`)."""
    t = re.sub(r"\{[^}]*\}", "", str(text or "")).strip()
    t = re.sub(r"\s{2,}", " ", t)
    if glyph and glyph not in t and len(glyph) <= 2:
        t = f"{t} {glyph}".strip()
    return t


def _running_header(s, case):
    bits = []
    if s.copyright and s.copyright_pos == "top":
        bits.append(f'<div class="copyright">{esc(s.copyright)}</div>')
    bits.append(repeating_head(s, case))
    bits = [b for b in bits if b]
    if not bits:
        return '<div class="page-header"></div>'
    return '<div class="page-header">' + "".join(bits) + "</div>"


def repeating_head(s, case=None):
    """**매 쪽 반복되는** 머리. 정본에서 7곳 중 5곳이 매 쪽 반복인데 조판은
    1쪽에만 찍고 있었다(한영1·한영2 표 전체, 세종1·성덕1·성덕2 한 줄).

    학교마다 반복분이 어디 적혀 있는지 다르다 —
      · 표 전체가 반복       → `running.header.repeat == "every"`
      · 매 쪽 줄 + 1쪽 덧붙임 → `running.header.line` / `running.header.running`
    """
    hdr = P.dig(s.raw, "running.header") or {}
    rep = str(hdr.get("repeat") or "")
    # ① 매 쪽 반복되는 줄이 따로 적힌 학교(세종1 `line`, 성덕 `running`)
    for key in ("line", "running", "other_pages"):
        v = hdr.get(key)
        lines = v if isinstance(v, list) else (
            v.get("lines") if isinstance(v, dict) else None)
        if lines is None and isinstance(v, dict):
            # 좌·중·우를 키로 적어 둔 학교(성덕1 `other_pages`, 성덕2 `running`)
            lines = [dict(v[side], align=side, role=v[side].get("role") or side)
                     for side in ("left", "center", "right")
                     if isinstance(v.get(side), dict)]
        if isinstance(lines, list) and lines:
            return _head_line_html(s, [x for x in lines if isinstance(x, dict)],
                                   case, cls="run-line")
    # ② 표 전체가 매 쪽 반복인 학교(한영1·한영2)
    if rep.startswith("every"):
        return header_table(s, case, table_cls="head-table run-table")
    return ""


def _head_line_html(s, els, case, cls="run-line"):
    """줄형 머리 한 벌을 HTML 로. 좌·중·우 정렬을 그대로 살린다."""
    out = []
    for e in els:
        role = e.get("role") or ""
        text = (case or {}).get(role) or _line_text(e)
        if not text or _RE_PAGENO.fullmatch(str(text).strip()):
            continue
        al = e.get("align") or "left"
        out.append(f'<span class="rl rl-{al}">{esc(str(text))}</span>')
    if not out:
        return ""
    return f'<div class="{cls}">' + "".join(out) + "</div>"


# ── 표형 머리표 ─────────────────────────────────────────────────────────────
# 16개 학교가 저마다 다른 표기로 셀을 적어 두었다(실측자가 달랐다). 이름이
# 아니라 **모양**으로 읽어 (행, 열, 병합, 글) 로 정규화한다.
_RE_PLACEHOLDER = re.compile(r"^\s*[(（].*[)）]\s*$")


def _cell_span(v):
    """`1` → (1,1) · `"2-3"` → (2,2) · `"1-3"` → (1,3)"""
    if isinstance(v, int):
        return v, 1
    m = re.match(r"\s*(\d+)\s*[-~]\s*(\d+)", str(v or "1"))
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return a, max(b - a + 1, 1)
    m = re.match(r"\s*(\d+)", str(v or "1"))
    return (int(m.group(1)) if m else 1), 1


_RE_SPAN_KO = re.compile(r"(\d+)\s*[~·,\-]\s*(\d+)\s*([열행])")


def _span_words(v):
    """`"1~6열 병합"` `"1·2행 병합"` `"좌측 전폭 병합"` → (rowspan, colspan)"""
    t = str(v or "")
    if not t:
        return 1, 1
    m = _RE_SPAN_KO.search(t)
    if m:
        n = int(m.group(2)) - int(m.group(1)) + 1
        return (n, 1) if m.group(3) == "행" else (1, n)
    if "전폭" in t or "전체" in t:
        return 1, 0            # 0 = 그 행 전체
    return 1, 1


def _header_grid(cells):
    """학교별 셀 표기를 [(row, col, rowspan, colspan, text, role)] 로 정규화."""
    out = []

    def colno(c, fallback):
        # 열 번호가 숫자면 그대로, 이름이면 **열이 아니라 셀 이름**이다
        # (한영3 `c="코드값"`). 그럴 땐 0 을 돌려 배치 단계에서 행 안 순서로
        # 왼쪽부터 빈 칸에 채운다.
        return c if isinstance(c, int) else 0

    for i, cell in enumerate(cells):
        if not isinstance(cell, dict):
            continue
        col = colno(cell.get("c", cell.get("col")), i + 1)
        # ① 라벨/값 두 줄짜리(명일·강동)
        if "label" in cell and "value" in cell:
            span = int(cell.get("rowspan") or 1)
            lab = str(cell["label"])
            # `(학교 배지)` 처럼 라벨 자체가 자리표면 그 칸은 통째로 비운다
            if _RE_PLACEHOLDER.match(lab):
                out.append((1, col, max(span, 2), 1, "", "logo"))
                continue
            if span > 1:
                out.append((1, col, span, 1, str(cell.get("value") or ""), "logo"))
            else:
                out.append((1, col, 1, 1, lab, "label"))
                out.append((2, col, 1, 1, str(cell["value"]), "value"))
            continue
        # ② row1 / row2 / row3 / row2_3 (한영1)
        rowkeys = [k for k in cell
                   if re.fullmatch(r"row\d(?:[_-]\d)?", k)]
        if rowkeys:
            if cell.get("rows"):
                r, sp = _cell_span(cell["rows"])
                out.append((r, col, max(sp, 3), 1,
                            str(cell.get("text") or ""), "title"))
                continue
            for k in rowkeys:
                m = re.findall(r"\d+", k)
                if not m:
                    continue
                r = int(m[0])
                sp = (int(m[-1]) - r + 1) if len(m) > 1 else 1
                out.append((r, col, sp, 1, str(cell[k]), k))
            continue
        # ③ r/row + c/col (한영2·한영3)
        r, sp = _cell_span(cell.get("r", cell.get("row", 1)))
        sp = max(sp, int(cell.get("rowspan") or 1))
        rs, cs = _span_words(cell.get("span"))
        out.append((r, col, max(sp, rs), cs, str(cell.get("text") or ""),
                    cell.get("role") or ""))
    return out


def _grid_from_rows(rows):
    """행 배열형 — 강동1·강동3(`rows:[{role,text|cells|labels}]`)과
    상일1·상일2(`rows|layout:[{row, cells:[{...}]}]`)를 함께 받는다."""
    out = []
    for ri, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            continue
        r = int(row.get("row") or ri)
        cells = row.get("cells")
        if not isinstance(cells, list):
            cells = row.get("labels")
        # ① 전폭 제목 행 (`merged`, `cells: 1`)
        if row.get("merged") or row.get("cells") in (1, "1"):
            txt = str(row.get("예") or row.get("text") or "")
            if "{" in txt:      # 템플릿만 있으면 실제 예시값을 쓴다
                txt = str(row.get("예") or "")
            out.append((r, 0, 1, 0, txt, row.get("role") or "title"))
            continue
        if isinstance(cells, list) and cells and isinstance(cells[0], str):
            for c in cells:
                out.append((r, 0, 1, 1, str(c), row.get("role") or "meta"))
            continue
        if isinstance(cells, list):
            for cell in cells:
                if not isinstance(cell, dict):
                    continue
                rs, cs = _span_words(cell.get("span"))
                rs = max(rs, int(cell.get("rowspan") or 1))
                out.append((r, 0, rs, cs, str(cell.get("text") or ""),
                            cell.get("role") or ""))
    return out


def _grid_from_rowkeys(hdr):
    """행별 키형 — 명일3(`row1`, `row2_labels`, `row3_values_예_*`)."""
    out = []
    r1 = hdr.get("row1")
    if isinstance(r1, dict):
        txt = r1.get("예_25-1") or r1.get("예") or r1.get("text") or ""
        if txt:
            out.append((1, 0, 1, 0, str(txt), "title"))
    labs = hdr.get("row2_labels") or []
    vals = None
    for k in sorted(hdr):
        if k.startswith("row3_values"):
            vals = hdr[k]
            break
    for c in labs:
        out.append((2, 0, 1, 1, str(c), "label"))
    for c in (vals or []):
        out.append((3, 0, 1, 1, str(c), "value"))
    return out


def _header_cells_source(hdr):
    """머리표 내용이 어느 키에 있든 grid 로 바꾼다. 학교마다 표기가 다르다."""
    if hdr.get("cells"):
        return _header_grid(hdr["cells"])
    for key in ("rows", "layout"):
        v = hdr.get(key)
        if isinstance(v, list) and v:
            return _grid_from_rows(v)
    if hdr.get("row2_labels"):
        return _grid_from_rowkeys(hdr)
    return []


_RE_ITEM_RANGE = re.compile(r"(\d+)\s*번\s*~\s*(\d+)\s*번\s*"
                            r"[(（]\s*(\d+)\s*문항\s*[)）]")


def _live_head_value(text, case, label=""):
    """머리표에 인쇄되는 **문항 범위**를 실제 조판값으로 갈아끼운다.

    프로파일 값은 정본 실측 시점의 고정 문자열이라(명일1 `1번 ~ 23번 (23문항)`)
    원고가 바뀌면 1쪽에 틀린 문항 수가 찍힌다. 표기 형식은 정본 그대로 두고
    숫자만 바꾼다.
    """
    m = _RE_ITEM_RANGE.search(text or "")
    if not m or not case:
        return text
    # 선택형이냐 서답형이냐는 **그 열의 라벨**로 가른다. 둘 다 1번부터라
    # 숫자만으로는 못 고른다(명일1 정본 23문항/2문항).
    tag = str(label or "")
    if "서답" in tag or "서술" in tag:
        n = case.get("n_ess")
    elif "선택" in tag or "객관" in tag:
        n = case.get("n_sel")
    else:
        return text
    if not n:
        return text
    return text[:m.start()] + f"{m.group(1)}번 ~ {n}번 ({n}문항)" + text[m.end():]


_RE_PAGENO = re.compile(r"\d+\s*/\s*\(?\s*\d+\s*\)?")


def header_table(s, case=None, table_cls="head-table"):
    """머리표가 **표**인 학교(16곳 중 14곳). 셀 방언을 정규화해 그린다."""
    hdr = P.dig(s.raw, "running.header") or {}
    grid = _header_cells_source(hdr)
    if not grid:
        return ""
    nrow = max(r + sp - 1 for r, _c, sp, _cs, _t, _o in grid)
    wide_rows = {r for r, c, _sp, cs, _t, _o in grid if not c and not cs}

    # ① 열 수 — (그 행 셀 수) + (다른 행 rowspan 이 그 행을 덮는 칸 수).
    #    전폭 행의 세로 병합 칸(상일 `문항`)을 빼먹으면 아래 행이 한 칸 밀린다.
    cover, need = {}, {}
    for r, _c, sp, cs, _t, _o in grid:
        for k in range(1, sp):
            cover[r + k] = cover.get(r + k, 0) + 1
        if r not in wide_rows:
            need[r] = need.get(r, 0) + max(cs, 1)
    fixed = [c + (cs - 1 if cs else 0) for _r, c, _sp, cs, _t, _o in grid if c]
    ncol = max([n + cover.get(r, 0) for r, n in need.items()] + fixed + [1])

    at, taken = {}, set()

    def place(r, col, sp, cs, text, role):
        at[(r, col)] = (sp, cs, text, role)
        width = cs if cs else ncol - col + 1
        for k in range(sp):
            for j in range(width):
                if (k, j) != (0, 0):
                    taken.add((r + k, col + j))

    # ② 열이 지정된 셀
    for r, c, sp, cs, text, role in grid:
        if c and (r, c) not in at:
            place(r, c, sp, cs, text, role)
    # ③ 전폭 행의 우측 셀 — 오른쪽 끝에서부터(정본 상일: 제목 좌, 문항·구분 우)
    for r in sorted(wide_rows):
        col = ncol
        for _r, _c, sp, cs, text, role in reversed(
                [g for g in grid if g[0] == r and not g[1] and g[3]]):
            while (r, col) in at or (r, col) in taken:
                col -= 1
            place(r, col, sp, cs, text, role)
            col -= max(cs, 1)
    # ④ 나머지 행을 왼쪽부터
    for r, c, sp, cs, text, role in grid:
        if c or r in wide_rows:
            continue
        col = 1
        while (r, col) in at or (r, col) in taken:
            col += 1
        place(r, col, sp, cs, text, role)
    # ⑤ 전폭 셀 — 그 행에 남은 왼쪽을 차지한다
    for r in sorted(wide_rows):
        for _r, _c, sp, _cs, text, role in [g for g in grid
                                            if g[0] == r and not g[1] and not g[3]]:
            width = 1
            while width < ncol and (r, 1 + width) not in at \
                    and (r, 1 + width) not in taken:
                width += 1
            place(r, 1, sp, width, text, role)

    taken = set()
    rows_html = []
    for r in range(1, nrow + 1):
        tds = []
        for c in range(1, ncol + 1):
            if (r, c) in taken:
                continue
            cell = at.get((r, c))
            if cell is None:
                tds.append("<td></td>")
                continue
            sp, cs, text, role = cell
            if not cs:
                cs = ncol - c + 1
            for k in range(1, sp):
                for j in range(cs):
                    taken.add((r + k, c + j))
            for j in range(1, cs):
                taken.add((r, c + j))
            txt = (case or {}).get(role) or text
            # 같은 열에서 **자기 바로 위** 셀이 그 칸의 라벨이다. 라벨 행이
            # 1행인 학교(명일2)도 있고 2행인 학교(명일1·명일3, 제목이 1행)도 있다.
            label = role or ""
            for rr in range(r - 1, 0, -1):
                up = at.get((rr, c))
                if up and up[2]:
                    label = up[2]
                    break
            txt = _live_head_value(txt, case, label)
            # `(결재 도장)` `(학교 배지)` 같은 자리표는 인쇄하지 않는다
            if _RE_PLACEHOLDER.match(txt or ""):
                txt = ""
            attr = (f' rowspan="{sp}"' if sp > 1 else "") + \
                   (f' colspan="{cs}"' if cs > 1 else "")
            cls = f' class="hc-{esc(role)}"' if role else ""
            body = esc(txt).replace("\n", "<br>")
            tds.append(f"<td{attr}{cls}>{body}</td>")
        rows_html.append("<tr>" + "".join(tds) + "</tr>")
    # `column-span: all` 이 걸린 래퍼로 감싼다 — 감싸지 않으면 본문 단이
    # 머리표 위에서 시작해 글자가 겹친다.
    if table_cls != "head-table":   # 러닝 머리 — 흐름 래퍼를 씌우지 않는다
        return f'<table class="{table_cls}">' + "".join(rows_html) + "</table>"
    return ('<header class="exam-head"><table class="head-table">'
            + "".join(rows_html) + "</table></header>")


def _header_lines(hdr):
    """줄형 머리표 — 표가 아니라 낱개 줄로 쌓는 학교(성덕1·성덕2·세종1).

    `first_page.lines` 배열이기도 하고 `line1` `line2_left` 처럼 키별로
    흩어져 있기도 하다. 실측자가 달라 표기가 갈렸을 뿐 내용은 같은 꼴이다.
    """
    fp = hdr.get("first_page") or {}

    def keep(e):
        # 쪽번호는 러닝 요소가 찍는다. 머리표에 적힌 것은 실측 당시의 고정
        # 문자열(`1/8`)이라 실제 쪽수와 어긋나고 두 번 찍힌다. role 이 없는
        # 학교(성덕1 `line2_right`)가 있어 값의 꼴로도 가른다.
        if "page_number" in str(e.get("role") or ""):
            return False
        t = str(e.get("text") or e.get("예") or "").strip()
        return not re.fullmatch(r"\d+\s*/\s*\(?\s*\d+\s*\)?", t)

    lines = fp.get("lines")
    if isinstance(lines, list) and lines:
        return [x for x in lines if isinstance(x, dict) and keep(x)]
    out = []
    side = {"left": 0, "center": 1, "right": 2}
    for k in fp:
        v = fp[k]
        if not isinstance(v, dict):
            continue
        if (v.get("text") or v.get("예") or v.get("template")) and \
                keep(v) and "page" not in k:
            out.append((k, dict(v, role=v.get("role") or k)))
    if out:
        def order(kv):
            k = kv[0]
            m = re.search(r"\d+", k)
            ln = int(m.group(0)) if m else 99
            pos = next((p for w, p in side.items() if w in k), 1)
            return (ln, pos)
        return [v for _k, v in sorted(out, key=order)]
    ln = hdr.get("line")
    if isinstance(ln, list) and ln:
        return [x for x in ln if isinstance(x, dict)]
    return []


def _line_text(e):
    """줄의 인쇄값. 템플릿만 있으면 실측 예시를 쓴다."""
    t = e.get("text")
    if t and "{" not in str(t):
        return str(t)
    for k in ("예", "예_25-1", "예_24-1"):
        if e.get(k):
            return str(e[k])
    return "" if (t and "{" in str(t)) else str(t or "")


def exam_head(s, case=None):
    """시험지 머리표 — 프로파일 running.header 를 그대로 옮긴다.

    학교마다 표이기도 하고(한영·명일·상일) 낱개 요소 + 이중선이기도 하다(배재).
    프로파일이 적어 둔 elements 를 순서대로 놓고, 정렬·크기·서체만 CSS 로 준다.
    프로파일에 머리표가 없으면 **아무것도 그리지 않는다**.
    """
    case = case or {}
    hdr = P.dig(s.raw, "running.header") or {}
    els = hdr.get("elements") or []
    if str(hdr.get("repeat") or "").startswith("every") and not els:
        # 표 전체가 매 쪽 반복이면 러닝이 찍는다 — 흐름에 또 넣지 않는다
        if not (hdr.get("first_page") or hdr.get("masthead_first_page")):
            return ""
    if not els:
        tbl = header_table(s, case)
        if tbl:
            return tbl
        els = _header_lines(hdr)
        if not els:
            return ""
    rows = []
    for e in els:
        role = e.get("role")
        text = case.get(role) or _line_text(e)
        if not text and role == "code_value":
            # 과목 코드 값은 프로파일 subject_code 에서 온다 — 정본에 큰 숫자로
            # 인쇄되는데 요소에 text 가 없어 통째로 빠져 있었다.
            text = str(s.subject_code or "")
        if not text:
            continue
        cls = ["eh", f"eh-{role}"] if role else ["eh"]
        if e.get("align") == "center":
            cls.append("eh-center")
        elif e.get("align") == "right":
            cls.append("eh-right")
        if e.get("underline"):
            cls.append("eh-underline")
        st = []
        size = e.get("size_pt")
        if size:
            st.append(f"font-size:{size}pt")
        # 정본에서 잰 자리에 그대로 앉힌다. 머리표는 표가 아니라 낱개 요소라
        # 흘려 보내면 과목 코드 값이 오른쪽 끝으로 튀는 등 배치가 어긋난다.
        m = e.get("실측_정본") or {}
        mx, my = _num0(m.get("x")), _num0(m.get("y"))
        if mx and my and s.ref_scale:
            cls.append("eh-abs")
            st.append(f"left:{round(mx * s.ref_scale, 2)}mm")
            st.append(f"top:{round(my * s.ref_scale, 2)}mm")
        style = f' style="{";".join(st)}"' if st else ""
        rows.append(f'<span class="{" ".join(cls)}"{style}>{esc(text)}</span>')
    if not rows:
        return ""
    rule = '<div class="eh-rule"></div>' if hdr.get("double_rule") else ""
    abs_h = _head_height(els, s)
    style = f' style="height:{abs_h}mm"' if abs_h else ""
    return (f'<header class="exam-head"{style}>' + "".join(rows) + rule
            + "</header>")


def _num0(v):
    """실측값이 dict/list 로 적힌 학교가 있다(세종1) — 숫자가 아니면 0."""
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _head_height(els, s):
    """절대 배치한 머리표가 차지할 높이 — 본문이 그 아래에서 시작하도록."""
    ys = [_num0((e.get("실측_정본") or {}).get("y")) for e in els]
    if not any(ys) or not s.ref_scale:
        return 0
    big = max(_num0((e.get("실측_정본") or {}).get("size_pt")) for e in els)
    return round(max(ys) * s.ref_scale + big * 25.4 / 72 * s.ref_scale + 2, 1)


def _running_footer(s, case):
    bits = []
    if s.page_number:
        tpl = esc(s.page_number).replace("{p}", "</span>").replace("{n}", "</span>")
        bits.append('<div class="pgnum"></div>')
    if s.copyright and s.copyright_pos != "top":
        bits.append(f'<div class="copyright">{esc(s.copyright)}</div>')
    return '<div class="page-footer">' + "".join(bits) + "</div>"


if __name__ == "__main__":
    import json
    import sys
    key = sys.argv[1]
    ir = json.load(open(sys.argv[2], encoding="utf-8"))
    spec = P.get(key)
    doc, warns = build_html(ir, spec)
    sys.stderr.write("\n".join("⚠ " + w for w in warns) + "\n")
    print(doc)
