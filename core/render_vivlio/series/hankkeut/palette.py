"""한끝 계열 파트 팔레트 — OKLCH 로 설계해 sRGB 로 굳힌다.

3계층(반복 지적 규칙 — 주색 + 보조색 + 공통색, 한 색의 채도 차이는 보조색이 아니다):
  · 주색 main/mid/deep/soft/pale/tint — **구조**: 머리 배지·문항 번호·쪽번호·간지 번호
  · 보조색 sub/submid/subpale/subtint — **내용 강조**: 요약문 상자·배열 조각 번호.
    주색과 색상환에서 멀리(대략 보색 쪽) 떨어뜨린다
  · 공통색 — 표지(돌·종이 톤)에서 온 웜그레이·아이보리 + K 회색 단계.
    지문 상자·조건 상자·괘선·부가 정보. 파트 색으로 물들이지 않는다

파트가 몇 개 나올지 모르므로 여섯 벌을 미리 두고, 넘치면 처음부터 다시 돈다.
톤(L·C)은 여섯 파트가 같고 색상만 돌린다 — 하우스 색감(C .06~.10 / L .68~.85,
중등 같이새김·블랙북 실측과 같은 곡선).

⚠ 금지색: 더스티 모브코럴(#DB9488)·세이지 그린(#81B98C) 계열을 어두운 톤으로 쓰지 않는다.
⚠ 흰 글자는 deep 위에만. 9pt 미만 글자·얇은 선은 유채색 대신 K 회색(4도 망점이 뭉갠다).
⚠ 따뜻한 색(주황·노랑)은 어두워지면 갈색 — deep 을 슬레이트로 받는다(5파트).
"""
import math

# (파트, 주색상, 보조색상, 진한색 색상 — None 이면 주색상, 'slate' 면 뉴트럴 잉크)
PARTS = (
    (1, 245, 60, None),       # 하늘 파랑 / 살구
    (2, 352, 190, None),      # 로즈 / 아쿠아
    (3, 172, 300, None),      # 민트 틸 / 라벤더
    (4, 292, 88, None),       # 바이올렛 / 레몬
    (5, 62, 238, 'slate'),    # 애프리콧 / 스카이
    (6, 208, 325, None),      # 아쿠아 블루 / 오키드 (코랄 22 는 submid 가 더스티 코랄로 떨어져 뺐다)
)

TONE = {
    'main': (0.815, 0.095),   # 색면 — 간지 띠·범위 칩
    'mid':  (0.660, 0.110),   # 괘선·작은 마크(얇은 선에 main 을 쓰면 사라진다)
    'deep': (0.500, 0.120),   # 흰 글자를 얹는 배경 · 큰 번호
    'soft': (0.890, 0.060),
    'pale': (0.945, 0.032),
    'tint': (0.975, 0.014),
}
TONE_SUB = {
    'sub':     (0.800, 0.095),
    'submid':  (0.680, 0.105),
    'subpale': (0.940, 0.036),
    'subtint': (0.974, 0.017),
}

# 공통색. K 단계는 **순수 회색**이라 인쇄에서 K 단색으로 내린다(print.gray_map).
COMMON = {
    'ink': '#231F20',      # K100 본문 먹
    'k80': '#58595B', 'k70': '#6D6E71', 'k60': '#808285', 'k50': '#939598',
    'k40': '#A7A9AC', 'k30': '#BCBEC0', 'k20': '#D1D3D4', 'k10': '#E6E7E8',
    'paper': '#FFFFFF',
    'ivory': '#F8F6F0',    # 지문 상자 — 표지 종이 톤을 아주 옅게
    'ivory2': '#F0EDE5',   # 조건 상자
    'stone': '#E5E2DA',    # 간지 바탕(표지 돌 톤)
}
K_RAMP = {'ink': 1.0, 'k80': 0.8, 'k70': 0.7, 'k60': 0.6, 'k50': 0.5,
          'k40': 0.4, 'k30': 0.3, 'k20': 0.2, 'k10': 0.1, 'paper': 0.0}

KEYS = tuple(TONE) + tuple(TONE_SUB)


def _srgb(L, C, H):
    h = math.radians(H)
    a, b = C * math.cos(h), C * math.sin(h)
    l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s = (L - 0.0894841775 * a - 1.2914855480 * b) ** 3
    rgb = (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
           -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
           -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)
    out = []
    for v in rgb:
        v = max(0.0, min(1.0, v))
        v = 12.92 * v if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055
        out.append(int(round(max(0.0, min(1.0, v)) * 255)))
    return '#%02X%02X%02X' % tuple(out)


def part_colors(no):
    """파트 번호(1부터) → 색 표. 여섯을 넘으면 처음부터 다시 돈다."""
    _, H, H2, HD = PARTS[(no - 1) % len(PARTS)]
    out = {k: _srgb(L, C, H) for k, (L, C) in TONE.items()}
    if HD == 'slate':
        out['deep'] = _srgb(0.430, 0.050, 250)
        out['mid'] = _srgb(0.680, 0.120, H - 12)
    elif HD is not None:
        out['deep'] = _srgb(0.500, 0.120, HD)
    out.update({k: _srgb(L, C, H2) for k, (L, C) in TONE_SUB.items()})
    return out


def css(n_parts):
    """:root 공통색 + `.pN` 파트 변수. 파트 수와 무관하게 최소 여섯 벌을 낸다."""
    L = [':root {']
    for k, v in COMMON.items():
        L.append(f'  --{k}: {v};')
    L.append('}')
    for no in range(1, max(6, n_parts) + 1):
        c = part_colors(no)
        L.append(f'.p{no} {{ ' + ' '.join(f'--{k}: {c[k]};' for k in KEYS) + ' }')
    return '\n'.join(L) + '\n'


# 유형 칩 — (바탕 soft, 왼쪽 띠). 유형은 파트와 **다른 축**이라 파트 색과 따로 둔다.
# 한 파트 안에 여섯 유형이 섞여 나오므로(한서끝 40제) 칩 색이 곧 4도 다양성이다.
# 띠는 0.9mm 색면이라 얇은 선 규칙에 안 걸린다. 더스티 코랄·세이지 계열은 피했다.
TYPE_COLORS = {
    'summary': ('#FDE4D0', '#EE9B5B'),   # 살구
    'grammar': ('#D4F1E4', '#3DAE87'),   # 민트
    'ask':     ('#E7E1FB', '#8B78D4'),   # 바이올렛
    'match':   ('#D6ECFA', '#3D98D3'),   # 스카이
    'arrange': ('#FBDDE8', '#DD6E9B'),   # 로즈
    'vocab':   ('#F6ECC4', '#CFA12B'),   # 골드
    'etc':     ('#EEEEEF', '#939598'),
}


def type_css():
    return ''.join(f'.ty-{k} {{ background: {bg}; border-left-color: {bar}; }}\n'
                   for k, (bg, bar) in TYPE_COLORS.items())


def gray_map():
    """인쇄(CMYK) — 무채색은 K 단색으로. 빠진 회색은 ICC 를 타 리치그레이가 된다."""
    return {COMMON[k].lower(): v for k, v in K_RAMP.items()}


if __name__ == '__main__':
    for no in range(1, len(PARTS) + 1):
        c = part_colors(no)
        print(no, ' '.join(f'{k}={c[k]}' for k in KEYS))
