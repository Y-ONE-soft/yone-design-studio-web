"""계열별 예측 어댑터 (역학습 W46 — 권고 ③).

역학습 채점기는 "원고(content.json) → 현행 파이프라인이 예측한 스타일"을
필요로 한다. W44 파일럿은 워크북 계열(engines.workbook_v2.plan)만 다뤘고,
블랙북/세서특필/화이트북은 content.json 구조가 달라 채점 대상 밖이었다.

여기서 하는 일은 **경로 연결뿐**이다 — 각 계열의 v2 플랜 빌더를 그대로
호출해 결과를 공통 형태로 정규화한다:

    {"flows": [{"step": <영역키>, "units": [...]}, ...]}

("step"은 워크북의 스텝 키 자리 — 블랙북/세서특필/화이트북에서는 flow의
"area"를 그대로 쓴다. 정렬·채점은 이 키를 스토리 그룹 단위로만 쓴다.)

플랜 빌더 자체(스타일 결정 로직)는 건드리지 않는다. 어댑터가 실패하면
그 쌍은 건너뛴다(호출자가 기록).
"""

SERIES_ADAPTER = {
    "워크북": "workbook",
    "워크북(모의고사)": "workbook",
    "교과서워크북": "workbook",
    "EBS워크북": "workbook",
    "블랙북": "blackbook",
    "세서스페셜": "seseospecial",
    "화이트북": "whitebook",
}


def adapter_for(series, content=None):
    """계열명(+ content 구조) → 어댑터 이름. 못 정하면 None."""
    name = SERIES_ADAPTER.get(series)
    if name:
        return name
    c = content or {}
    if isinstance(c.get("steps"), dict) and c["steps"]:
        return "workbook"
    if c.get("sections"):
        return "blackbook"
    if c.get("part1") is not None or c.get("part2") is not None:
        return "seseospecial"
    if c.get("days") is not None:
        return "whitebook"
    return None


def _norm(plan):
    """flow의 area/step 키를 "step"으로 통일 (flatten_plan 계약)."""
    flows = []
    for i, f in enumerate(plan.get("flows") or []):
        g = dict(f)
        g["step"] = f.get("step") or f.get("area") or "flow%d" % i
        flows.append(g)
    out = dict(plan)
    out["flows"] = flows
    return out


def _workbook(content, job_dir=None):
    from engines.workbook_v2.plan import ensure_step3_kinds, steps_to_plan
    steps = content.get("steps") or {}
    ensure_step3_kinds(steps.get("step3"))
    return steps_to_plan(
        steps, workbook_type=content.get("workbook_type") or "모의고사")


def _blackbook(content, job_dir=None):
    """블랙북은 v2 파서가 원고(docx)에서 직접 IR을 만든다 — v1 content.json의
    sections(part1_problem …)는 형태가 달라 그대로 못 쓴다. job의 uploads/가
    남아 있으면 v2 파서를 그대로 태우고(진짜 현행 예측 경로), 없으면 포기."""
    from engines.blackbook_v2.render import sections_to_plan
    sections = content.get("sections") or {}
    if "problems_p1" in sections:
        return sections_to_plan(sections)
    up = _uploads(job_dir)
    if not up:
        raise ValueError("블랙북 예측 불가 — uploads 원고 없음")
    from engines.blackbook_v2.parser import parse_files
    return sections_to_plan(parse_files(up))


def _uploads(job_dir):
    import os
    if not job_dir:
        return []
    d = os.path.join(job_dir, "uploads")
    if not os.path.isdir(d):
        return []
    return [os.path.join(d, n) for n in sorted(os.listdir(d))
            if not n.startswith(".")
            and n.lower().endswith((".docx", ".hwp", ".hwpx"))]


def _seseospecial(content, job_dir=None):
    from engines.seseospecial_v2.plan import content_to_plan
    return content_to_plan(content)


def _whitebook(content, job_dir=None):
    from engines.whitebook_v2.plan import content_to_plan
    return content_to_plan(content)


BUILDERS = {
    "workbook": _workbook,
    "blackbook": _blackbook,
    "seseospecial": _seseospecial,
    "whitebook": _whitebook,
}


def can_predict(content, series="", job_dir=None):
    """이 쌍에서 현행 예측(플랜)을 만들 수 있는가 — 수집기의 plan_ready 판정."""
    name = adapter_for(series, content)
    if not name:
        return False
    if name == "workbook":
        return bool(isinstance(content.get("steps"), dict) and content["steps"])
    if name == "blackbook":
        sec = content.get("sections") or {}
        return bool("problems_p1" in sec or _uploads(job_dir))
    if name == "seseospecial":
        return bool(content.get("part1") or content.get("part2"))
    if name == "whitebook":
        return bool(content.get("days"))
    return False


def build_plan(content, series="", job_dir=None):
    """content.json → 공통 형태 플랜. (plan, adapter_name) 반환."""
    name = adapter_for(series, content)
    if not name:
        raise ValueError("예측 어댑터 없음 (계열=%s)" % series)
    return _norm(BUILDERS[name](content, job_dir=job_dir)), name
