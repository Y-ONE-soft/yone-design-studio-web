"""동형모의고사 '케이스'(템플릿 비품) 구성 (W51).

케이스 = 원고가 아니라 InDesign 템플릿에 수기로 들어있는 머리표/문제유형 박스
값들(저작권 문구, 시험명, 출제교사, 문항수·배점 …). 원고에는 없으므로 실제
운영에선 UI 입력이 필요하지만, 이번 배치(기반 + 동형 1종 연결)는 파일럿 코퍼스
(한영3)로 검증하므로 **파일럿 케이스 픽스처를 기본값**으로 쓰고, job 메타데이터로
아는 필드(학교/시험기간 등)만 덮어쓴다.
"""
import json
import os

_PILOT_CASE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "pilot", "vivliostyle", "case_hanyoung3.json")

_PERIOD_TO_EXAM = {
    "26-1-중간": "2026학년도 1학기 중간고사",
    "26-1-기말": "2026학년도 1학기 기말고사",
    "26-2-중간": "2026학년도 2학기 중간고사",
    "26-2-기말": "2026학년도 2학기 기말고사",
}


def _load_default_case():
    try:
        with open(_PILOT_CASE, encoding="utf-8") as f:
            case = json.load(f)
        case.pop("_doc", None)
        case.pop("corpus_case", None)
        case.pop("reference_pdf", None)
        return case
    except (OSError, ValueError):
        return {}


def build_case(content, job_dir=None, meta=None):
    """content.json + job 메타데이터 → 케이스 dict.

    Args:
        content: content.json (school/grade/… 포함).
        job_dir: 메타 .txt 조회용(선택).
        meta: 추가 오버라이드 dict(선택).
    """
    case = _load_default_case()
    school = (content or {}).get("school") or case.get("school_full", "")
    grade = (content or {}).get("grade", "")

    def _read_meta(key):
        if meta and meta.get(key):
            return meta[key]
        if job_dir:
            p = os.path.join(job_dir, f"{key}.txt")
            if os.path.exists(p):
                return open(p, encoding="utf-8").read().strip()
        return ""

    if school:
        case["school_full"] = school
        # 저작권 문구의 학교명만 실제 학교로 교체(문구 골격은 픽스처 유지)
        case["copyright_line"] = (
            f"이 시험 문제의 저작권은 {school}에 있습니다. 저작권법에 의해 "
            f"보호받는 저작물이므로 무단 전재와 복제는 금지되며, 이를 어길시 "
            f"저작권법에 의거 처벌될 수 있습니다.")

    exam_period = _read_meta("exam_period")
    if exam_period and exam_period in _PERIOD_TO_EXAM:
        case["exam_title"] = _PERIOD_TO_EXAM[exam_period]
    exam_type = _read_meta("exam_type")
    if exam_type:
        # "1학기 기말고사" → "2026학년도 1학기 기말고사"
        case["exam_title"] = f"2026학년도 {exam_type}" if "학년도" not in exam_type \
            else exam_type
    exam_date = _read_meta("exam_date")
    if exam_date:
        case.setdefault("_exam_date", exam_date)

    if meta:
        for k, v in meta.items():
            if v:
                case[k] = v
    if grade:
        case.setdefault("_grade", grade)
    return case
