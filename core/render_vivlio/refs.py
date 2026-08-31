"""자리표 — 지면의 글 한 조각이 **data 안 어디서 왔는지**를 HTML 에 싣는다.

작업대에서 지면을 클릭해 그 자리에서 고칠 수 있게 하는 바닥. 고친 것은
`errata.json` 에 쌓이고 `data` 를 다시 뽑아도 얹힌다(`errata.py`).

## ⚠ 속성이 아니라 **클래스**로 싣는다

Vivliostyle 은 조판 결과 DOM 에 **임의 속성을 옮기지 않는다** — `data-ref` 만
심으면 화면에서 클릭해도 아무것도 못 찾는다(실제로 그랬다. 남는 것은
`data-vivliostyle-*` 와 `data-adapt-eloff` 뿐이다). 반면 **class 는 남는다**
(CSS 가 거기 걸려 있으니 당연하다). 그래서 `vrefN` 클래스로 싣고 번호↔경로 표는
`build/refs.json` 으로 따로 낸다. `data-ref` 는 원본 HTML 을 사람이 읽을 때를
위해 같이 남긴다.

## ⚠ 원래 클래스를 바꾸지 말 것

자리표를 붙이면서 **없던 클래스를 같이 얹으면 지면이 달라진다.** 블랙북에서
대화문 줄에 `.t` 를 얹었다가 `<보기>` 상자 줄바꿈이 바뀌어 26·61면이 어긋났다
— 글자는 하나도 안 틀려서 회귀 대조가 아니면 못 봤다. `mark()` 에 넘기는
`base` 는 **그 자리에 원래 있던 클래스 그대로**여야 한다.

## 쓰는 법

    refs.index(data, ("lessons", ("vocab", "problems", "answers")))  # 렌더 직전
    ...
    o.append(f'<p{refs.mark(refs.of(item, "stem"), "head")}>…')
    ...
    refs.dump(build_dir)                                            # 렌더 직후
"""
import json
import os
import re

_PATH = {}      # id(객체) → 점 경로
_SEQ = {}       # 점 경로 → 번호


def clear():
    _PATH.clear()
    _SEQ.clear()


def index(data, spec):
    """객체 → 경로 표를 만든다. 렌더 직전에 **한 번**.

    `spec` = (바깥 목록 이름, (안쪽 목록 이름들…)). 예)
      ("lessons", ("vocab", "problems", "answers"))  → lessons.0.problems.3
      ("units",   ("words",))                        → units.2.words.11
    """
    clear()
    outer, inners = spec
    for i, blk in enumerate(data.get(outer) or []):
        if not isinstance(blk, dict):
            continue
        for kind in inners:
            for j, obj in enumerate(blk.get(kind) or []):
                if isinstance(obj, dict):
                    _PATH[id(obj)] = "%s.%d.%s.%d" % (outer, i, kind, j)
    return _PATH


def index_lists(data, names):
    """평평한 목록들 → `head.12` 꼴. 단어장(vocabook)처럼 최상위가 바로 목록인 계열."""
    clear()
    for name in names:
        for i, obj in enumerate(data.get(name) or []):
            if isinstance(obj, dict):
                _PATH[id(obj)] = "%s.%d" % (name, i)
    return _PATH


def index_paths(data, paths):
    """겹겹이 든 목록까지 훑어 객체 → 경로 표를 만든다.

    `index()`(두 겹)·`index_lists()`(한 겹)로는 못 닿는 데가 있다. 단어장의
    워크북은 `workbook.3.sections.1.items.7` 로 세 겹이고, 특강은 부·강·문항이
    계열마다 다르게 겹친다. 그래서 **열쇠 사슬**을 받아 그대로 따라 내려간다.

        refs.index_paths(data, [
            ("head",),                            # head.12
            ("workbook", "sections", "items"),    # workbook.3.sections.1.items.7
        ])

    지나는 길의 **모든 dict 를 등록한다** — 위 예에서 `workbook.3` 과
    `workbook.3.sections.1` 도 자리표를 갖는다. 그래야 문항 하나가 아니라
    구역 전체에 쪽 나눔을 걸 수 있다.

    ⚠ 목록이 아닌 dict 를 만나면 그 자리에서 멈춘다(경로를 지어내지 않는다).
    """
    clear()
    def walk(node, prefix, chain):
        if not isinstance(node, list):
            return
        for i, obj in enumerate(node):
            if not isinstance(obj, dict):
                continue
            path = "%s.%d" % (prefix, i)
            _PATH.setdefault(id(obj), path)
            if chain:
                walk(obj.get(chain[0]), "%s.%s" % (path, chain[0]), chain[1:])
    for chain in paths:
        if not chain:
            continue
        walk(data.get(chain[0]), chain[0], list(chain[1:]))
    return _PATH


def of(obj, sub=""):
    """그 객체의 경로(+하위 항목). 표에 없으면 빈 문자열 = 자리표 없음."""
    r = _PATH.get(id(obj))
    if not r:
        return ""
    return "%s.%s" % (r, sub) if sub else r


# 자리표 이름의 **머리글자가 곧 출처**다. 작업대는 이걸 보고 어디를 고칠지 안다.
#   `lessons.…`  원고(data.json)   → 글자 편집은 `edits.json` 에 쌓인다
#   `book.…`     책 설정(config)   → 글자 편집은 `config.json` 을 고친다
#   `#…`         조판이 만든 것    → 고를 수만 있다(스타일·색·쪽 나눔)
CONFIG_PREFIX = "book."
FIXED_PREFIX = "#"


def source_of(ref):
    """그 자리의 글이 **어디서 오는가**. 작업대가 사람 말로 알려 주는 데 쓴다."""
    if not ref:
        return ""
    if ref.startswith(FIXED_PREFIX):
        return "fixed"
    if ref.startswith(CONFIG_PREFIX):
        return "config"
    return "data"


def mark(ref, base=""):
    """`class="<원래 클래스> vrefN" id="vrefN" data-ref="…"` 를 만든다.

    `ref` 가 비면 **원래 클래스만** 돌려준다(자리표 없는 자리는 그대로 둔다).

    세 가지를 다는 이유가 각각 다르다:
      class  조판 결과 DOM 에 **남는 유일한 것** → 클릭한 자리를 되짚고,
             면을 넘기며 그 자리를 찾아가는 데 쓴다
      id     원본 HTML 에만 있다. ⚠ **조판 결과에는 안 남는다** —
             `navigateToInternalUrl('#vrefN')` 로 뛸 수 있을 줄 알고 넣었는데
             아무 일도 안 일어났다(찾기 결과를 눌러도 지면이 안 움직였다).
             사람이 원본을 읽을 때를 위해 남겨 둔다.
      data-ref  결과에는 안 남지만 **조판할 때는 있다** → 스타일 선택자로 쓸 수 있다
             (`[data-ref="lessons.0.problems.3"]{break-before:page}` 처럼.
              CSS 는 조판하는 동안 적용되므로 사라진 뒤여도 상관없다)
    """
    if not ref:
        return ' class="%s"' % base if base else ""
    n = _SEQ.setdefault(ref, len(_SEQ) + 1)
    cls = (base + " " if base else "") + "vref%d" % n
    return ' class="%s" id="vref%d" data-ref="%s"' % (cls, n, ref)


_TAG = re.compile(r"<([a-zA-Z][\w-]*)((?:\s[^<>]*?)?)(/?)>")


def stamp(html_frag, ref):
    """이미 만들어진 조각의 **맨 앞 태그**에 자리표를 얹는다.

    계열에 따라서는 자리마다 손으로 `mark()` 를 넣기가 너무 많다(특강은 40여
    종류의 블록이 994줄에 흩어져 있다). 그런 계열은 조각이 한 곳(`put()`)을
    지나가므로, 거기서 한 번에 찍는 편이 낫다.

    ⚠ **class 를 두 번 쓰면 안 된다.** 같은 태그에 `class` 속성이 둘이면
      브라우저는 앞의 것만 읽고 우리 `vrefN` 을 버린다 — 화면에서 클릭이
      조용히 안 먹는다. 그래서 있으면 **합쳐 넣는다**.

    ⚠ 클래스가 없던 태그에는 `vrefN` 만 새로 붙는다. 뜻 있는 클래스를 얹으면
      판이 달라지지만(블랙북 26·61면), `vrefN` 은 어떤 CSS 도 안 걸리므로
      안전하다 — 블랙북 대화문 줄이 이미 그렇게 하고 있다.
    """
    if not ref or not html_frag:
        return html_frag
    m = _TAG.search(html_frag)
    if not m or m.start() != 0:
        return html_frag                       # 태그로 시작하지 않으면 손대지 않는다
    n = _SEQ.setdefault(ref, len(_SEQ) + 1)
    attrs = m.group(2) or ""
    if "data-ref=" in attrs:
        return html_frag                       # 이미 찍혔다
    cm = re.search(r'\bclass="([^"]*)"', attrs)
    if cm:
        attrs = (attrs[:cm.start(1)] + cm.group(1) + " vref%d" % n
                 + attrs[cm.end(1):])
    else:
        attrs += ' class="vref%d"' % n
    attrs += ' id="vref%d" data-ref="%s"' % (n, ref)
    return "<%s%s%s>%s" % (m.group(1), attrs, m.group(3),
                           html_frag[m.end():])


def table():
    return {str(n): r for r, n in _SEQ.items()}


def dump(build_dir):
    """`build/refs.json` — 작업대가 화면의 `vrefN` 을 원본으로 되짚는 데 쓴다."""
    os.makedirs(build_dir, exist_ok=True)
    p = os.path.join(build_dir, "refs.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(table(), f, ensure_ascii=False)
    return p
