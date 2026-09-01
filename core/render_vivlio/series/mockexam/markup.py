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
        """서답형 라벨. 학교에 따라 문자열이거나 **표**다(상일 계열)."""
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
                    f'{tail}</div>')
        tpl = s.essay_template or "[서답형 {n}]"
        return f'<span class="essay-no">{esc(tpl.replace("{n}", str(n)))}</span>'

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
            label = self.essay_label(self.essay_no, it.get("label"), score)
            if s.essay_is_table or s.essay_pos == "own_line":
                out.append(label)
                out.append(f'<p class="stem srv">{self.inline(q)}'
                           f'{self.score_str(score)}</p>')
            else:
                out.append(f'<p class="stem srv">{label} {self.inline(q)}'
                           f'{self.score_str(score)}</p>')
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


def build_body(doc, spec, case=None):
    """IR 문서 → 본문 HTML + 경고."""
    r = Renderer(spec, case)
    out = []
    for it in doc.get("items", []):
        intro = it.get("_group_intro")
        if intro:
            gid = (it.get("header") or {}).get("group_id") or ""
            m = re.search(r"G-(\d+)-(\d+)", gid)
            a, b = (int(m.group(1)), int(m.group(2))) if m else (r.q_no + 1, r.q_no + 1)
            head = r.group_head(a, b, strip_source(intro))
            if head:
                out.append(head)
            elif intro:
                # 묶음 표기를 안 쓰는 학교 — 지시문만 발문 자리에 둔다
                out.append(f'<p class="group-intro">{esc(strip_source(intro))}</p>')
        out.append(r.item(it))
    return "\n".join(out), r.warnings


def build_html(doc, spec, case=None, css_href="theme.css"):
    body, warns = build_body(doc, spec, case)
    s = spec
    case = case or {}
    head_html = _running_header(s, case)
    foot_html = _running_footer(s, case)
    notice = ""
    if s.notice_head:
        notice = "".join(f'<p class="notice">{esc(l)}</p>' for l in s.notice_head)
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
