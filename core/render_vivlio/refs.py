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


def of(obj, sub=""):
    """그 객체의 경로(+하위 항목). 표에 없으면 빈 문자열 = 자리표 없음."""
    r = _PATH.get(id(obj))
    if not r:
        return ""
    return "%s.%s" % (r, sub) if sub else r


def mark(ref, base=""):
    """`class="<원래 클래스> vrefN" id="vrefN" data-ref="…"` 를 만든다.

    `ref` 가 비면 **원래 클래스만** 돌려준다(자리표 없는 자리는 그대로 둔다).

    세 가지를 다는 이유가 각각 다르다:
      class  조판 결과 DOM 에 **남는 유일한 것** → 클릭한 자리를 되짚는 데 쓴다
      id     조판 결과에도 남아 **그 자리로 이동**할 수 있다(검색 결과 → 지면)
      data-ref  결과에는 안 남지만 **조판할 때는 있다** → 스타일 선택자로 쓸 수 있다
             (`[data-ref="lessons.0.problems.3"]{break-before:page}` 처럼.
              CSS 는 조판하는 동안 적용되므로 사라진 뒤여도 상관없다)
    """
    if not ref:
        return ' class="%s"' % base if base else ""
    n = _SEQ.setdefault(ref, len(_SEQ) + 1)
    cls = (base + " " if base else "") + "vref%d" % n
    return ' class="%s" id="vref%d" data-ref="%s"' % (cls, n, ref)


def table():
    return {str(n): r for r, n in _SEQ.items()}


def dump(build_dir):
    """`build/refs.json` — 작업대가 화면의 `vrefN` 을 원본으로 되짚는 데 쓴다."""
    os.makedirs(build_dir, exist_ok=True)
    p = os.path.join(build_dir, "refs.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(table(), f, ensure_ascii=False)
    return p
