"""
발문 → leaf 유형 코드 분류.

기본 사용:
    from engines._taxonomy import classify
    code, label, kind = classify("다음 글의 제목으로 가장 적절한 것은?")
    # → ('OBJ-CTN-TITLE', '제목', '객관식')
"""
from .rules import COMPILED


def normalize_question(q: str) -> str:
    """발문 표기 변형 정규화: HTML 엔티티, 다양한 괄호, 오타 등."""
    q = q.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    q = q.replace("〈", "<").replace("〉", ">").replace("《", "<").replace("》", ">")
    # 대괄호 [보기] / [조건] / [A] → 꺾쇠로 통일 (마크 라벨 [A], [B] 등은 영향 없게 단어 단위)
    q = q.replace("[보기]", "<보기>").replace("[조건]", "<조건>")
    q = q.replace("일고", "읽고")  # 오타
    return q


def classify(q: str):
    """발문 문자열을 받아 (code, label, kind) 튜플 반환.

    매칭 실패 시 (None, None, None).
    kind: "객관식" 또는 "서술형".
    """
    if not q:
        return None, None, None
    qn = normalize_question(q)
    for code, label, pat in COMPILED:
        if pat.search(qn):
            kind = "객관식" if code.startswith("OBJ") else "서술형"
            return code, label, kind
    return None, None, None


def classify_many(questions):
    """여러 발문을 한 번에 분류. 입력 = list[str], 출력 = list[dict]."""
    return [
        {"q": q, **dict(zip(("code", "label", "kind"), classify(q)))}
        for q in questions
    ]


def is_question(line: str) -> bool:
    """문자열이 발문 형태인지 휴리스틱 판정 (extract 단계에서 사용)."""
    import re
    s = line.strip()
    if len(s) < 12 or len(s) > 400:
        return False
    if not re.search(
        r"(다음 (?:글|문장|글의|중)|밑줄 친|글의 (?:흐름|문맥상|제목|주제|요지|내용|순서|빈칸|밑줄|목적|분위기|심경|어조|어휘|어법|괄호|밑줄)|"
        r"윗글|위 글|위의 글|아래 (?:글|문장)|주어진 (?:글|문장|단어)|"
        r"서술형\s*\d|객관식|어휘\s*추론|어법상|문맥상|글의 흐름|"
        r"적절한 것은|적절하지 않은 것은|있는 대로 고른|"
        r"가장 알맞은|쓰시오\s*\.?$|작성하시오|완성하시오|고치시오|"
        r"빈칸\s*\([A-Z]\)|빈칸\s*\[[A-Z]\]|빈칸에 들어갈)",
        s,
    ):
        return False
    if not re.search(
        r"(\?|것은|것을|것\?|시오\.?|것\?|기에 가장 적절한 곳은|쓰시오\.?|것끼리)",
        s[-30:],
    ):
        return False
    return True
