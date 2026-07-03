"""블랙북 v2 전환 타당성 가드 — 파서 일반화 + 프레임 기하 재현성.

(1) mockexam_v2의 build_ir(무수정)이 블랙북 문제 파일의 문항 수를 정확 재현
(2) template_spec의 프레임 좌표로 v1 JSX의 module/large/narrow 영역 분류 재현
"""
import glob
import json
import os
import unicodedata

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


def test_build_ir_generalizes_to_blackbook():
    from engines.blackbook.kind_parser import classify_filename
    from engines.mockexam_v2.parser import extract_file_paragraphs, build_ir

    case = os.path.join(TESTS_DIR, "corpus", "blackbook", "027d750a")
    golden = json.load(open(os.path.join(case, "golden", "content.json"),
                            encoding="utf-8"))["sections"]
    got = {}
    for f in sorted(glob.glob(os.path.join(case, "inputs", "*"))):
        name = unicodedata.normalize("NFC", os.path.basename(f))
        for pre in ("manuscript_", "answers_"):
            if name.startswith(pre):
                name = name[len(pre):]
        kind = classify_filename(name)
        if kind in ("part1_problem", "part2_problem"):
            doc = build_ir(extract_file_paragraphs(f))
            got[kind] = got.get(kind, 0) + len(doc["items"])
    assert got["part1_problem"] == len(golden["part1_problem"]) == 107
    assert got["part2_problem"] == len(golden["part2_problem"]) == 43


def test_frame_geometry_classification_from_spec():
    spec = json.load(open(os.path.join(TESTS_DIR, "fixtures",
                                       "template_spec_blackbook.json"),
                          encoding="utf-8"))
    counts = {"module": 0, "large": 0, "narrow": 0}
    for pg in spec["page_map"]:
        for fr in pg["frames"]:
            t, l, b, r = fr["bounds"]
            w, h = r - l, b - t
            if h < 30 or w < 50:
                continue
            if w >= 150 and h < 200:
                counts["module"] += 1
            elif w >= 150 and h >= 200:
                counts["large"] += 1
            elif w < 100 and h >= 200:
                counts["narrow"] += 1
    # 코퍼스 표준(문제 107+43=150)을 담을 수 있는 프레임 수 확보
    assert counts["module"] >= 150, counts
    assert counts["large"] >= 8 and counts["narrow"] >= 2, counts
