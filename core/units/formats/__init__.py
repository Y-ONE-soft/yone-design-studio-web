"""원고 형식 등록부 — 캔버스·렌더러는 책 종류(워크북·모의고사 …)를 모른다. 형식이 스스로 밝힌 것만 쓴다.

형식 모듈 하나 = 원고 한 종류를 읽는 어댑터. 모듈마다 밝히는 것:

    ID, NAME      형식 id · 사람이 읽는 이름
    LABELS        자리 이름 → 한글 이름 (캔버스 「원고 자리」 목록, 원고 전 자리 이름표)
    FMT           자리마다 기본 글 모양 (한 스토리에 흘릴 때 — 발문 굵게 같은 단락 스타일). 없으면 {}
    kinds()       유형 이름 목록 (면의 「받는 원고」). 원고를 넣기 전에도 고를 수 있게

원고 파일을 형식별로 읽던 것(detect · parse — 예전 조판 엔진 파서)은 2026-10-19 뺐다. 원고는 contents 레코드로 받는다.
"""
from core.units.formats import mockexam, workbook

REGISTRY = [workbook, mockexam]
BY_ID = {m.ID: m for m in REGISTRY}


def catalog():
    """캔버스에 내보낼 형식 목록 — 원고 없이 틀을 먼저 그릴 수 있게."""
    return [{"id": m.ID, "name": m.NAME, "fields": {k: v for k, v in m.LABELS.items() if k not in ("no", "answer")},
             "kinds": m.kinds(), "fmt": getattr(m, "FMT", {})} for m in REGISTRY]


def labels_all():
    """모든 형식의 자리 이름 — 원고를 붓기 전 자리 이름표·견본에 쓴다."""
    out = {}
    for m in REGISTRY:
        for k, v in m.LABELS.items():
            out.setdefault(k, v)
    return out
