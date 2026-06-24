"""파서 회귀 기준선 — 지문번호/헤더 형식 카탈로그.

구조 인식 방식으로 파서를 재작성할 때, 기존에 지원하던 모든 형식이
'동일하게' 처리되는지 검증하기 위한 안전망.

각 케이스: 원고 단락 리스트(헤더 + 지문번호 + 본문...) →
  - _strip_manuscript_headers 결과의 첫 단락 (= 헤더가 제대로 잘렸는지)
  - _extract_question_numbers 결과 (= 지문번호 인식)

`python3 -m engines.workbook._parser_regression`  로 현재 동작 출력.
재작성 후 같은 출력이 나오면 회귀 0.
"""
from engines.workbook import parser as P


def _mk(texts):
    return [{"text": t, "runs": [{"t": t, "ul": False}]} for t in texts]


# (이름, 원고 단락들, 기대: 본문 시작 단락 텍스트, 기대 지문번호)
CASES = [
    ("L형 교과서 (L1-본문1)",
     ["공통영어1 비상(홍)", "Q. 다음 글을 읽고 물음에 답하시오.", "1. L1-본문1",
      "A month ago, I flew to San Francisco, feeling excited.", "2. L1-본문2",
      "Fisherman's Wharf is popular for its shops."]),
    ("L-페이지형 (L4-p.82)",
     ["책 제목", "1. L4-p.82", "The kitchen is a great place to begin."]),
    ("모의고사 (p2-no.20)",
     ["고1_2025_10월", "1. p2-no.20", "This is the first passage body text here."]),
    ("대괄호 한글 ([본문1])",
     ["어휘선택(문제지)", "[본문1]", "The body text starts here after marker."]),
    ("대괄호 숫자 ([20])",
     ["헤더", "[20]", "Passage twenty body content goes here now."]),
    ("본문정리 ([Project 2-1])",
     ["[Project 2-1]", "《Cooking and Eating for the Planet》",
      "The kitchen is a great place to begin making changes."]),
    ("YBM김 새형 (PROJECT 2-본문1)",
     ["공통영어1_YBM김은형 - PROJECT 2", "Q. [   ] 안에서 어법 상 알맞은 것을 고르시오.",
      "어법선택(문제지)", "", "READING", "1. PROJECT 2-본문1",
      "《Cooking and Eating for the Planet》 The kitchen is a great place.",
      "2. PROJECT 2-본문2", "《Eat Organic Vegetables》 Consume more products."]),
]


def run():
    for name, texts in CASES:
        paras = _mk(texts)
        stripped = P._strip_manuscript_headers(paras)
        first = stripped[0]["text"] if stripped else "(빈)"
        nums = P._extract_question_numbers(paras, "test")
        print("[%s]" % name)
        print("   헤더제거 후 첫 단락: %r" % first[:50])
        print("   지문번호 인식:       %s" % nums)
        print()


if __name__ == "__main__":
    run()
