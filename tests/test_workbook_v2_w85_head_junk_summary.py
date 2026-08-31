"""W85 — Step3 머리 워크시트 블록 + 요약문 배경 (사용자 반복 지적).

2026-08-31 성덕고2 EBS 연계 외부지문 조판:
  ① 원고 머리의 표제·머리글 막대·기입란이 실전문제 첫 지면에 인쇄됐다.
     ("성덕고2 EBS 연계 외부지문 고난도 변형문제 / 외부지문 1~5번 | 객관식
      50문항 | 학생용 / 학교 ____ / 이름 ____ / 점수 ____ / 제목")
     기존 선두 정리는 **첫 실질 줄**에서 멈춰(30자 상한) 표제 한 줄만 보고
     중단했다 — 머리 블록을 끝까지 걷어야 한다.
  ② 요약 문제의 요약문에 배경(상자) 스타일이 안 붙었다. 판정이 '발문 직후'
     만 봐서, 발문 → 지문 → 요약문 → 선지 순서인 원고를 놓쳤다.
"""


def _p(*texts):
    return [{"text": t, "runs": [{"t": t, "ul": False}]} for t in texts]


def _texts(paras):
    from engines.workbook.parser import _s3_text
    return [_s3_text(p) for p in paras if _s3_text(p)]


def test_head_block_is_stripped_to_first_content_line():
    from engines.workbook.parser import _strip_step3_rights_and_title
    rows = _p("SEONGDEOK HS 2 · EBS LINKED PASSAGES",
              "성덕고2 EBS 연계 외부지문 고난도 변형문제",
              "외부지문 1~5번  |  객관식 50문항  |  학생용",
              "학교  __________________",
              "이름  __________________",
              "점수  __________________",
              "",
              "1. 다음 글의 제목으로 가장 적절한 것은?",
              "Rangers in Kenya have outfitted elephants with collars.")
    assert _texts(_strip_step3_rights_and_title(rows)) == [
        "1. 다음 글의 제목으로 가장 적절한 것은?",
        "Rangers in Kenya have outfitted elephants with collars."]


def test_head_strip_stops_at_content_and_keeps_mid_document():
    """문서 중간은 무접촉 — 권리 고지만 걷어낸다."""
    from engines.workbook.parser import _strip_step3_rights_and_title
    rows = _p("1. 다음 글의 제목으로 가장 적절한 것은?",
              "A passage that ends with a period.",
              "이 자료는 저작권의 보호를 받는 저작물로 무단 배포할 수 없습니다.",
              "짧은 줄",                     # 중간의 짧은 줄은 그대로
              "2. 다음 글의 주제는?")
    out = _texts(_strip_step3_rights_and_title(rows))
    assert "짧은 줄" in out
    assert not any("저작권" in t for t in out)
    assert len(out) == 4


def test_summary_after_passage_gets_background():
    """요약문은 발문 직후가 아니라 **지문 뒤**에 온다."""
    from core.structure import classify_paragraphs
    rows = _p("16. 다음 글의 내용을 한 문장으로 요약하고자 한다. "
              "빈칸 (A), (B)에 들어갈 말로 가장 적절한 것은?",
              "",
              "Nicknames and their associated identities have become an "
              "important means of identifying the participants in online "
              "chat rooms and newsgroups, a sociolinguist observes.",
              "",
              "A nickname is not a neutral label: it leaks ____(A)____ "
              "about its owner and therefore lets the user control the "
              "____(B)____ that others form online.",
              "",
              "        (A)                       (B)",
              "①  personal clues  ……  speaking style",
              "②  official records  ……  first impression")
    kinds = [r["kind"] for r in classify_paragraphs(rows)]
    texts = [p["text"] for p in rows]
    i = next(i for i, t in enumerate(texts) if t.startswith("A nickname"))
    assert kinds[i] == "P-CONTEXT"          # → 배경 스타일
    j = next(i for i, t in enumerate(texts) if t.startswith("Nicknames"))
    assert kinds[j] == "P"                  # 지문은 그대로


def test_two_column_choice_header_is_not_a_summary():
    """'(A)   (B)' 두 열 선지 머리도 형태 판정은 통과한다 — 길이로 가른다."""
    from core.structure import classify_paragraphs
    rows = _p("7. 다음 글의 빈칸 (A), (B)에 들어갈 말로 가장 적절한 것은?",
              "",
              "A passage about advertising that runs on for a while and "
              "ends with a period so it reads as a body paragraph.",
              "",
              "(A)     (B)",
              "① Nevertheless  Instead",
              "② Moreover  Thus")
    kinds = [r["kind"] for r in classify_paragraphs(rows)]
    i = next(i for i, p in enumerate(rows) if p["text"].strip() == "(A)     (B)")
    assert kinds[i] != "P-CONTEXT"
