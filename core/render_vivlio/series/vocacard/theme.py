"""vocacard 테마 생성 — `vocabook.theme` 의 팔레트/치수(③)→배경 SVG(②) 생성
로직을 그대로 불러 쓰되, 스타일시트 소스만 자체 파일(`themes/vocacard.css`)로
가리킨다. `build_css()` 는 파일 텍스트를 `/*@PRELUDE@*/`/`/*@GENERATED@*/` 자리에
치환하는 방식이라 계열마다 스타일시트가 한 벌 필요하다 — vocabook.css 를
공유하면 상일보카 쪽 CSS 를 건드리게 되어 파일을 나눴다.
"""
import os

from core.render_vivlio.series.vocabook.theme import (  # noqa: F401 (재노출)
    DEFAULT_METRICS, metrics_of, sections_of, prelude, generated,
)

THEME_SRC = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "themes", "vocacard.css")


def build_css(cfg):
    src = open(THEME_SRC, encoding="utf-8").read()
    return (src.replace("/*@PRELUDE@*/", prelude(cfg))
               .replace("/*@GENERATED@*/", generated(cfg)))


def write(cfg, path, log=None):
    css = build_css(cfg)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(css)
    if log:
        m = metrics_of(cfg)
        log(f"[테마] {len(css.splitlines())}줄 생성 "
            f"(밴드 {m['band_h']}mm · 띠 {m['strip_h']}mm · "
            f"섹션 {len(sections_of(cfg))}) → {os.path.basename(path)}")
    return path
