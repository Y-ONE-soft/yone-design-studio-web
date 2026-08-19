"""자연 높이 실측 — "한 면에 한 항목만 조판해 바닥 잉크를 잰다".

가변 배치(한 면 2문항, 펼침면 단위 흐름)를 하려면 항목이 **실제로 몇 mm 인지**
알아야 한다. 추정 공식으로는 안 된다(글꼴 대체·줄바꿈·상자가 다 영향을 준다).
그래서 측정 전용 HTML 을 한 번 더 조판해 재고, 그 값으로 본 조판을 한 번에 끝낸다.
반복 조판으로 수렴시키려 하면 발산한다.

계열 무관한 부분은 "PDF → 항목별 높이" 뿐이다. 측정용 HTML(항목마다 개면)은
계열 렌더러가 만든다.
"""
import json
import os

from core.render_vivlio import cli, probe


def heights_from_pdf(pdf, keys, top, bottom, pad=0.0, skip_blank=True):
    """측정용 PDF → {key: 높이mm}.

    Args:
        keys: 조판 순서대로의 항목 키 목록(문항 번호 등).
        top: 본문 시작 y(mm) — 머리 영역을 제외하는 경계. 높이의 원점이기도 하다.
        bottom: 본문 끝 y(mm) — 꼬리 영역 제외.
        pad: 실측값에 더할 여유(mm).
        skip_blank: 파리티로 생긴 빈 면 건너뛰기.
    Raises:
        ValueError: 측정된 면 수 ≠ 항목 수 (침묵 유실 금지)
    """
    out, k = {}, 0
    with probe.open_pdf(pdf) as doc:
        for page in doc:
            b = probe.ink_bottom(page, top=top - 1.5, bottom=bottom)
            if skip_blank and b <= top:
                continue
            if k >= len(keys):
                k += 1
                continue
            out[str(keys[k])] = round(b - top + pad, 1)
            k += 1
    if k != len(keys):
        raise ValueError(f"높이 측정 실패: 항목 {len(keys)} vs 측정 면 {k}")
    return out


def measure(html_path, out_pdf, keys, top, bottom, pad=0.0, log=None,
            timeout=900):
    """측정용 HTML 조판 → 항목별 높이 dict."""
    cli.run_build(html_path, out_pdf, log=log, timeout=timeout)
    return heights_from_pdf(out_pdf, keys, top, bottom, pad)


def save(heights, path, log=None, label="높이"):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(heights, f, ensure_ascii=False, indent=0)
    hs = sorted(heights.values())
    if hs:
        (log or print)(
            f"■ {label} 측정 {len(hs)}개  최소 {hs[0]}mm / "
            f"중앙 {hs[len(hs) // 2]}mm / 최대 {hs[-1]}mm")
    return path


def load(path):
    if path and os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return {}
