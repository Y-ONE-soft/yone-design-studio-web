"""워크북 v2 플랜 빌더 가드 — step3 (W1). 스텝 확장 시 여기에 케이스 추가."""
import json
import os

from engines.workbook_v2.plan import steps_to_plan

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


def test_step3_builder_corpus():
    inv = set(json.load(open(os.path.join(
        TESTS_DIR, "fixtures", "template_spec_workbookC.json"),
        encoding="utf-8"))["paragraph_styles"])
    case = os.path.join(TESTS_DIR, "corpus", "workbook", "0a5da924")
    c = json.load(open(os.path.join(case, "golden", "content.json"),
                       encoding="utf-8"))
    plan = steps_to_plan(c["steps"])
    s3 = next(f for f in plan["flows"] if f["step"] == "step3")
    assert len(s3["units"]) == 22
    assert s3["target"] == {"master": "O"}
    styles = {p["s"] for u in s3["units"] for p in u}
    assert all(s in inv for s in styles), styles - inv
    # 정답/그룹헤더는 제거돼야 함 (kind GH/A → 미포함)
    texts = [p["t"] for u in s3["units"] for p in u]
    assert not any(t.strip() in ("정답", "[정답]") for t in texts)
