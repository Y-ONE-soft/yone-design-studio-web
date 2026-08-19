"""W59 블랙북 v2 — 교과서 블랙북(공백 마커·화살표 요약·채점 기준·해석) 구조 인식.

Vivliostyle 파이프라인(조판/교재/프리미엄북/블랙북/26-2-중간)과 대조해 드러난
차이를 고정한다. 원고 파일 없이 도는 합성 입력.

  1) `< 보 기 >` 처럼 글자 사이를 띄운 마커도 보기 상자
  2) `(a) 한글 문장` 보기 항목이 한글이라는 이유로 상자에서 떨어져 나가지 않음
  3) `↓` 는 버리지 않고, 그 다음 단락은 요약문(박스) — 밑줄이 길어 답란으로
     보이더라도 화살표 신호가 우선
  4) `[채점 기준]` 은 조건 블록
  5) 원고 순서 유지 — 보기 → 선지 → 답란 → 채점 기준
  6) 해설 원고의 `[해석]` 이 유실되지 않음
"""
import sys

from core.structure.paragraph_kind import _base_kind, classify_paragraphs
from engines.blackbook.parser import _parse_answer_lines
from engines.blackbook_v2.render import _ir_item_to_unit
from engines.mockexam_v2.parser import build_ir

sys.path.insert(0, ".")


def _paras(*texts):
    return [{"text": t, "runs": [{"t": t}]} for t in texts]


def test_spaced_box_marker_and_grading_marker():
    assert _base_kind("< 보 기 >")[0] == "Box"
    assert _base_kind("[채점 기준]")[0] == "Cond"
    assert _base_kind("[답안 작성 안내]")[0] == "Cond"
    # 정답/해설 라벨은 조건이 아니다 (해설 원고 오염 방지)
    assert _base_kind("[정답]")[0] != "Cond"


def test_korean_box_items_stay_in_box():
    out = classify_paragraphs(_paras(
        "< 보 기 >",
        "(a) 미국인 Sam이 기타 부분을 더한다.",
        "(b) 글쓴이가 키보드로 곡을 연주해 보낸다.",
    ))
    assert [o["kind"] for o in out] == ["Box", "Box", "Box"]


def test_choices_are_not_swallowed_by_box():
    out = classify_paragraphs(_paras(
        "< 보 기 >",
        "( experiences / had / have / life )",
        "① 첫 번째 선지입니다.",
    ))
    assert out[1]["kind"] == "Box"
    assert out[2]["kind"] == "C"


def test_arrow_kept_and_summary_boxed():
    doc = build_ir(_paras(
        "1. 다음 글의 내용을 한 문장으로 요약하고자 한다. 빈칸 (A), (B)에 들어갈 말로 "
        "가장 적절한 것은?",
        "The band members lived in different time zones and could not meet, "
        "so they assembled each song part by part instead of playing together.",
        "↓",
        "a shared name ________________________________________",
        "① routine  ―  limit",
    ))
    blocks = doc["items"][0]["stimulus"]["blocks"]
    labels = [b.get("label") for b in blocks]
    assert "Sym" in labels, "화살표가 버려졌다"
    # 밑줄이 길어 답란으로 잡히더라도 화살표 다음 = 요약문
    assert labels[labels.index("Sym") + 1] == "Sum"


def test_plan_order_is_manuscript_order():
    doc = build_ir(_paras(
        "13. 다음 글의 빈칸에 들어갈 말을 <보기>의 단어를 모두 사용하여 배열하시오.",
        "Our band is something really special and we talk about everything "
        "together, including the hardships we face in our own daily lives.",
        "< 보 기 >",
        "( experiences / had / have / life / nor / same / the / we )",
        "답 : ______________________________________________",
        "[채점 기준]",
        "1. 주어진 단어는 모두 한 번씩만 사용할 것",
    ))
    flow = {"Q": "Q", "P": "P", "Box": "Box", "Box@summary": "Sum",
            "Ans": "Ans", "Cond": "Cond", "C": "C", "UNKNOWN": "U",
            "Sym": "Sym", "Word": "W", "K": "K", "P-CONTEXT": "PC",
            "Q-INTRO": "QI", "AnsL": "Ans"}
    kinds = [p["s"] for p in _ir_item_to_unit(doc["items"][0], flow)]
    assert kinds.count("Box") >= 1 and "Ans" in kinds and "Cond" in kinds
    assert kinds.index("Box") < kinds.index("Ans") < kinds.index("Cond"), kinds
    # 원고가 라벨을 들고 있으면 합성 <조건> 을 넣지 않는다
    texts = [p["t"] for p in _ir_item_to_unit(doc["items"][0], flow)]
    assert "<조건>" not in texts and "[채점 기준]" in texts


def test_answer_translation_is_kept():
    got = _parse_answer_lines([
        "1", "[정답] ③",
        "[해석] 우리 밴드는 정말로 특별한 무언가이다.",
        "[해설] 멤버들은 비슷한 배경도 같은 경험도 없다.",
    ])
    assert len(got) == 1
    assert got[0]["answer"] == "③"
    assert got[0]["translation"].startswith("우리 밴드는")
    assert got[0]["explanation"].startswith("멤버들은")
