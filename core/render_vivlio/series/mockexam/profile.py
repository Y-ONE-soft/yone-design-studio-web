# -*- coding: utf-8 -*-
"""학교 프로파일 로딩 — 손으로 쓴 관측을 렌더러가 쓸 수 있는 형태로 정규화한다.

프로파일(`profiles/<학교키>.json`)은 **관측**이고 `_결정.json`은 **정책**이다.
둘을 합쳐 렌더러가 바로 쓰는 `Spec` 을 낸다.

프로파일은 학교마다 다른 사람(에이전트)이 실측해 쓴 것이라 **필드 모양이 조금씩
다르다**. 그래서 여기는 방어적으로 읽는다 — 없으면 터지는 게 아니라 `missing` 에
쌓아 두고, 렌더러가 그 자리를 비운 채 조판하고 검수 게이트가 지목한다.
"어림값으로 채워 넣고 조용히 넘어가는 것"이 가장 나쁘다.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILES = os.path.join(HERE, "profiles")

_cache = {}


class ProfileError(Exception):
    pass


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def decisions():
    """사용자가 확정한 조판 정책."""
    if "_결정" not in _cache:
        _cache["_결정"] = _load(os.path.join(PROFILES, "_결정.json"))
    return _cache["_결정"]


def manifest():
    if "_manifest" not in _cache:
        _cache["_manifest"] = _load(os.path.join(PROFILES, "_reference_manifest.json"))
    return _cache["_manifest"]


def available():
    """조판 대상 학교키 목록 (제외된 학교는 빠진다)."""
    out = []
    for f in sorted(os.listdir(PROFILES)):
        if f.endswith(".json") and not f.startswith("_"):
            out.append(f[:-5])
    return out


def raw(key):
    """프로파일 원본 dict."""
    if key not in _cache:
        p = os.path.join(PROFILES, key + ".json")
        if not os.path.exists(p):
            excl = os.path.join(PROFILES, "_제외", key + ".json")
            if os.path.exists(excl):
                raise ProfileError(
                    f"{key} 은 범위에서 제외된 학교다 (profiles/_제외/). "
                    f"다시 넣으려면 프로파일을 profiles/ 로 옮기고 _결정.json 의 "
                    f"대상학교를 고칠 것.")
            raise ProfileError(
                f"{key} 프로파일이 없다. 있는 학교: {', '.join(available())}")
        _cache[key] = _load(p)
    return _cache[key]


# ── 값 꺼내기 ───────────────────────────────────────────────────────────────

def dig(d, path, default=None):
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return default
        cur = cur.get(part)
        if cur is None:
            return default
    return cur


def _first(d, paths, default=None):
    """여러 후보 경로 중 먼저 값이 있는 것. 프로파일 모양 차이를 흡수한다."""
    for p in paths:
        v = dig(d, p)
        if v not in (None, "", [], {}):
            return v
    return default


def _str(v, default=None):
    """문자열로 강제. 프로파일이 같은 자리에 dict 를 넣어 둔 경우가 있다
    (명일2 `summary.render`, 명일3 `summary.arrow.glyph`) — 사람이 설명을
    덧붙이려다 모양이 갈린 것이라, 값처럼 생긴 항목을 골라 준다."""
    if v is None:
        return default
    if isinstance(v, str):
        return v
    if isinstance(v, dict):
        for k in ("glyph", "value", "text", "render", "형태", "값", "표기"):
            if isinstance(v.get(k), str):
                return v[k]
        for k, x in v.items():
            if not str(k).startswith("_") and isinstance(x, str):
                return x
        return default
    if isinstance(v, list) and v:
        return _str(v[0], default)
    return str(v)


def _num(v, default=None):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().rstrip("ptmm").strip()
        try:
            return float(s)
        except ValueError:
            return default
    if isinstance(v, list) and v:
        return _num(v[0], default)
    return default


class Spec(object):
    """렌더러가 쓰는 정규화된 학교 규칙.

    값이 없으면 None 을 두고 `missing` 에 무엇이 왜 없는지 남긴다. 렌더러는
    None 을 만나면 그 요소를 **그리지 않는다** — 그럴듯한 기본값으로 때우지 않는다.
    """

    def __init__(self, key, prof, dec):
        self.key = key
        self.raw = prof
        self.dec = dec
        self.missing = []
        self._build()

    # ── 기록 ──
    def _need(self, name, value, why=""):
        if value in (None, "", [], {}):
            self.missing.append(f"{name}{(' — ' + why) if why else ''}")
            return None
        return value

    def _build(self):
        p = self.raw
        self.school = _first(p, ["school"], self.key)
        self.school_short = _first(p, ["school_short"], "")
        self.grade = _first(p, ["grade"], "")
        self.subject_title = _first(p, ["subject_title"], "")
        self.subject_code = _first(p, ["subject_code"], "")

        # ── 정본 ──
        self.ref_exam = dig(p, "reference.exam")
        self.ref_kind = dig(p, "reference.kind")
        # '대체 정본인가' 는 프로파일 산문이 아니라 지정표의 ok 로 판정한다 —
        # 어떤 프로파일은 fallback 자리에 "없음 — 직전 회차가 있다" 라고 적었다.
        entry = (manifest().get("schools") or {}).get(self.key) or {}
        self.ref_fallback = entry.get("fallback") if entry.get("ok") is False else None
        self.is_fallback = entry.get("ok") is False
        self.approx = bool(dig(p, "typography.approx"))

        # ── 지면 (제품 상수 B4, 프로파일 값은 B4 환산치) ──
        size = _first(p, ["page.size_mm"], self.dec["판형"]["값"])
        self.page_w, self.page_h = float(size[0]), float(size[1])
        self.columns = int(_num(_first(p, ["page.columns"], 2)) or 2)
        # 필드명이 학교마다 다르다(사람이 쓴 관측이라). 후보를 넓게 잡는다.
        self.col_origin = _first(p, [
            "page.column_origin_mm", "page.column_origins_mm",
            "page.column_origin_mm_b4", "page.현행_단.col1"])
        self.col_width = _num(_first(p, [
            "page.column_width_mm", "page.col_w_mm", "page.column_width_mm_b4",
            "page.columns_geom.mm_column_width", "page.현행_단.column_width_mm"]))
        self.col_gap = _num(_first(p, [
            "page.column_gap_mm", "page.gap_mm", "page.column_gap_mm_b4",
            "page.columns_geom.mm_column_gap", "page.현행_단.column_gap_mm"]))
        self.text_left = _num(_first(p, [
            "page.text_left_mm", "page.현행_단.text_left_mm",
            "page.columns_geom.mm_text_left"]))
        self.text_right = _num(_first(p, [
            "page.text_right_mm", "page.columns_geom.mm_text_right"]))
        self.rule_top = _num(_first(p, ["page.rule_top_mm", "page.hrule.top_mm"]))
        self.rule_bottom = _num(_first(p, ["page.rule_bottom_mm", "page.hrule.bottom_mm"]))

        cr = _first(p, ["page.column_rule"], {}) or {}
        self.column_rule = bool(cr.get("on"))
        self.column_rule_pt = _num(cr.get("width_pt"), 0.24)

        pb = _first(p, ["page.page_border"], {}) or {}
        self.page_border = bool(pb.get("on"))
        self.page_border_pt = _num(pb.get("width_pt"), 1.0)

        if self.col_width is None and self.columns == 2 and self.text_left and self.text_right:
            gap = self.col_gap or 5.0
            self.col_width = (self.text_right - self.text_left - gap) / 2.0
        self._need("page.column_width_mm", self.col_width, "단 폭을 못 정했다")

        # ── 서체·크기 (역할별) ──
        self.roles = {}
        for name, r in (dig(p, "typography.roles") or {}).items():
            if not isinstance(r, dict):
                continue
            self.roles[name] = {
                "font": r.get("font"),
                "size_pt": _num(r.get("size_pt")),
                "leading_pt": _num(r.get("leading_pt")),
                "bold": bool(r.get("bold")),
                "indent_mm": _num(r.get("first_line_indent_mm") or r.get("indent_mm"), 0.0),
                "hang_mm": _num(r.get("hang_mm"), 0.0),
                "space_before_pt": _num(r.get("space_before_pt"), 0.0),
                "align": r.get("align") or "justify",
            }
        for must in ("passage", "stem", "choice"):
            if must not in self.roles:
                self.missing.append(f"typography.roles.{must} — 역할 수치가 없다")

        # ── 표기 ──
        self.q_template = _str(_first(p, ["numbering.question.template"]), "{n}.") or "{n}."
        self.qnum_size = _num(_first(p, ["numbering.question.marker_size_pt",
                                         "typography.roles.qnum.size_pt"]))
        self.essay_template = self._need(
            "numbering.essay.template",
            _str(_first(p, ["numbering.essay.template"])),
            "서답형 라벨 형식")
        self.essay_counter = _first(p, ["numbering.essay.counter"], "separate")
        # 상일 계열은 라벨이 문자열이 아니라 **표**다(반전 칩 + 유형칸).
        # template 은 사람이 읽는 설명일 뿐이므로 render/cells 를 따로 꺼낸다.
        self.essay_render = _first(p, ["numbering.essay.render"], "inline")
        self.essay_cells = _first(p, ["numbering.essay.cells"], [])
        self.essay_score_bracket = _first(p, ["numbering.essay.score_bracket",
                                              "numbering.essay.score_after_table.text"])
        self.essay_is_table = bool(self.essay_cells) or "chip" in (self.essay_render or "")
        self.essay_pos = _first(p, ["numbering.essay.pos"], "inline")
        self.group_template = _str(_first(p, ["numbering.group.template"]))
        self.group_mixed = _str(_first(p, ["numbering.group.mixed_template"]))
        self.group_intro_same_line = bool(
            _first(p, ["numbering.group.intro_on_same_line"], True))

        # ── 배점 ──
        self.score_bracket = _str(_first(p, ["score.bracket"]))
        self.score_attach = _first(p, ["score.attach"], "stem_end")
        self.score_space = _first(p, ["score.space_before"], "")
        self.score_decimals = int(_num(_first(p, ["score.decimals"], 1)) or 1)
        self.score_integer_form = _first(p, ["score.integer_form"], "{n}점")
        self.score_variation = dig(p, "score.variation.정책") or "single"

        # ── 상자 ──
        self.given = self._box(p, "given")
        self.cond = self._box(p, "cond")
        self.summary = {
            "marker": _str(_first(p, ["summary.marker"])),
            "render": _str(_first(p, ["summary.render"]), "plain") or "plain",
            "arrow": _str(_first(p, ["summary.arrow.glyph", "summary.arrow"])),
        }
        self.given_sentence = self._box(p, "given_sentence")

        # ── 선지 ──
        self.choice_layout = _str(_first(p, ["choices.layout"]), "one_per_line") or "one_per_line"
        self.choice_marker = _first(p, ["choices.marker"], "①")
        self.ab_sep = _str(_first(p, ["choices.ab_pair.separator"]))
        self.insert_marker = _first(p, ["choices.insert_marker"], "( ① )")

        # ── 러닝 요소 ──
        self.copyright = _str(_first(p, ["running.copyright.text"]))
        self.copyright_pos = _first(p, ["running.copyright.pos"], "bottom")
        self.page_number = _str(_first(p, ["running.page_number.template"]))
        self.page_number_pos = _first(p, ["running.page_number.pos"], "bottom_center")
        self.continue_marker = dig(p, "running.continue_marker") or {}
        self.notice_head = _first(p, ["running.notice_head.lines", "notice.head"], [])

        # ── 마무리 ──
        end = _first(p, ["ending.text"])
        self.ending_lines = ([str(x) for x in end] if isinstance(end, list)
                             else ([str(end)] if end else []))
        self.ending = self.ending_lines[0] if self.ending_lines else None
        self.ending_align = _first(p, ["ending.align"], "center")
        self.ending_bold = bool(dig(p, "ending.bold"))
        st = dig(p, "score_table") or {}
        self.score_table = bool(st.get("on"))
        # 배점표(세종 계열) — 마지막 쪽 마무리 문구 아래. 값은 배분표에서 오고
        # 모양만 프로파일이 정한다. `cols` 는 머리칸을 포함한 수라 1을 뺀다.
        self.score_table_layout = _str(st.get("layout"), "horizontal_bands")
        self.score_table_band = max(int(_num(st.get("cols"), 13) or 13) - 1, 1)
        self.score_table_essay = bool(st.get("includes_essay"))
        self.score_table_essay_label = _str(st.get("essay_label_in_table"),
                                            "서{n}")
        self.score_table_border_pt = float(_num(st.get("border_pt"), 0.24)
                                           or 0.24)
        self.score_table_heads = (_str(st.get("head_no"), "번호"),
                                  _str(st.get("head_score"), "배점"))

    def _box(self, p, name):
        b = p.get(name) or {}
        border = b.get("border") or {}
        return {
            "marker": _str(b.get("marker")),
            "render": _str(b.get("render"), "plain_line") or "plain_line",
            "align": _str(b.get("align"), "left") or "left",
            "border_pt": _num(border.get("width_pt"), 0.4),
            "pad_mm": _num(border.get("pad_mm"), 1.5),
            "item_marker": b.get("item_marker"),
        }

    # ── 편의 ──
    def role(self, name, fallback="passage"):
        return self.roles.get(name) or self.roles.get(fallback) or {}

    def fmt_score(self, value):
        """배점 문자열. 괄호가 없는 학교(세종1)는 None 을 돌려 '안 찍는다'를 뜻한다."""
        if not self.score_bracket or self.score_attach == "none":
            return None
        b = self.score_bracket
        open_c, close_c = (b[0], b[-1]) if len(b) >= 2 else ("[", "]")
        if float(value) == int(value):
            body = self.score_integer_form.replace("{n}", str(int(value)))
            if "{n}" not in self.score_integer_form:
                body = f"{int(value)}점"
        else:
            body = f"{round(float(value), self.score_decimals)}점"
        return f"{self.score_space}{open_c}{body}{close_c}"

    def report(self):
        return {
            "key": self.key, "school": self.school, "grade": self.grade,
            "정본": self.ref_exam, "정본성격": self.ref_kind,
            "대체": bool(self.ref_fallback), "수치근사": self.approx,
            "missing": self.missing,
        }


def get(key):
    """학교키 → Spec."""
    return Spec(key, raw(key), decisions())


if __name__ == "__main__":
    import sys
    keys = sys.argv[1:] or available()
    for k in keys:
        s = get(k)
        r = s.report()
        flag = "대체" if r["대체"] else "직전"
        print(f"{k:6s} {r['정본']:9s} {flag} {'근사' if r['수치근사'] else '실측'} "
              f"| 단 {s.columns}×{s.col_width}mm | 배점 {s.score_bracket} "
              f"| 서답형 {s.essay_template} | 마무리 {s.ending!r}")
        for m in r["missing"]:
            print(f"        ⚠ {m}")
