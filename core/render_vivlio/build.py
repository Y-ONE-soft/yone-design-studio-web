"""Vivliostyle 빌드 러너 (W51) — 렌더 플랜/HTML → PDF.

파일럿 `pilot/vivliostyle/build.py` 를 일반화한 것. 시리즈별 HTML 생성은
`core.render_vivlio.<series>` 모듈이, 시리즈별 스타일은 `themes/<theme>.css` 가
담당하고, 이 파일은 **공통 빌드 오케스트레이션**(HTML/테마/폰트/자산 배치 →
vivliostyle CLI 실행 → 마지막 페이지 오버라이드 재빌드)만 맡는다.

InDesign 경로와 완전히 독립적이다(별도 Node 프로세스). 실서비스 Python 과 무관.
"""
import os
import shutil
import subprocess  # noqa: F401 — 하위 호환(외부에서 참조)
import time        # noqa: F401

from core.render_vivlio import cli as _cli
from core.render_vivlio import stage as _stage

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
THEMES_DIR = _stage.THEMES_DIR

# CLI 위치·실행은 `core.render_vivlio.cli` 가 단일 소스다. 아래 이름들은 기존
# 호출부(engines/mockexam_v2_viv 등) 호환을 위해 남긴 별칭.
PILOT_DIR = _cli.PILOT_DIR
CLI_BIN = _cli.cli_path() or _cli._CANDIDATES[0]
ASSETS_DIR = os.path.join(PILOT_DIR, "assets")
CLI_VERSION = _cli.CLI_VERSION

# 실물이 쓰는 서체의 로컬 설치 파일 (실측: pdffonts + fc-list). 없으면 스킵.
DEFAULT_FONT_FILES = [
    "~/Library/Fonts/HANDotum.ttf",
    "~/Library/Fonts/HANDotumB.ttf",
    "~/Library/Fonts/HANBatang.ttf",
    "~/Library/Fonts/HANBatangB.ttf",
    "~/Library/Fonts/H2GTRE.TTF",
    "~/Library/Fonts/NanumMyeongjo.otf",
    "~/Library/Fonts/NanumMyeongjoBold.otf",
]


VivliostyleUnavailable = _cli.VivliostyleUnavailable


def cli_available():
    return _cli.cli_available()


def count_pdf_pages(path):
    from core.render_vivlio import probe
    return probe.page_count(path)


def _run_cli(html_path, pdf_path, log, timeout):
    return _cli.run_build(html_path, pdf_path, log=log, timeout=timeout)


def _copy_theme(theme, build_dir, log):
    """`themes/<theme>.css` → build_dir/theme.css (+ 공통 골격 `_base.css`)."""
    return _stage.stage_theme(build_dir, theme, log)


def _copy_fonts(build_dir, font_files, log):
    _stage.stage_fonts(build_dir, font_files or DEFAULT_FONT_FILES, log,
                       required=False)


def _copy_assets(build_dir):
    return _stage.stage_assets(build_dir, ASSETS_DIR)


def render_html_to_pdf(html_text, theme, out_pdf, log, *, build_dir=None,
                       font_files=None, last_page_end=False, timeout=300):
    """HTML 문자열 → PDF (하위 레벨).

    Args:
        html_text: 완성된 HTML. `<link rel="stylesheet" href="theme.css">` 를
            포함해야 한다(이 함수가 theme.css 를 build_dir 에 배치).
        theme: `themes/<theme>.css` 시리즈 테마 이름.
        out_pdf: 산출 PDF 절대경로.
        build_dir: 중간 산출(html/css/fonts) 디렉터리. None 이면 out_pdf 옆 build/.
        last_page_end: True 면 1차 빌드로 페이지 수를 잰 뒤 마지막 페이지에
            '끝.' 러닝 푸터(element(pageFooterLast))를 주입해 재빌드.
    Returns:
        {"pdf": out_pdf, "pages": int|None, "seconds": float, "passes": int}
    """
    out_pdf = os.path.abspath(out_pdf)
    if build_dir is None:
        build_dir = os.path.join(os.path.dirname(out_pdf), "_vivlio_build")
    os.makedirs(build_dir, exist_ok=True)
    os.makedirs(os.path.dirname(out_pdf), exist_ok=True)

    # 마지막 페이지 오버라이드 링크 주입(1차는 빈 lastpage.css)
    override = os.path.join(build_dir, "lastpage.css")
    open(override, "w").close()
    if 'href="lastpage.css"' not in html_text:
        html_text = html_text.replace(
            '<link rel="stylesheet" href="theme.css">',
            '<link rel="stylesheet" href="theme.css">\n'
            '<link rel="stylesheet" href="lastpage.css">')

    html_path = os.path.join(build_dir, "index.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_text)
    _copy_theme(theme, build_dir, log)
    _copy_fonts(build_dir, font_files, log)
    _copy_assets(build_dir)

    total = 0.0
    passes = 1
    total += _run_cli(html_path, out_pdf, log, timeout)
    pages = count_pdf_pages(out_pdf)

    if last_page_end and pages:
        with open(override, "w", encoding="utf-8") as f:
            f.write(f"@page :nth({pages}) {{\n"
                    f"  @bottom-center {{ content: element(pageFooterLast); }}\n"
                    f"}}\n")
        total += _run_cli(html_path, out_pdf, log, timeout)
        pages = count_pdf_pages(out_pdf)
        passes = 2

    return {"pdf": out_pdf, "pages": pages, "seconds": round(total, 1),
            "passes": passes}


# 시리즈 이름 → HTML 빌더 (플랜+케이스 → HTML 문자열)
def _series_html_builder(theme):
    if theme == "mockexam":
        from core.render_vivlio import mockexam
        return mockexam.build_html
    raise ValueError(f"지원하지 않는 vivlio 테마/시리즈: {theme}")


def render_plan_to_pdf(plan, theme, out_pdf, log, *, case=None,
                       build_dir=None, font_files=None, last_page_end=True,
                       timeout=300):
    """렌더 플랜 → PDF (공개 API).

    Args:
        plan: [{"t","s","runs"}] 렌더 플랜(백엔드 무관 데이터).
        theme: 시리즈 이름 = `themes/<theme>.css`. HTML 빌더도 이 이름으로 선택.
        out_pdf: 산출 PDF 절대경로.
        case: 시리즈별 템플릿 비품(머리표/문제유형 박스 등) dict.
    Returns:
        render_html_to_pdf 의 반환 dict.
    """
    build_html = _series_html_builder(theme)
    html_text = build_html(plan, case or {})
    return render_html_to_pdf(html_text, theme, out_pdf, log,
                              build_dir=build_dir, font_files=font_files,
                              last_page_end=last_page_end, timeout=timeout)
