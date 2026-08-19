"""Vivliostyle 렌더 백엔드 — HTML/CSS → @vivliostyle/cli → PDF.

**3계층**으로 나뉜다. 계열이 늘어도 손대는 곳이 정해져 있게 하기 위한 것이다.

  ① 공용 백엔드 = 이 패키지 루트
     cli(설치·실행) · stage(서체/테마/자산 배치) · probe(PDF 계측) ·
     paged(2패스 면 지정) · measure(자연 높이 실측) · bleed(도련·TrimBox·간지) ·
     verify(검수 게이트) · svg(배경 SVG) · config/book(책 오케스트레이션)
     — 어느 계열에도 없는 것이 없고, 어느 계열에만 있는 것도 없다.

  ② 계열 = `series/<이름>/`
     원고 인식 + 마크업 + 스타일. 단어장(vocabook), 프리미엄북 블랙북(blackbook),
     그리고 앞으로 늘어날 것들. 새 계열은 `series/base.Series` 네 훅만 채운다.

  ③ 책 1권 = 교재 폴더의 `config.json` + 원고
     판형·도련 · 팔레트 · 원고 파일명 · 간지 경로 · 계열 옵션. 교재 폴더는 git 이
     아니므로 **코드를 두지 않는다**(복사하는 순간 포크가 늘고 롤백이 안 된다).

두 갈래 진입점이 있다:

  · 책 한 권 조판 (단어장·블랙북 …)
        from core.render_vivlio import book
        book.main(["<책폴더>", "build"])

  · 렌더 플랜 백엔드 (동형모의고사 v2 — InDesign 과 같은 플랜을 CSS 로 조판)
        from core.render_vivlio.build import render_plan_to_pdf

Node/CLI 의존은 실서비스 Python 과 **무관한 별도 프로세스**다.
"""

from core.render_vivlio.build import (  # noqa: F401
    render_plan_to_pdf,
    render_html_to_pdf,
    count_pdf_pages,
    cli_available,
    VivliostyleUnavailable,
)
