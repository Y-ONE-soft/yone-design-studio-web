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
