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

_RE_GREP_BOLD = re.compile(r"(\(\s*[A-Ea-e]\s*\)|\[[AB]\])")
_RE_SOURCE_TAG = re.compile(
    r"\s*\[\s*(?:\d{2}년\s*\d{1,2}월[^\]]*|\d{4}\.[^\]]*번[^\]]*|"
    r"\d+\s*과[^\]]*|\d+강[^\]]*|[^\]]*수능특강[^\]]*)\]\s*")


def esc(t):
    return html.escape(t or "", quote=False)


def strip_source(text):
    """출처 태그 제거 — 시험지에 인쇄되면 안 된다(현행 결함 중 하나)."""
    return _RE_SOURCE_TAG.sub(" ", text or "").strip()


class Renderer(object):
    def __init__(self, spec, case=None):
        self.s = spec
        self.case = case or {}
        self.q_no = 0
        self.essay_no = 0
        self.warnings = []

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

    def group_head(self, a, b, intro, essay_ns=None):
        """묶음 머리. 학교마다 괄호·구분자·혼합 표기가 다르다."""
        s = self.s
        if not s.group_template:
            # 묶음 표기를 안 쓰는 학교(상일1·광문2·세종1 일부) — 머리를 만들지 않는다
            return ""
        if essay_ns and s.group_mixed:
            tpl = s.group_mixed
            marker = tpl.replace("{n}", str(a)).replace("{m}", str(essay_ns[0]))
        else:
            marker = s.group_template.replace("{a}", str(a)).replace("{b}", str(b))
        marker = re.sub(r"\{지시문\}", "", marker).strip()
        text = f"{marker} {intro}".strip() if s.group_intro_same_line and intro \
            else marker
        body = esc(text)
        if not s.group_intro_same_line and intro:
            body += f'</p><p class="group-intro">{esc(intro)}'
        return f'<p class="group">{body}</p>'

    # ── 상자 ──────────────────────────────────────────────────────────────
    def box(self, cls, box_spec, label, lines):
        """보기/조건 — 프로파일의 render 방식대로."""
        if not lines:
            return ""
        render = box_spec.get("render") or "plain_line"
        marker = label or box_spec.get("marker") or ""
        body = "".join(f'<p class="{cls}">{self.inline(l)}</p>' for l in lines)

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
        is_essay = it.get("kind") == "서술형"
        score = (it.get("header") or {}).get("score")

        # 발문 — 번호(또는 서답형 라벨) + 본문 + 배점
        q = strip_source(it.get("question") or "")
        if is_essay:
            self.essay_no += 1
            label, took = self.essay_label(self.essay_no, it.get("label"), score)
            tail = "" if took else self.score_str(score)
            if s.essay_is_table or s.essay_pos == "own_line":
                out.append(label)
                out.append(f'<p class="stem srv">{self.inline(q)}{tail}</p>')
            else:
                out.append(f'<p class="stem srv">{label} {self.inline(q)}{tail}</p>')
        else:
            self.q_no += 1
            num = f'<span class="qnum">{self.qnum(self.q_no)}</span> '
            if group_ctx and group_ctx.get("member_no_stem"):
                out.append(f'<p class="stem">{num}{self.score_str(score)}</p>')
            else:
                out.append(f'<p class="stem">{num}{self.inline(q)}'
                           f'{self.score_str(score)}</p>')

        # 지문
        for blk in (it.get("stimulus") or {}).get("blocks", []):
            content = strip_source(blk.get("content") or "")
            if not content:
                continue
            label = blk.get("label")
            if label == "Sym":
                arrow = s.summary.get("arrow") or content
                out.append(f'<p class="summary-arrow">{esc(arrow)}</p>')
                continue
            cls = "passage"
            if blk.get("kind") == "para":
                cls = "passage passage-context"
            if label == "Ans":
                cls = "answer"
            out.append(f'<p class="{cls}">'
                       f'{self.inline(content, blk.get("marks"), grep_bold=True)}</p>')

        # 보기
        given = it.get("given")
        if given and given.get("content"):
            lines = [l for l in given["content"].split("\n") if l.strip()]
            out.append(self.box("given", s.given, s.given.get("marker"), lines))

        # 조건
        if it.get("constraints"):
            out.append(self.box("cond", s.cond, s.cond.get("marker"),
                                list(it["constraints"])))

        # 선지
        ch = it.get("choices")
        if ch and ch.get("items"):
            items = ch["items"]
            layout = s.choice_layout or "one_per_line"
            cells = []
            for c in items:
                lab = c.get("label") or ""
                cells.append(f'<p class="choice">'
                             f'{self.inline((lab + " " + c["content"]).strip())}</p>')
            if layout in ("grid2", "grid3"):
                n = 2 if layout == "grid2" else 3
                out.append(f'<div class="choice-grid g{n}">' + "".join(cells) + "</div>")
            else:
                out.append("".join(cells))
        return "\n".join(x for x in out if x)


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

    # 묶음: 도입문이 나온 문항부터, 다음 도입문(또는 끝) 직전까지가 한 묶음이다.
    starts = [i for i, r in enumerate(plan) if r["item"].get("_group_intro")]
    for gi, i in enumerate(starts):
        end = starts[gi + 1] - 1 if gi + 1 < len(starts) else len(plan) - 1
        members = plan[i:end + 1]
        sel = [m for m in members if not m["essay"]]
        ess = [m for m in members if m["essay"]]
        plan[i]["group"] = {
            "a": sel[0]["no"] if sel else None,
            "b": sel[-1]["no"] if sel else None,
            "essay_ns": [m["no"] for m in ess],
            "n": len(members),
            "intro": r_intro(plan[i]["item"]),
        }
    return plan


def r_intro(it):
    return strip_source(it.get("_group_intro") or "")


def build_body(doc, spec, case=None, scores=None):
    """IR 문서 → 본문 HTML + 경고."""
    r = Renderer(spec, case)
    scores = scores or {}
    sel_scores = list(scores.get("선택형") or [])
    ess_scores = list(scores.get("서답형") or [])
    out = []
    for row in _number_items(doc):
        it = row["item"]
        g = row.get("group")
        if g:
            if g["a"] is not None and g["b"] is not None and g["b"] > g["a"]:
                head = r.group_head(g["a"], g["b"], g["intro"], g["essay_ns"])
            elif g["essay_ns"] and g["a"] is not None and spec.group_mixed:
                head = r.group_head(g["a"], g["a"], g["intro"], g["essay_ns"])
            else:
                head = ""          # 묶음이 한 문항뿐 — 머리를 만들지 않는다
            if head:
                out.append(head)
            elif g["intro"]:
                out.append(f'<p class="group-intro">{esc(g["intro"])}</p>')
        # 배점은 원고가 안 주므로 배분표에서 꺼내 얹는다
        if row["essay"]:
            if len(ess_scores) >= row["no"]:
                it.setdefault("header", {})["score"] = ess_scores[row["no"] - 1]
        else:
            if len(sel_scores) >= row["no"]:
                it.setdefault("header", {})["score"] = sel_scores[row["no"] - 1]
        out.append(r.item(it))
    return "\n".join(out), r.warnings


def build_html(doc, spec, case=None, css_href="theme.css", scores=None):
    body, warns = build_body(doc, spec, case, scores)
    s = spec
    case = case or {}
    head_html = _running_header(s, case)
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


def _running_header(s, case):
    bits = []
    if s.copyright and s.copyright_pos == "top":
        bits.append(f'<div class="copyright">{esc(s.copyright)}</div>')
    if not bits:
        return '<div class="page-header"></div>'
    return '<div class="page-header">' + "".join(bits) + "</div>"


def exam_head(s, case=None):
    """시험지 머리표 — 프로파일 running.header 를 그대로 옮긴다.

    학교마다 표이기도 하고(한영·명일·상일) 낱개 요소 + 이중선이기도 하다(배재).
    프로파일이 적어 둔 elements 를 순서대로 놓고, 정렬·크기·서체만 CSS 로 준다.
    프로파일에 머리표가 없으면 **아무것도 그리지 않는다**.
    """
    case = case or {}
    hdr = P.dig(s.raw, "running.header") or {}
    els = hdr.get("elements") or []
    if not els:
        return ""
    rows = []
    for e in els:
        text = case.get(e.get("role")) or e.get("text") or ""
        if not text:
            continue
        cls = ["eh"]
        if e.get("align") == "center":
            cls.append("eh-center")
        elif e.get("align") == "right":
            cls.append("eh-right")
        if e.get("underline"):
            cls.append("eh-underline")
        size = e.get("size_pt")
        style = f' style="font-size:{size}pt"' if size else ""
        rows.append(f'<span class="{" ".join(cls)}"{style}>{esc(text)}</span>')
    if not rows:
        return ""
    rule = '<div class="eh-rule"></div>' if hdr.get("double_rule") else ""
    return '<header class="exam-head">' + "".join(rows) + rule + "</header>"


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
