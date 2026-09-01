"""서식이 있는 글을 **사람이 고칠 수 있는 한 줄**로 폈다 되접는다.

원고에서 온 글은 굵기·밑줄·기울임을 조각으로 들고 있다:

    ["다음 글의 ", {"t": "밑줄 친", "u": true}, " 부분을 고르시오."]

작업대에서 오타 하나를 고치려고 이걸 그대로 보여 줄 수는 없다. 그렇다고 서식을
버리고 민글로 받으면 **밑줄이 사라진다** — 어법 문제는 밑줄이 곧 문제라서 그건
글자를 고치는 게 아니라 문제를 망가뜨리는 것이다(특강에서 이미 겪었다).

그래서 서식을 눈에 보이는 표시로 폈다가 되접는다:

    다음 글의 __밑줄 친__ 부분을 고르시오.

    **굵게**   __밑줄__   //기울임//   \\**  는 글자 그대로의 별표

⚠ **민글로 들어온 것은 민글로 돌려준다.** 형태가 바뀌면(문자열 → 목록) 그 자체로
  data.json 이 달라져 회귀 대조가 시끄러워진다.
"""
import re

MARKS = (("b", "**"), ("u", "__"), ("i", "//"))
_ESC = re.compile(r"\\(\*\*|__|//|\\)")


def _esc(t):
    out = t.replace("\\", "\\\\")
    for _, m in MARKS:
        out = out.replace(m, "\\" + m)
    return out


def to_text(rich):
    """rich(문자열 | 조각 | 목록) → 표시가 든 한 줄."""
    if rich is None:
        return ""
    if isinstance(rich, str):
        return _esc(rich)
    if isinstance(rich, dict):
        t = _esc(rich.get("t", ""))
        for key, m in MARKS:
            if rich.get(key):
                t = m + t + m
        return t
    return "".join(to_text(x) for x in rich)


def _split(s):
    """표시를 조각으로. 겹친 표시(`**__x__**`)도 받는다."""
    out, buf, flags = [], [], {}
    i = 0
    while i < len(s):
        m = _ESC.match(s, i)
        if m:
            buf.append(m.group(1))
            i = m.end()
            continue
        hit = None
        for key, mk in MARKS:
            if s.startswith(mk, i):
                hit = (key, mk)
                break
        if hit:
            key, mk = hit
            if buf:
                out.append((("".join(buf)), dict(flags)))
                buf = []
            flags[key] = not flags.get(key)
            if not flags[key]:
                flags.pop(key)
            i += len(mk)
            continue
        buf.append(s[i])
        i += 1
    if buf:
        out.append(("".join(buf), dict(flags)))
    return out


def from_text(text, like=None):
    """표시가 든 한 줄 → rich. `like` 가 민글이면 민글로 돌려준다.

    `like` 는 **원래 값**이다 — 모양을 되도록 그대로 지키기 위한 것이지
    내용을 가져오지는 않는다.
    """
    parts = [(t, f) for t, f in _split(text) if t != ""]
    plain = all(not f for _, f in parts)
    if plain:
        joined = "".join(t for t, _ in parts)
        if isinstance(like, str) or like is None:
            return joined
        if isinstance(like, list) and len(like) == 1 and isinstance(like[0], str):
            return [joined]
        return joined
    segs = []
    for t, f in parts:
        if f:
            d = {"t": t}
            d.update({k: True for k in f})
            segs.append(d)
        else:
            segs.append(t)
    return segs[0] if len(segs) == 1 and isinstance(segs[0], dict) else segs


def plain(rich):
    """서식을 뗀 순수 글자 (길이 비교·검수용)."""
    if rich is None:
        return ""
    if isinstance(rich, str):
        return rich
    if isinstance(rich, dict):
        return rich.get("t", "")
    return "".join(plain(x) for x in rich)


# ══════════════════════════════════════════════════════════════════
# 글자 단위 서식 — 표시가 아니라 **진짜 서식**으로 고친다
# ══════════════════════════════════════════════════════════════════
#
# 위의 `to_text`/`from_text` 는 굵기·밑줄·기울임 셋만 표시(`**굵게**`)로 폈다
# 되접는다. 그걸로는
#   ① 고른 몇 글자만 12pt·빨강 같은 **임의 서식**을 담을 수 없고
#   ② 편집기를 열 때마다 글이 `**이렇게**` 보여 조판을 보는 눈이 흐트러진다.
#
# 그래서 편집기에는 **HTML** 을 준다. 사람은 보이는 대로 고치고, 저장할 때
# 그 HTML 을 세그먼트로 되접는다.
#
#   세그먼트  {"t": "글", "b": 1, "u": 1, "i": 1,
#              "st": {"font-size": "12pt", …},   ← 직접 서식
#              "cs": "강조"}                      ← 문자 스타일 이름
#
# ⚠ **민글로 들어온 것은 민글로 돌려준다.** 서식을 하나도 안 걸면 예전과
#   똑같은 문자열이 나와야 한다 — 안 그러면 data.json 이 달라져 회귀 대조가
#   시끄러워지고, 납품본과 글이 달라 보인다.
#
# ⚠ 조판이 만든 것(빈칸 밑줄 등)은 `data-raw` 에 **원본 글자**를 싣고 나간다.
#   그래야 편집기에서 빈칸처럼 보이면서도 되접을 때 정확히 돌아온다.
import html as _html
import re as _re

# 편집기가 허용하는 태그 — 이 밖의 것은 글자만 남긴다(붙여넣기 오염 방지)
_OK_TAGS = {"b", "strong", "u", "i", "em", "span", "br", "a"}
# 직접 서식으로 받는 CSS 속성 — 인쇄에 뜻이 있는 것만
ST_PROPS = ("font-size", "font-weight", "font-style", "font-family",
            "letter-spacing", "color", "background-color",
            "text-decoration", "vertical-align", "line-height")
_BLANK = _re.compile(r"_{3,}")


def _st_css(st):
    return "".join(f"{k}:{v};" for k, v in (st or {}).items()
                   if k in ST_PROPS and str(v).strip())


def seg_html(seg, blanks=True):
    """세그먼트 하나 → 편집기 HTML."""
    if isinstance(seg, str):
        t = _html.escape(seg)
        return _blank_html(t) if blanks else t
    if not isinstance(seg, dict):
        return ""
    t = _html.escape(seg.get("t", ""))
    if blanks:
        t = _blank_html(t)
    st = _st_css(seg.get("st"))
    cs = seg.get("cs")
    if st or cs:
        a = (f' class="cs-{_html.escape(str(cs))}"' if cs else "")
        a += (f' style="{st}"' if st else "")
        t = f"<span{a}>{t}</span>"
    if seg.get("u"):
        t = f"<u>{t}</u>"
    if seg.get("i"):
        t = f"<i>{t}</i>"
    if seg.get("b"):
        t = f"<b>{t}</b>"
    lk = safe_link(seg.get("lk"))
    if lk:
        t = f'<a class="viv-lk" href="{_html.escape(lk)}">{t}</a>'
    t += foot_html(seg)
    return t


# 링크로 받아 주는 것 — **여기 없는 것은 버린다**.
# ⚠ `javascript:` 같은 것을 그대로 실으면 그 HTML 을 여는 사람에게 그대로
#   실행된다. 조판 결과는 사람이 브라우저로도 열어 보므로 막아 둔다.
_LINK_OK = _re.compile(r'''^(https?://|mailto:|#)[^\s"'<>]*$''', _re.I)


def safe_link(v):
    """링크 주소를 걸러 낸다. 이상하면 **빈 문자열**(링크 없음)."""
    u = (v or "").strip() if isinstance(v, str) else ""
    return u if u and _LINK_OK.match(u) else ""


def foot_html(seg):
    """각주 — 그 자리에 번호를 달고 글은 **면 아래**로 내린다.

    조판 엔진이 `float: footnote` 로 한다(실측). 번호도 엔진이 센다 — 사람이
    세면 문단을 옮길 때마다 어긋난다.

        {"t": "출처가 붙는 글", "fn": "고교 영어 교과서, 2026"}

    ⚠ 각주 글은 **원고에 있는 그대로** 나간다(빈칸 표시는 안 한다).
      각주 안에서 또 각주를 달 수는 없다.
    """
    if not isinstance(seg, dict):
        return ""
    fn = seg.get("fn")
    if not fn:
        return ""
    body = _html.escape(fn if isinstance(fn, str) else plain(fn))
    return f'<span class="viv-fn">{body}</span>'


# 각주 모양 — 계열 테마가 덮어써도 된다. 조판 엔진이 면 아래로 내린다.
FOOT_CSS = """
/* 각주 — `float: footnote` 는 조판 엔진의 일이다(브라우저 미리보기에서는
   그냥 작은 글씨로 보인다). 번호는 엔진이 센다. */
.viv-fn { float: footnote; font-size: 7.5pt; line-height: 1.35; }
@page { @footnote { border-top: 0.4pt solid currentColor; padding-top: 1mm; } }
"""


def _blank_html(t):
    """`_____` → 빈칸처럼 보이는 조각(되접을 글자를 실어 둔다)."""
    return _BLANK.sub(
        lambda m: ('<span class="ed-blank" data-raw="%s">%s</span>'
                   % (m.group(0), "&nbsp;" * len(m.group(0)))), t)


def to_html(rich, blanks=True):
    """rich → 편집기 HTML. 보이는 그대로 고치게 하는 것이 목적이다."""
    if rich is None:
        return ""
    if isinstance(rich, (str, dict)):
        return seg_html(rich, blanks)
    return "".join(seg_html(x, blanks) for x in rich)


# ── HTML → 세그먼트 ────────────────────────────────────────────────
_TAG = _re.compile(r"<(/?)([a-zA-Z][\w-]*)((?:\s[^<>]*?)?)/?>")
_ATTR = _re.compile(r'([\w-]+)\s*=\s*"([^"]*)"')


def _parse_style(v):
    out = {}
    for bit in (v or "").split(";"):
        if ":" not in bit:
            continue
        k, _, val = bit.partition(":")
        k, val = k.strip().lower(), val.strip()
        if k in ST_PROPS and val:
            out[k] = val
    return out


def from_html(src, like=None):
    """편집기 HTML → rich. **민글이면 민글로 돌려준다.**"""
    segs, stack, buf = [], [], []

    def flush():
        if not buf:
            return
        t = "".join(buf)
        del buf[:]
        if not t:
            return
        fn = [False]                          # 이 덩어리가 각주 글인가
        f = {}
        st = {}
        cs = ""
        lk = ""
        for tag, attrs in stack:
            if tag in ("b", "strong"):
                f["b"] = True
            elif tag == "u":
                f["u"] = True
            elif tag in ("i", "em"):
                f["i"] = True
            elif tag == "span":
                st.update(_parse_style(attrs.get("style", "")))
                for c in (attrs.get("class") or "").split():
                    if c.startswith("cs-"):
                        cs = c[3:]
                    elif c == "viv-fn":
                        fn[0] = True          # 이 조각은 **각주 글**이다
            elif tag == "a":
                lk = safe_link(attrs.get("href", "")) or lk
        if fn[0]:
            # 각주는 **글이 아니라 딸린 것**이다 — 빈 조각에 실어 둔다.
            # (그 자리에 번호만 서고 글은 면 아래로 내려간다.)
            segs.append({"t": "", "fn": t})
            return
        if not (f or st or cs or lk):
            segs.append(t)
            return
        d = {"t": t}
        d.update(f)
        if st:
            d["st"] = st
        if cs:
            d["cs"] = cs
        if lk:
            d["lk"] = lk
        segs.append(d)

    i = 0
    while i < len(src):
        m = _TAG.search(src, i)
        if not m:
            buf.append(_html.unescape(src[i:]))
            break
        buf.append(_html.unescape(src[i:m.start()]))
        tag = m.group(2).lower()
        attrs = dict(_ATTR.findall(m.group(3) or ""))
        closing = bool(m.group(1))
        if tag in _OK_TAGS:
            if tag == "br":
                buf.append(" ")
            elif closing:
                flush()
                for j in range(len(stack) - 1, -1, -1):
                    if stack[j][0] == tag:
                        stack.pop(j)
                        break
            else:
                flush()
                # ⚠ 조판이 만든 조각은 **원본 글자**로 되돌린다
                raw = attrs.get("data-raw")
                if raw is not None:
                    buf.append(raw)
                    # 그 조각의 안쪽 글은 버린다(보여 주기용이었다)
                    end = src.find("</" + tag, m.end())
                    i = (end + len(tag) + 3) if end >= 0 else m.end()
                    continue
                stack.append((tag, attrs))
        i = m.end()
    flush()

    if not segs:
        return "" if isinstance(like, str) or like is None else []
    if all(isinstance(x, str) for x in segs):
        joined = "".join(segs)
        if isinstance(like, list) and len(like) == 1 and isinstance(like[0], str):
            return [joined]
        return joined
    # 붙어 있는 같은 서식은 하나로 — 잘게 쪼개진 채로 두면 data 가 지저분해진다
    out = []
    for s in segs:
        if out and isinstance(s, dict) and isinstance(out[-1], dict) \
                and {k: v for k, v in s.items() if k != "t"} \
                == {k: v for k, v in out[-1].items() if k != "t"}:
            out[-1]["t"] += s["t"]
        elif out and isinstance(s, str) and isinstance(out[-1], str):
            out[-1] += s
        else:
            out.append(dict(s) if isinstance(s, dict) else s)
    return out[0] if len(out) == 1 and isinstance(out[0], dict) else out


def seg_attr(seg):
    """조판 HTML 에 실을 **글자 서식 속성**(class·style).

    계열 렌더러가 세그먼트를 HTML 로 바꿀 때 이 한 줄만 끼우면, 작업대에서
    건 글자 단위 서식이 그대로 인쇄까지 간다. 서식이 없으면 빈 문자열이라
    **예전과 글자 하나 다르지 않다**(회귀가 조용하다).
    """
    if not isinstance(seg, dict):
        return ""
    st = _st_css(seg.get("st"))
    cs = seg.get("cs")
    a = ""
    if cs:
        a += ' class="cs-%s"' % _html.escape(str(cs))
    if st:
        a += ' style="%s"' % st
    return a
