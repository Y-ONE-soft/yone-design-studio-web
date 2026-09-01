"""정규식 스타일 — **꼴이 맞는 글자마다** 문자 스타일을 건다.

인디자인의 「단락 스타일 > 정규 표현식 스타일」이다. 사람이 일일이 고르지
않아도, 조판할 때마다 그 꼴을 찾아 스타일을 입힌다.

    "grep_styles": [
      {"pat": "\\\\d+%",       "cls": "강조"},
      {"pat": "\\\\[[^\\\\]]+\\\\]", "cls": "라벨", "sel": "head"}
    ]

`sel` 은 **그 클래스를 가진 태그 안에서만** 이라는 뜻이다(없으면 어디서나).

## 왜 조판 직전에 하나

계열마다 HTML 을 제 손으로 짜므로, 계열을 하나하나 고치면 또 빠뜨린다(표에서
겪었다). 조판은 전부 `cli.run_build()` 를 지나가므로 **거기서 한 번** 한다.
측정 조판도 같이 지나가니 잰 높이와 실제 조판이 어긋나지 않는다.

⚠ **태그 안은 절대 건드리지 않는다.** 속성값에 스타일을 끼우면 HTML 이
  깨진다 — 글자 자리(태그 바깥)만 바꾼다.
⚠ `<style>` · `<script>` 안도 안 건드린다.
⚠ 이미 스타일이 걸린 자리(`class="cs-…"`)에는 겹쳐 걸지 않는다.
"""
import json
import os
import re

FILE = "grep.json"
MAX_PAT = 200          # 정규식은 이보다 길 수 없다(되짚기 폭발 막이)
MAX_HITS = 20000       # 한 파일에서 이보다 많이 고치지 않는다


def write(build_dir, rules):
    """`build/grep.json` — 조판 직전에 읽는다. 규칙이 없으면 **지운다**."""
    p = os.path.join(build_dir, FILE)
    ok = [r for r in (rules or [])
          if isinstance(r, dict) and r.get("pat") and r.get("cls")]
    if not ok:
        if os.path.exists(p):
            os.remove(p)
        return ""
    os.makedirs(build_dir, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(ok, f, ensure_ascii=False)
    return p


def rules_for(html_path):
    p = os.path.join(os.path.dirname(os.path.abspath(html_path)), FILE)
    if not os.path.exists(p):
        return []
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f) or []
    except (OSError, ValueError):
        return []


_SKIP = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.I | re.S)
_TAG = re.compile(r"<[^>]*>")


def apply_text(html, rules):
    """HTML 글자 자리에만 규칙을 건다. 태그·스크립트는 그대로 둔다."""
    if not rules:
        return html, 0
    hits = [0]

    def one(part, rule, pat, cls, sel):
        # `sel` 이 있으면 그 클래스를 가진 태그 **안쪽**에서만
        return pat.sub(lambda m: _wrap(m, cls, hits), part)

    out = html
    for r in rules:
        pat_s = str(r.get("pat") or "")[:MAX_PAT]
        cls = re.sub(r"[^0-9A-Za-z가-힣_-]", "", str(r.get("cls") or ""))
        if not pat_s or not cls:
            continue
        try:
            pat = re.compile(pat_s)
        except re.error:
            continue                       # 못 알아들을 규칙은 **조용히 넘긴다**
        sel = re.sub(r"[^0-9A-Za-z가-힣_-]", "", str(r.get("sel") or ""))
        out = _walk(out, pat, cls, sel, hits)
    return out, hits[0]


def _wrap(m, cls, hits):
    if hits[0] >= MAX_HITS:
        return m.group(0)
    hits[0] += 1
    return '<span class="cs-%s">%s</span>' % (cls, m.group(0))


def _walk(html, pat, cls, sel, hits):
    """태그 바깥(글자 자리)만 골라 바꾼다."""
    out = []
    i = 0
    depth = 0          # `sel` 태그 안쪽 깊이(0 이면 바깥)
    want = bool(sel)
    stack = []
    for m in _TAG.finditer(html):
        text = html[i:m.start()]
        if text:
            out.append(_sub_text(text, pat, cls, hits)
                       if (not want or depth > 0) else text)
        tag = m.group(0)
        out.append(tag)
        i = m.end()
        low = tag.lower()
        if low.startswith("</"):
            if stack:
                was = stack.pop()
                if was:
                    depth -= 1
        elif not low.endswith("/>") and not low.startswith("<!"):
            name = re.match(r"<([a-zA-Z][\w-]*)", tag)
            void = name and name.group(1).lower() in (
                "br", "img", "hr", "meta", "link", "input")
            hit = bool(want and re.search(r'class="[^"]*\b%s\b' % re.escape(sel),
                                          tag))
            if not void:
                stack.append(hit)
                if hit:
                    depth += 1
    tail = html[i:]
    if tail:
        out.append(_sub_text(tail, pat, cls, hits)
                   if (not want or depth > 0) else tail)
    return "".join(out)


def _sub_text(text, pat, cls, hits):
    return pat.sub(lambda m: _wrap(m, cls, hits), text)


def apply_file(html_path):
    """조판 직전에 그 HTML 에 규칙을 건다. 건 곳 수를 돌려준다."""
    rules = rules_for(html_path)
    if not rules:
        return 0
    try:
        with open(html_path, encoding="utf-8") as f:
            src = f.read()
    except OSError:
        return 0
    if "<!--grep-done-->" in src:
        return 0                            # 두 번 걸지 않는다
    # `<style>` · `<script>` 는 통째로 떼어 두고 나중에 되돌린다
    keep = []

    def hide(m):
        keep.append(m.group(0))
        return "\x00%d\x00" % (len(keep) - 1)

    body = _SKIP.sub(hide, src)
    body, n = apply_text(body, rules)
    body = re.sub(r"\x00(\d+)\x00", lambda m: keep[int(m.group(1))], body)
    if not n:
        return 0
    body = body.replace("</body>", "<!--grep-done--></body>", 1)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(body)
    return n
