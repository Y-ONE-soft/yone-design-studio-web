"""OKLCH 색 도구 — **톤을 유지한 채 색상만 돌리기** 위해 쓴다.

단원마다 지면 색을 바꾸되 "톤은 계속 맞춰야" 할 때, HSL 로 색상만 돌리면
톤이 무너진다(같은 S·L 이라도 노랑은 밝고 파랑은 어둡게 보인다). OKLCH 는
L 이 **지각 밝기**라, `L` 과 `C/최대채도` 비율을 고정한 채 `H` 만 돌리면
네 단원이 같은 톤으로 읽힌다.

`max_c(L, H)` 는 그 밝기·색상에서 sRGB 를 벗어나지 않는 최대 채도다. 채도를
절대값으로 옮기면 색상에 따라 어떤 건 색이 죽고 어떤 건 영역을 벗어나므로,
**최대채도 대비 비율**로 옮긴다.
"""
import math

# sRGB ↔ OKLab (Björn Ottosson)
_M1 = ((0.4122214708, 0.5363325363, 0.0514459929),
       (0.2119034982, 0.6806995451, 0.1073969566),
       (0.0883024619, 0.2817188376, 0.6299787005))
_M2 = ((0.2104542553, 0.7936177850, -0.0040720468),
       (1.9779984951, -2.4285922050, 0.4505937099),
       (0.0259040371, 0.7827717662, -0.8086757660))
_N1 = ((1.0, 0.3963377774, 0.2158037573),
       (1.0, -0.1055613458, -0.0638541728),
       (1.0, -0.0894841775, -1.2914855480))
_N2 = ((4.0767416621, -3.3077115913, 0.2309699292),
       (-1.2684380046, 2.6097574011, -0.3413193965),
       (-0.0041960863, -0.7034186147, 1.7076147010))


def _dot(m, v):
    return tuple(sum(a * b for a, b in zip(row, v)) for row in m)


def _srgb2lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _lin2srgb(c):
    return 12.92 * c if c <= 0.0031308 else 1.055 * (c ** (1 / 2.4)) - 0.055


def hex2rgb(h):
    h = (h or "").lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def rgb2hex(rgb):
    return "#" + "".join(f"{min(255, max(0, round(c * 255))):02x}" for c in rgb)


def rgb2oklch(rgb):
    lin = tuple(_srgb2lin(c) for c in rgb)
    lms = _dot(_M1, lin)
    L, a, b = _dot(_M2, tuple(math.copysign(abs(v) ** (1 / 3), v) for v in lms))
    C = math.hypot(a, b)
    H = math.degrees(math.atan2(b, a)) % 360.0
    return L, C, H


def oklch2rgb(L, C, H):
    a = C * math.cos(math.radians(H))
    b = C * math.sin(math.radians(H))
    lms = _dot(_N1, (L, a, b))
    lin = _dot(_N2, tuple(v ** 3 for v in lms))
    return tuple(_lin2srgb(c) for c in lin)


def hex2oklch(h):
    return rgb2oklch(hex2rgb(h))


def oklch2hex(L, C, H):
    return rgb2hex(oklch2rgb(L, C, H))


def in_gamut(L, C, H, tol=1e-4):
    return all(-tol <= c <= 1 + tol for c in oklch2rgb(L, C, H))


def max_c(L, H, hi=0.45, steps=28):
    """그 밝기·색상에서 sRGB 안에 드는 최대 채도(이분 탐색)."""
    lo = 0.0
    if not in_gamut(L, 0.0, H):
        return 0.0
    for _ in range(steps):
        mid = (lo + hi) / 2
        if in_gamut(L, mid, H):
            lo = mid
        else:
            hi = mid
    return lo


def rotate(hex_color, hue):
    """밝기와 **최대채도 대비 비율**을 지킨 채 색상만 `hue` 로 돌린다."""
    L, C, H = hex2oklch(hex_color)
    top = max_c(L, H)
    pct = (C / top) if top else 0.0
    return oklch2hex(L, pct * max_c(L, hue), hue)
