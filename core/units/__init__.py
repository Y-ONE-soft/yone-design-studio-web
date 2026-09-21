"""디자인 단위 — 원자(인디자인 오브젝트) → 부품 → 블록 → 지면 → 구간 → 틀 · 옷 · 세트.

스키마는 `core/schema/units.schema.json`, 설명·보기는 `docs/디자인_단위_스키마.md`.

    store      라이브러리 읽기·쓰기 — catalog/_units/<kind>.json (볼륨이 정본, 리포는 시드)
    render     원자 JSON → SVG. 부품·지면·틀을 같은 코드로 그린다. 콘텐츠는 세트에서, 색·서체는 옷에서
    decompose  PDF 한 면·이미지·프롬프트 → 원자 목록 + 부품 후보 (같은 원자 형식)
    sample     필드 타입별 견본 값 — 콘텐츠 없이 디자인만 볼 때

기존 계열 렌더러(core/render_vivlio/series/*)와는 독립이다 — 납품 중인 책은 건드리지 않는다.
"""
