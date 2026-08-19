"""배경 SVG 헬퍼 — Vivliostyle 에서 '도형'을 그리는 유일하게 안전한 방법.

왜 전부 배경 SVG 인가(전부 실제로 데인 것):
  · 마진 박스(러닝 요소)에서 `transform: rotate()` · `visibility: hidden` 은 무시된다
  · 마진 박스에 `position: relative` 를 주면 `position: running()` 이 덮여
    **본문에 그대로 그려진다**
  · 마진 박스에서 세로 음수 마진은 잘린다(가로 음수 마진 + 같은 크기 패딩만 통함)
  · 박스 높이(= 페이지 여백)를 넘는 요소는 잘린다
  · 본문에서도 `clip-path` + `filter: drop-shadow()` 를 같이 주면 요소가 통째로 사라진다
  · `border-radius` 는 자식을 자르지 않는다
  · `@page` 배경의 `repeating-linear-gradient` 는 주기가 어긋난다

그래서 장식·도형은 예외 없이 배경 SVG(data URI)로 굽는다. 색이 SVG 안에 **구워져**
들어가므로, 팔레트를 바꾸면 반드시 생성기를 다시 돌려야 한다(안 그러면 띠·밴드만
옛 색으로 남는다 — 실제로 두 번 발생).

⚠ 좌표를 옮길 때는 **박스(width/height)도 같이 키울 것**. 안 키우면 도형이 박스
밖에서 잘린다. `get_drawings()` 는 클리핑 전 bbox 라 "좌표는 맞는데 안 보이는"
상황이 생긴다 — 좌표 확인으로 끝내지 말고 고해상도 렌더로 눈으로 볼 것.
"""

NS = "http://www.w3.org/2000/svg"


def h(color):
    """`#` 는 data URI 안에서 프래그먼트로 잘린다 → `%23`."""
    return (color or "").replace("#", "%23")


def data_uri(w, h_, body, viewbox=None, repeat="no-repeat"):
    """SVG data URI background 값. w/h 는 mm, viewBox 는 mm 수치와 1:1."""
    vb = viewbox or f"0 0 {w} {h_}"
    return ("url(\"data:image/svg+xml;utf8,"
            f"<svg xmlns='{NS}' width='{w}mm' height='{h_}mm' "
            f"viewBox='{vb}'>{body}</svg>\")"
            + (f" {repeat}" if repeat else ""))


def rect(x, y, w, h_, fill, opacity=None):
    op = f" opacity='{opacity}'" if opacity is not None else ""
    return f"<rect x='{x}' y='{y}' width='{w}' height='{h_}' fill='{h(fill)}'{op}/>"


def line(x1, y1, x2, y2, stroke, width=0.25):
    return (f"<line x1='{x1}' y1='{y1}' x2='{x2}' y2='{y2}' "
            f"stroke='{h(stroke)}' stroke-width='{width}'/>")


def path(d, fill=None, stroke=None, width=None, opacity=None):
    a = f"<path d='{d}'"
    if fill:
        a += f" fill='{h(fill)}'"
    if stroke:
        a += f" stroke='{h(stroke)}'"
    if width is not None:
        a += f" stroke-width='{width}'"
    if opacity is not None:
        a += f" opacity='{opacity}'"
    return a + "/>"


def mirror(body, w):
    """좌우 반전 — 오른쪽에서 시작하는 면용(태그·꼬리를 바깥쪽으로)."""
    return f"<g transform='translate({w},0) scale(-1,1)'>{body}</g>"


def hrules(w, h_, pitch, stroke, width=0.25, start=None):
    """가로 괘선 묶음(MEMO 면).

    `repeating-linear-gradient` 는 Vivliostyle 에서 주기가 어긋난다 — 줄을 하나씩
    그린 SVG 로 대신한다.
    """
    y = pitch if start is None else start
    body = []
    while y <= h_ + 1e-9:
        body.append(line(0, round(y, 3), w, round(y, 3), stroke, width))
        y += pitch
    return data_uri(w, h_, "".join(body))


def hairline(color, w, thickness=0.353):
    """얇은 괘선을 **선 두께만 한 상자**로 깐다.

    `linear-gradient` 의 색 정지점으로 그린 얇은 선은 72dpi 로 래스터화되며
    사라진다. 단색 그라디언트를 두께만 한 배경 상자로 두면 남는다.
    """
    return (f"linear-gradient({h(color)}, {h(color)}) no-repeat "
            f"0 0 / {w}mm {thickness}mm")
