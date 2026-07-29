"""Vivliostyle 렌더 백엔드 (W51) — 파일럿(`pilot/vivliostyle/`)을 실서비스
재사용 백엔드로 승격한 것.

핵심 계약: **렌더 플랜(list[{"t","s","runs"}]) → 시맨틱 HTML + CSS 테마 →
@vivliostyle/cli → PDF**. 렌더 플랜은 기존 v2 파이프라인(예: mockexam_v2 의
`ir_to_render_plan`)이 만든 데이터 그대로다 — 같은 플랜을 InDesign 백엔드로도,
이 백엔드로도 조판할 수 있다(백엔드 무관 자산).

공개 API:
    build.render_plan_to_pdf(plan, theme, out_pdf, log, *, case=None, ...)
        시리즈 테마(`themes/<theme>.css`)를 골라 플랜을 PDF로 렌더.
    build.render_html_to_pdf(...)  — HTML 문자열을 직접 받는 하위 레벨 함수.

Node/CLI 의존은 실서비스 Python 3.9 와 **무관한 별도 프로세스**다.
CLI 위치·버전은 `build.py` 상단 상수 참조(파일럿 node_modules 재사용).
"""

from core.render_vivlio.build import (  # noqa: F401
    render_plan_to_pdf,
    render_html_to_pdf,
    count_pdf_pages,
    cli_available,
    VivliostyleUnavailable,
)
