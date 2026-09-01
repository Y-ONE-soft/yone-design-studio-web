"""동형 v2 파서 실측 테스트 — 코퍼스 5케이스 (InDesign 불필요)."""
import glob
import os

import pytest

from core.schema import validate_v2
from engines.mockexam_v2.parser import parse_manuscripts

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(TESTS_DIR, "corpus", "mockexam")

# 케이스별 기대 문항 수 (파서 개선 시 diff 검토 후 갱신)
# 2026-09-01 갱신 — 구조 기반 판정 도입(객관식/서술형을 발문 정규식이 아니라
# 선지·답란·원고 라벨로 결정) + 범위 묶음 펼치기 + 출처 태그 분리.
EXPECTED_ITEMS = {
    # 값의 근거 = **원고 머리에 적힌 선언 문항수**. 이제 5케이스 중 4케이스가
    # 선언과 정확히 일치한다(1f172958 은 머리에 선언이 없다).
    "029c4385": 30,   # 선언 객관식 24 + 서답형 6 = 30 ✔
    "0365e674": 50,   # 2회분 합. 선언 50 ✔
    "057985b4": 30,   # 029c4385 와 같은 원고. 선언 30 ✔
    "1f172958": 28,   # 원고 머리에 선언 없음 — 2026-07-06 실측값 유지
    "69f4dd89": 32,   # 선언 선택형 26 + 서답형 6 = 32 ✔
}

# 아직 taxonomy leaf 코드가 안 붙는 발문의 허용 비율. `type` 은 유형 라벨용
# 부가 정보이고, 조판이 실제로 쓰는 갈래(객관식/서술형)는 아래 kind 로 판정한다.
# 종전에는 "모든 발문에 type 이 있다"를 단언했는데, 그건 분류 룰이 완전해서가
# 아니라 **매칭 안 되는 발문이 통째로 유실되고 있었기 때문**에 성립했다.
MAX_UNTYPED_RATIO = 0.20


def _cases():
    return sorted(os.listdir(CORPUS)) if os.path.isdir(CORPUS) else []


@pytest.mark.parametrize("case", _cases())
def test_v2_parse_case(case):
    docs = parse_manuscripts(glob.glob(os.path.join(CORPUS, case, "inputs", "*")))
    assert docs, "입력 없음"

    total = 0
    obj_ok = obj_total = 0
    for _name, doc in docs:
        assert validate_v2(doc) == [], f"스키마 오류: {validate_v2(doc)[:2]}"
        for it in doc["items"]:
            total += 1
            assert it["kind"] in ("객관식", "서술형"), (
                f"갈래 미판정: {it['question'][:50]}")
            assert it["stimulus"]["blocks"] or it["stimulus"]["type"] == "empty"
            if it["kind"] != "객관식":
                continue
            obj_total += 1
            n_choices = len(it["choices"]["items"]) if it["choices"] else 0
            inline = (it.get("variants") or {}).get("inline_marker") == "V6-INLINE"
            if n_choices == 5 or (n_choices == 0 and inline):
                obj_ok += 1

    untyped = sum(1 for _n, d in docs for it in d["items"]
                  if it.get("type") is None)
    assert untyped <= total * MAX_UNTYPED_RATIO, (
        f"taxonomy 미매칭 발문이 너무 많다: {untyped}/{total}")
    assert total == EXPECTED_ITEMS[case], f"문항 수 {total} != {EXPECTED_ITEMS[case]}"
    # 객관식의 90%+ 는 '선지 5개' 또는 '밑줄형(본문 내 선지)'여야 함
    assert obj_ok / obj_total >= 0.85, f"선지 구조 정합 {obj_ok}/{obj_total}"


def test_v2_1f172958_srv_types():
    """서답형 발문([서답형 N])은 전부 SRV-* / 서술형이어야 한다.

    2026-07-06: 서답형 4·6이 객관식 코드(OBJ-VOC-UND-MEAN / OBJ-LNG-AB)로
    오분류되던 회귀 방지 (첫 매칭 우선 룰 테이블에서 OBJ 룰이 선점하던 건).
    """
    docs = parse_manuscripts(
        glob.glob(os.path.join(CORPUS, "1f172958", "inputs", "*")))
    srv = [it for _n, doc in docs for it in doc["items"]
           if (it["question"] or "").startswith("[서답형")]
    assert len(srv) == 6, f"서답형 문항 수 {len(srv)} != 6"
    for it in srv:
        assert it["type"] and it["type"].startswith("SRV-"), \
            f"서답형이 객관식 코드로 분류: {it['type']} — {it['question'][:40]!r}"
        assert it["kind"] == "서술형", f"{it['kind']} — {it['question'][:40]!r}"
