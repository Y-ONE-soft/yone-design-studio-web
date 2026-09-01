"""손잡이(knob) 선언 — **무엇을 만질 수 있는지**를 계열이 스스로 말한다.

## 왜 필요한가

지금까지 손잡이는 계열마다 그때그때 필요한 것만 즉흥적으로 뚫려 있었다.

    vocaunit  색 20여 개 + 파트별 · 치수 오버라이드 · theme.py 완전 파라미터화
    vocabook  common + sections · 치수 5개
    special   파트별 7색 · 치수 0개
    blackbook 색 0개(CSS 에 박힘) · 레이아웃 8개

**어디에도 "무엇을 만질 수 있다"는 선언이 없다.** 그래서
 ⑴ 사용자는 뭘 고칠 수 있는지 몰라 무조건 클로드를 부르고
 ⑵ 편집기를 만들 수 없고(폼을 그릴 스키마가 없다)
 ⑶ 클로드조차 매번 계열 코드를 읽어 확인해야 한다(컨텍스트 소모).

계열이 손잡이를 **선언**하면 이 셋이 한 번에 풀린다. 편집기는 선언에서 폼을
자동으로 그리므로 계열별 UI 를 따로 만들 필요가 없다.

## 두 가지 손잡이

    css 있음   값을 `:root{--이름: 값}` 으로 내보낸다 (테마가 **고정 CSS** 인 계열)
    css 없음   계열 코드가 config 를 이미 읽고 있다 (테마를 **생성**하는 계열)

`blackbook` 은 앞쪽, `vocabook`·`vocaunit` 은 뒤쪽이다. 둘을 한 스키마로 묶어야
편집기가 계열을 가리지 않는다.

## ⚠ 손잡이는 **덮어쓰기만** 한다

기본값은 지금 테마에 들어 있는 값 그대로고, config 에 없는 키는 **아무것도
내보내지 않는다**. 그래야 손잡이를 뚫는 것만으로는 지면이 한 픽셀도 안 바뀐다
(납품 중인 책이 있으므로 이건 협상 대상이 아니다). 회귀는
`scripts/vivlio_baseline.py compare` 로 확인한다.

## ⚠ 손잡이를 너무 많이 뚫지 말 것

손잡이 30개짜리 폼은 아무도 안 쓴다. **계열당 8~15개**, 기준은 "실제로 시안
왕복이 났던 자리"다. 그 목록은 지어내는 게 아니라 이미 있다 — 지금까지의 수정
이력이 곧 손잡이 후보다.
"""
import copy
import json

# 손잡이 묶음 — 편집기가 이 차례로 접어 보여 준다
# 편집기가 이 차례로 접어 보여 준다. "섹션"은 파트·섹션마다 되풀이되는
# 색 묶음(상일보카 6섹션 × 3색) — 주색과 섞으면 목록이 안 읽힌다.
GROUPS = ("색", "섹션", "치수", "고급")


class Knob(object):
    """손잡이 하나.

    key     config 안의 점 경로 (`palette.gold`, `metrics.slot`)
    kind    color | mm | pt | number | enum | bool
    css     내보낼 CSS 변수 이름(`--gold`). 계열이 직접 읽는 값이면 None.
    default 지금 테마에 들어 있는 값 — 편집기가 '되돌리기'에 쓴다
    affects 이 값이 지면 어디에 나타나는가 (사람이 읽는 말)
    """

    __slots__ = ("key", "kind", "label", "css", "default", "min", "max",
                 "step", "unit", "values", "affects", "group", "resettable")

    def __init__(self, key, kind, label, css=None, default=None,
                 min=None, max=None, step=None, unit="", values=None,
                 affects="", group="색", resettable=None):
        self.key, self.kind, self.label = key, kind, label
        self.css, self.default = css, default
        self.min, self.max, self.step, self.unit = min, max, step, unit
        self.values, self.affects, self.group = values or (), affects, group
        # **되돌릴 수 있는가** — 우리가 '진짜 기본값'을 아는 손잡이만.
        # blackbook 처럼 테마 CSS 에 기본값이 박힌 계열은 지우면 그 값으로
        # 돌아간다. 반대로 vocabook·vocaunit 의 팔레트는 **config 가 곧 원본**
        # 이라 지우면 계열 코드의 임시 폴백으로 떨어져 디자인이 달라진다 →
        # 그런 손잡이는 되돌리기를 막는다(모르는 값을 아는 척하지 않는다).
        self.resettable = (default is not None) if resettable is None \
            else bool(resettable)

    def to_dict(self, value=None):
        d = {"key": self.key, "kind": self.kind, "label": self.label,
             "group": self.group, "affects": self.affects,
             "default": self.default, "value": value,
             "resettable": self.resettable}
        for f in ("min", "max", "step", "unit"):
            if getattr(self, f) not in (None, ""):
                d[f] = getattr(self, f)
        if self.values:
            d["values"] = list(self.values)
        if self.css:
            d["css"] = self.css
        return d


# ── config 안의 점 경로 읽고 쓰기 ──────────────────────────────────
def get(data, key, default=None):
    cur = data
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def has(data, key):
    _miss = object()
    return get(data, key, _miss) is not _miss


def put(data, key, value):
    """점 경로에 값을 넣는다(중간 딕트는 만든다). data 를 그 자리에서 고친다."""
    parts = key.split(".")
    cur = data
    for p in parts[:-1]:
        if not isinstance(cur.get(p), dict):
            cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = value
    return data


def unset(data, key):
    """손잡이를 기본값으로 되돌린다 = config 에서 지운다."""
    parts = key.split(".")
    cur = data
    for p in parts[:-1]:
        if not isinstance(cur, dict) or p not in cur:
            return data
        cur = cur[p]
    if isinstance(cur, dict):
        cur.pop(parts[-1], None)
    return data


# ── 계열에 묻기 ──────────────────────────────────────────────────
def of(cfg, series):
    """계열이 선언한 손잡이 목록. 계열이 선언하지 않았으면 빈 목록.

    ⚠ `series` 는 **인스턴스**여야 한다. 클래스를 넘기면 `knobs()` 가 self 를 못
      받아 터진다 — 실제로 그랬고, 더 나쁜 것은 그때 빌드가 죽었는데도 폴더에
      **먼저 만든 PDF 가 남아 있어 회귀 대조가 통과**했다는 점이다. 그래서
      여기서 조용히 넘어가지 않고 분명히 알린다.
    """
    if isinstance(series, type):
        series = series()
    # 판형·도련처럼 **어느 책에나 있는 것**은 계열이 저마다 선언하게 두지
    # 않는다 — 그러면 인디자인의 「문서 설정」이 책마다 다른 꼴이 된다.
    base = []
    bf = getattr(series, "base_knobs", None)
    if bf is not None:
        base = list(bf()) or []
    fn = getattr(series, "knobs", None)
    if fn is None:
        return base
    return base + (list(fn(cfg)) or [])


def describe(cfg, series):
    """편집기에 넘길 형태 — 손잡이 + **지금 값** + 기본값과 다른가."""
    out = []
    for k in of(cfg, series):
        v = get(cfg.data, k.key, None)
        d = k.to_dict(v if v is not None else k.default)
        d["overridden"] = has(cfg.data, k.key)
        out.append(d)
    return out


# ── CSS 로 내보내기 ──────────────────────────────────────────────
def css_text(cfg, series):
    """`css` 가 붙은 손잡이 중 **config 에 실제로 있는 것만** `:root` 로.

    ⚠ 없는 키를 기본값으로 채워 내보내면 안 된다 — 그 순간 CSS 우선순위가 바뀌어
      (파일 뒤쪽 규칙·명시도) 지면이 달라질 수 있다. 덮어쓰기만 한다.
    """
    lines = []
    for k in of(cfg, series):
        if not k.css or not has(cfg.data, k.key):
            continue
        v = get(cfg.data, k.key)
        if v is None:
            continue
        if k.kind in ("mm", "pt") and isinstance(v, (int, float)):
            v = "%g%s" % (v, k.kind)
        lines.append("  %s: %s;   /* %s */" % (k.css, v, k.label))
    if not lines:
        return ""
    return ("/* 손잡이 덮어쓰기 — config.json 이 정한 값만 나온다.\n"
            "   여기를 직접 고치지 말 것(빌드마다 다시 쓰인다). */\n"
            ":root {\n" + "\n".join(lines) + "\n}\n")


def table_css():
    """표 기본 모양 — 계열 테마가 덮어써도 된다.

    작업대에서 넣은 표는 어느 계열에서나 같은 모양이어야 한다. 계열 테마마다
    따로 적으면 계열이 늘 때마다 또 적어야 한다.
    """
    from core.render_vivlio import table as _t
    return _t.CSS


def page_rules_text(cfg):
    """`config.page_rules` → `@page` 규칙.

    ## 인디자인의 마스터 페이지에 해당한다

    머리말·꼬리말·여백처럼 **면에 걸리는 것**은 단락 스타일로는 못 건드린다.
    CSS 조판에서는 `@page` 가 그 자리다 — 왼쪽 면·오른쪽 면·첫 면을 갈라
    여백과 머리·꼬리를 정한다.

        "page_rules": {
          ":left":  {"margin-left": "23mm", "margin-right": "26mm"},
          ":right": {"margin-left": "26mm", "margin-right": "23mm"},
          "":       {"margin-top": "31.5mm"}
        }

    ⚠ 계열 테마의 `@page` **뒤에** 나가므로 여기 적은 것이 이긴다. 그래서
      한 줄만 적어도 그 값만 바뀐다(테마를 통째로 베낄 필요가 없다).
    """
    rules = cfg.section("page_rules") or {}
    if not rules:
        return ""
    out = ["\n/* 마스터 페이지(@page) — 작업대의 문서 설정이 쓴다. */"]
    for sel, props in rules.items():
        if not isinstance(props, dict) or not props:
            continue
        body = "\n".join("  %s: %s;" % (k, v) for k, v in props.items()
                          if str(v).strip())
        if body:
            out.append("@page %s {\n%s\n}" % (str(sel).strip(), body))
    return "\n".join(out) + "\n" if len(out) > 1 else ""


def styles_text(cfg):
    """`config.styles` → CSS 규칙. **단락 스타일 패널**이 여기에 쓴다.

        "styles": {
          ".head":  { "font-size": "9pt", "letter-spacing": "-0.01em" },
          "[data-ref=\"lessons.0.problems.3\"]": { "break-before": "page" }
        }

    선택자를 그대로 쓴다 — 조판 규칙을 손보는 자리라 갇힌 목록으로는 모자란다.
    ⚠ 값 검사는 브라우저(CSS 파서)에 맡긴다. 이상한 값은 그 규칙만 무시된다.
    """
    st = cfg.section("styles") or {}
    out = []
    for sel, props in st.items():
        if not isinstance(props, dict) or not props:
            continue
        body = "\n".join("  %s: %s;" % (k, v) for k, v in props.items() if v != "")
        if body:
            out.append("%s {\n%s\n}" % (sel, body))
    if not out:
        return ""
    return ("\n/* 단락 스타일 — 작업대의 스타일 패널이 쓴다. 손으로 고쳐도 되지만\n"
            "   패널에서 다시 저장하면 덮어쓴다. */\n" + "\n".join(out) + "\n")


def write(cfg, series, build_dir, name="knobs.css"):
    """`build/knobs.css` 를 쓴다. 덮어쓸 값이 없으면 **빈 파일**.

    빈 파일이어도 링크는 늘 있어야 한다 — 있다 없다 하면 계열 HTML 이 책마다
    달라져서 회귀 대조가 어려워진다.
    """
    from core.render_vivlio import stage
    return stage.write_css(build_dir, name,
                           css_text(cfg, series) + styles_text(cfg)
                           + page_rules_text(cfg)
                           + (table_css() if _has(cfg, "table") else "")
                           + (box_css() if _has(cfg, "box") else ""))


def box_css():
    """자유 배치 상자의 기본 모양 — 계열 테마가 덮어써도 된다."""
    from core.render_vivlio import box as _b
    return _b.CSS


def _has(cfg, kind):
    """이 책에 그 블록이 실제로 있나. 원고와 편집 이력을 **둘 다** 본다."""
    import os
    needle = '"%s"' % kind
    for name in ("data.json", "edits.json"):
        p = cfg.path(name)
        if not os.path.exists(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                if needle in f.read():
                    return True
        except OSError:
            pass
    return False


def has_block(cfg, kind):
    """작업대가 넣은 블록이 이 책에 있나 — **계열 밖에서도** 물어본다.

    중등부는 조판 코드가 3계층 밖에 살아 `knobs.css` 를 안 쓴다. 그 다리가
    표·상자 CSS 를 직접 뽑아야 해서 밖으로 연다.
    """
    return _has(cfg, kind)


def _has_table(cfg):
    """이 책에 **표가 실제로 있나.**

    표 CSS 는 아무 것도 안 맞으면 무해하지만, 없는 책까지 넣으면 `knobs.css` 가
    책마다 달라질 이유가 없는데 달라진다. 있는 책에만 넣는다.

    ⚠ **원고와 편집 이력을 둘 다** 본다. 작업대에서 넣은 표는 `edits.json` 에
      있어서 `data.json` 만 보면 못 찾는다 — 그러면 표가 괘선 없이 글자만
      늘어선 채로 나간다(실제로 그랬다).
    """
    import os
    for name in ("data.json", "edits.json"):
        p = cfg.path(name)
        if not os.path.exists(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                if '"table"' in f.read():
                    return True
        except OSError:
            pass
    return False


# ── 값 바꾸기 (편집기·CLI 공용) ───────────────────────────────────
def apply(cfg_data, changes):
    """`{키: 값}` 을 config 딕트 사본에 반영해 돌려준다. None = 기본값으로 되돌리기."""
    data = copy.deepcopy(cfg_data)
    for key, value in (changes or {}).items():
        if value is None:
            unset(data, key)
        else:
            put(data, key, value)
    return data


# ── config.json 을 **서식을 지키며** 고치기 ─────────────────────────
# 통째로 다시 쓰면(`json.dump`) 값은 맞지만 **손으로 맞춘 서식이 사라진다** —
# 빈 줄 묶음, `"page": { "width": 210, … }` 처럼 한 줄로 쓴 것, 주석 구실을 하는
# `_note` 의 자리. 작업대에서 색 하나 바꿀 때마다 파일 전체가 뒤집히면 안 되므로
# **바뀐 값의 자리만** 갈아 끼운다. (실제로 한 번 뒤집어 놓고 되돌렸다.)

_WS = " \t\r\n"


class _Scan(object):
    """원문 위치를 들고 다니는 최소 JSON 훑개. 값 스팬을 경로별로 모은다."""

    def __init__(self, raw):
        self.s = raw
        self.i = 0
        self.spans = {}          # 점경로 → (키 시작, 값 시작, 값 끝)

    def ws(self):
        while self.i < len(self.s) and self.s[self.i] in _WS:
            self.i += 1

    def string(self):
        assert self.s[self.i] == '"'
        j = self.i + 1
        while True:
            c = self.s[j]
            if c == "\\":
                j += 2
                continue
            if c == '"':
                break
            j += 1
        out = json.loads(self.s[self.i:j + 1])
        self.i = j + 1
        return out

    def value(self, path):
        self.ws()
        c = self.s[self.i]
        if c == "{":
            return self.obj(path)
        if c == "[":
            return self.arr(path)
        if c == '"':
            self.string()
            return
        j = self.i
        while j < len(self.s) and self.s[j] not in ",}]" + _WS:
            j += 1
        self.i = j

    def obj(self, path):
        start = self.i
        self.i += 1                      # {
        while True:
            self.ws()
            if self.s[self.i] == "}":
                self.i += 1
                # ⚠ 루트는 `path` 가 빈 문자열이라 그냥 이으면 `".{}"` 가 된다.
                #   그래서 **최상위에 새 키를 넣을 자리**를 못 찾아, config 를
                #   통째로 다시 쓰다가 손으로 맞춘 모양(빈 줄·한 줄짜리 객체)을
                #   다 잃었다.
                self.spans[(path + ".{}") if path else "{}"] = (
                    start, start, self.i)
                return
            kstart = self.i
            key = self.string()
            self.ws()
            assert self.s[self.i] == ":"
            self.i += 1
            self.ws()
            vstart = self.i
            sub = (path + "." + key) if path else key
            self.value(sub)
            self.spans[sub] = (kstart, vstart, self.i)
            self.ws()
            if self.s[self.i] == ",":
                self.i += 1

    def arr(self, path):
        self.i += 1                      # [
        n = 0
        while True:
            self.ws()
            if self.s[self.i] == "]":
                self.i += 1
                return
            self.value("%s[%d]" % (path, n))
            n += 1
            self.ws()
            if self.s[self.i] == ",":
                self.i += 1


def spans(raw):
    sc = _Scan(raw)
    sc.value("")
    return sc.spans


def _indent_of(raw, pos):
    """pos 가 있는 줄의 들여쓰기 문자열."""
    ls = raw.rfind("\n", 0, pos) + 1
    j = ls
    while j < len(raw) and raw[j] in " \t":
        j += 1
    return raw[ls:j]


def patch_text(raw, changes):
    """원문 JSON 문자열에 `{키: 값}` 을 반영. None 이면 그 키를 지운다.

    바뀌는 곳만 손대므로 나머지 줄·빈 줄·한 줄짜리 객체가 그대로 남는다.
    되돌려 읽을 수 없는 모양이면(원문이 JSON 이 아니면) 예외를 낸다 —
    부르는 쪽이 통째 쓰기로 물러설 수 있게.
    """
    sp = spans(raw)
    # 뒤에서부터 고쳐야 앞쪽 위치가 안 밀린다
    todo = []
    for key, val in (changes or {}).items():
        if key in sp:
            todo.append((sp[key][0], "del" if val is None else "set", key, val))
        elif val is not None:
            parent = key.rsplit(".", 1)[0] if "." in key else ""
            pkey = (parent + ".{}") if parent else "{}"
            if pkey not in sp:
                # 부모 객체가 아예 없다 — **있는 데까지 올라가 통째로 만든다.**
                # 예전엔 여기서 포기했고, 부르는 쪽은 config 를 통째로 다시 써
                # 손으로 맞춘 모양을 다 잃었다(`verify.design.strict` 를 켜려다
                # 그럴 뻔했다). 없는 것은 우리가 만들면 된다.
                have, rest = parent, []
                while have and (have + ".{}") not in sp:
                    have, _, last = have.rpartition(".")
                    rest.insert(0, last)
                anchor = ((have + ".{}") if have else "{}")
                if anchor not in sp:
                    raise KeyError("부모가 없다: " + parent)
                leaf = key.rsplit(".", 1)[1] if "." in key else key
                nested = {leaf: val}
                for name in reversed(rest[1:]):
                    nested = {name: nested}
                todo.append((sp[anchor][2], "add",
                             (have + "." if have else "") + rest[0], nested))
                continue
            todo.append((sp[pkey][2], "add", key, val))
    out = raw
    for pos, kind, key, val in sorted(todo, key=lambda t: -t[0]):
        if kind == "set":
            _, vs, ve = sp[key]
            out = out[:vs] + json.dumps(val, ensure_ascii=False) + out[ve:]
        elif kind == "del":
            ks, _, ve = sp[key]
            j = ve
            while j < len(out) and out[j] in _WS:
                j += 1
            if j < len(out) and out[j] == ",":    # 뒤 쉼표까지 지운다
                ve = j + 1
            else:                                  # 마지막 멤버면 앞 쉼표를 지운다
                k = ks - 1
                while k >= 0 and out[k] in _WS:
                    k -= 1
                if k >= 0 and out[k] == ",":
                    ks = k
            # 줄 전체가 비면 그 줄도 지운다
            ls = out.rfind("\n", 0, ks) + 1
            le = ve
            while le < len(out) and out[le] in " \t":
                le += 1
            if out[ls:ks].strip() == "" and le < len(out) and out[le] == "\n":
                ks, ve = ls, le + 1
            out = out[:ks] + out[ve:]
        else:                                      # add — 부모 `}` 앞에 끼운다
            _, _, pe = sp[(key.rsplit(".", 1)[0] + ".{}") if "." in key else "{}"]
            brace = pe - 1                         # `}` 자리
            body = out[:brace].rstrip()
            ind = _indent_of(out, brace) + "  "
            sep = "" if body.endswith("{") else ","
            line = "%s\n%s%s: %s\n%s" % (
                sep, ind, json.dumps(key.rsplit(".", 1)[-1], ensure_ascii=False),
                json.dumps(val, ensure_ascii=False), _indent_of(out, brace))
            out = body + line + out[brace:]
    json.loads(out)                                # 깨졌으면 여기서 걸린다
    return out
