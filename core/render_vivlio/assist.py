# -*- coding: utf-8 -*-
"""작업대의 클로드 칸 — 한국어로 시키면 **디자인 값**을 고쳐 준다.

## 왜 좁게 여는가

작업대에는 이미 「직접 손보기(CSS)」 칸이 있었는데, 그건 CSS 를 쓸 줄 아는
사람만 쓸 수 있어 사실상 빈 칸이었다. 사람이 하고 싶은 말은
"머리 띠를 좀 더 진하게" 이지 `.sechdr{background:#…}` 가 아니다.

그렇다고 모델에게 리포를 통째로 열어 주면 안 된다. **계열 코드를 고치면 그
계열 책이 전부 흔들리고, 원고를 고치면 납품본과 글이 달라진다.** 그래서 손댈
수 있는 곳을 셋으로 못 박는다 — 셋 다 **그 책 폴더 안 파일**이라 다른 책은
어떤 경우에도 안 바뀐다.

    knobs           config.json 의 손잡이 값 (계열이 선언한 것만)
    styles          config.json 의 `styles` 절 → build/knobs.css
    overrides_css   그 책의 overrides.css

## ⚠ 모델이 준 것을 그대로 쓰지 않는다

`apply()` 는 받은 것을 **전부 다시 검사한다.**
  · 손잡이는 계열이 선언한 키만, 색은 `#rrggbb`, 치수는 min~max 안
  · 선택자·속성은 작업대의 손 편집과 **같은 검사**를 지난다(`{`·`}`·`;`·`<`)
  · CSS 는 길이 상한과 `@import`·바깥 `url(` 금지 — 조판이 밖으로 나가면 안 된다
모델이 엉뚱한 것을 주면 **고치지 않고 이유를 돌려준다.** 조용히 반만 먹는 것이
제일 나쁘다.

## ⚠ 되돌릴 수 있어야 한다

고치기 전에 `config.json`·`overrides.css` 를 `.bak` 으로 남긴다.
작업대는 그 둘을 되돌리는 단추를 준다.
"""
import json
import os
import re

MODEL = os.environ.get("YONE_ASSIST_MODEL", "claude-sonnet-5")
MAX_CSS = 8000
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
BAD_CSS = re.compile(r"@import|url\(\s*['\"]?(?:https?:)?//|expression\(|</", re.I)
BAD_CHARS = "{};<>"


class Refused(Exception):
    """고치지 않고 돌려보낸다. 메시지는 **사람에게 보여 줄 말**이다."""


def have_key():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


# ── 모델에게 줄 것 ────────────────────────────────────────────────
def context(cfg, knobs_spec, page_classes=(), picked=""):
    """지금 이 책의 상태. **원고는 넣지 않는다** — 고칠 수 있는 것이 아니다."""
    ks = []
    for k in knobs_spec:
        ks.append({"key": k.get("key"), "kind": k.get("kind"),
                   "label": k.get("label"), "affects": k.get("affects"),
                   "value": k.get("value"), "default": k.get("default"),
                   "min": k.get("min"), "max": k.get("max"),
                   "unit": k.get("unit")})
    ov = ""
    p = cfg.path("overrides.css")
    if os.path.exists(p):
        ov = open(p, encoding="utf-8").read()[:MAX_CSS]
    return {
        "series": cfg.series,
        "book": {k: cfg.book.get(k) for k in ("title", "school", "period")},
        "page": cfg.page,
        "knobs": ks,
        "styles": cfg.section("styles") or {},
        "overrides_css": ov,
        "page_classes": sorted(set(page_classes))[:120],
        "picked": picked,
    }


SYSTEM = """너는 인쇄 교재 조판의 디자인을 손보는 조수다. 한국어로 답한다.

고칠 수 있는 것은 셋뿐이다.
  knobs          계열이 선언한 손잡이 값 (아래 목록에 있는 key 만)
  styles         CSS 선택자 → 속성. 조판에 그대로 얹힌다
  overrides_css  그 책에만 걸리는 CSS 한 장

지켜야 하는 것
  · 목록에 없는 손잡이 key 를 지어내지 마라.
  · 색은 `#rrggbb`. 치수는 주어진 min~max 안에서.
  · 확실하지 않으면 **고치지 말고** `note` 에 무엇이 필요한지 적어라.
    엉뚱하게 고치는 것보다 안 고치는 편이 낫다.
  · 이건 **인쇄물**이다. 화면용 효과(그림자·애니메이션·hover)는 쓰지 마라.
  · 본문 글자는 8pt 아래로 내리지 마라(읽을 수 없다).
  · 사용자가 말한 것만 고쳐라. 겸사겸사 다른 데를 손보지 마라.

`note` 에는 **무엇을 왜 그렇게 바꿨는지** 한두 문장으로 적는다."""

TOOL = {
    "name": "apply_design",
    "description": "디자인 값을 고친다. 고칠 것이 없으면 note 만 채운다.",
    "input_schema": {
        "type": "object",
        "properties": {
            "knobs": {"type": "object",
                      "description": "손잡이 key → 값. 목록에 있는 key 만."},
            "styles": {"type": "object",
                       "description": "선택자 → {속성: 값}. 값이 빈 문자열이면 그 속성을 지운다."},
            "overrides_css": {"type": "string",
                              "description": "그 책 overrides.css 전체를 이걸로 바꾼다. 안 바꾸려면 넣지 마라."},
            "note": {"type": "string", "description": "무엇을 왜 바꿨는지 한두 문장."},
        },
        "required": ["note"],
    },
}


def ask(prompt, ctx, log=None):
    """모델에게 묻는다. 키가 없으면 **어떻게 넣는지** 알려 주고 멈춘다."""
    if not have_key():
        raise Refused(
            "클로드 키가 없습니다. 터미널에서 "
            "`export ANTHROPIC_API_KEY=…` 를 넣고 통합웹을 다시 띄우세요.")
    try:
        import anthropic
    except ImportError:
        raise Refused("`anthropic` 꾸러미가 없습니다 — `pip install anthropic`")
    client = anthropic.Anthropic()
    r = client.messages.create(
        model=MODEL, max_tokens=4000, system=SYSTEM, tools=[TOOL],
        tool_choice={"type": "tool", "name": "apply_design"},
        messages=[{"role": "user", "content":
                   "지금 이 책의 상태다:\n```json\n"
                   + json.dumps(ctx, ensure_ascii=False, indent=1)
                   + "\n```\n\n시킬 일: " + prompt}])
    for blk in r.content:
        if getattr(blk, "type", "") == "tool_use":
            return dict(blk.input or {})
    raise Refused("모델이 고칠 것을 내놓지 않았습니다.")


# ── 받은 것을 다시 검사한다 ────────────────────────────────────────
def vet(out, knobs_spec):
    """모델이 준 것을 **전부** 검사한다. 통과한 것만 돌려준다."""
    spec = {k.get("key"): k for k in knobs_spec}
    knobs, styles, bad = {}, {}, []

    for key, val in (out.get("knobs") or {}).items():
        k = spec.get(key)
        if not k:
            bad.append(f"모르는 손잡이: {key}")
            continue
        if k.get("kind") == "color":
            if not (isinstance(val, str) and HEX.match(val)):
                bad.append(f"{key}: 색은 #rrggbb 여야 한다 ({val})")
                continue
        elif k.get("kind") in ("mm", "pt", "number"):
            try:
                val = float(val)
            except (TypeError, ValueError):
                bad.append(f"{key}: 숫자가 아니다 ({val})")
                continue
            lo, hi = k.get("min"), k.get("max")
            if lo is not None and val < lo or hi is not None and val > hi:
                bad.append(f"{key}: {lo}~{hi} 밖이다 ({val})")
                continue
        knobs[key] = val

    for sel, props in (out.get("styles") or {}).items():
        if not isinstance(sel, str) or not sel.strip() or len(sel) > 200 \
                or any(c in sel for c in "{}"):
            bad.append(f"이상한 선택자: {sel}")
            continue
        if not isinstance(props, dict):
            bad.append(f"{sel}: 규칙이 없다")
            continue
        clean = {}
        for pk, pv in props.items():
            if any(c in str(pk) + str(pv) for c in BAD_CHARS):
                bad.append(f"{sel} {pk}: 이상한 값")
                continue
            clean[str(pk)] = str(pv)
        if clean:
            styles[sel.strip()] = clean

    css = out.get("overrides_css")
    if css is not None:
        if not isinstance(css, str) or len(css) > MAX_CSS:
            bad.append("CSS 가 너무 길다")
            css = None
        elif BAD_CSS.search(css):
            bad.append("CSS 에 바깥을 부르는 것이 들어 있다(@import·http url)")
            css = None

    return {"knobs": knobs, "styles": styles, "overrides_css": css,
            "note": str(out.get("note") or "")[:1000], "refused": bad}
